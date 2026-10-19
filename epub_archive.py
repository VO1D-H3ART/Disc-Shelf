"""Safe, RAM-backed EPUB opening for DiscShelf.

EPUBs are read only on demand, not during filename scanning. Only web-renderable
book resources are unpacked into tmpfs; no source files are modified, no network
is used, and no persistent cache/index is created. The GUI owns the returned
preview and must call cleanup_epub() after closing the WebEngine page.
"""
from __future__ import annotations

import os
import posixpath
import shutil
import stat
import tempfile
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

# EPUB 2 NCX and EPUB 3 XHTML navigation documents may contain legitimate
# <!DOCTYPE ...> declarations. defusedxml allows those while rejecting XML
# entity declarations and external entity expansion.
try:
    from defusedxml import ElementTree as SafeET
    from defusedxml.common import DefusedXmlException
except ImportError:  # Keep the bookshelf usable even before EPUB deps are installed.
    SafeET = None
    DefusedXmlException = ()

from office_conversion import ram_temp_root

EPUB_PREFIX = 'discshelf-epub-'
MAX_EPUB_BYTES = 256 * 1024 * 1024
MAX_UNPACKED_BYTES = 384 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 4000
MAX_XML_BYTES = 4 * 1024 * 1024
CHUNK_SIZE = 256 * 1024
PAGE_EXTENSIONS = frozenset({'.xhtml', '.html', '.htm'})
RENDER_EXTENSIONS = PAGE_EXTENSIONS | frozenset({
    '.css', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.avif',
    '.svg', '.ico', '.woff', '.woff2', '.ttf', '.otf', '.eot',
})


class EpubError(Exception):
    """Friendly error for malformed, oversized, or unsupported books."""


class EpubCancelled(EpubError):
    pass


@dataclass(frozen=True)
class EpubChapter:
    label: str
    archive_path: str  # relative to the EPUB tmpfs directory


@dataclass(frozen=True)
class EpubTocItem:
    label: str
    archive_path: str
    fragment: str = ''
    level: int = 0


@dataclass(frozen=True)
class EpubPreview:
    temp_directory: str
    display_title: str
    chapters: tuple[EpubChapter, ...]
    toc: tuple[EpubTocItem, ...]


def cleanup_epub(path: str | None) -> None:
    """Remove only EPUB-generated RAM folders, never anything on the disc."""
    if not path:
        return
    directory = Path(path)
    try:
        from office_conversion import _mount_type
        if (not directory.is_symlink() and directory.name.startswith(EPUB_PREFIX)
                and _mount_type(directory) == 'tmpfs'):
            shutil.rmtree(directory)
    except OSError:
        pass


def _check_cancelled(cancelled: threading.Event) -> None:
    if cancelled.is_set():
        raise EpubCancelled('EPUB opening cancelled.')


def _checked_name(name: str) -> str:
    """Validate an actual ZIP member name; do not silently normalize traversal."""
    if (not name or name.startswith('/') or '\\' in name or '\x00' in name
            or any(part in ('', '.', '..') for part in name.rstrip('/').split('/'))):
        raise EpubError('EPUB contains an unsafe archive entry path.')
    if len(name) > 600:
        raise EpubError('EPUB contains an excessively long archive entry path.')
    return name


def _reference(base: str, href: str) -> tuple[str, str] | None:
    """Normalize an OPF/nav-relative URI *within* the EPUB container."""
    if not href or '\\' in href or '\x00' in href:
        return None
    try:
        ref = urlsplit(href)
        if ref.scheme or ref.netloc or ref.query:
            return None
        # A leading slash must not refer to host filesystem paths.
        decoded = unquote(ref.path)
        if not decoded or decoded.startswith('/') or '\\' in decoded or '\x00' in decoded:
            return None
        relative = posixpath.normpath(posixpath.join(posixpath.dirname(base), decoded))
        if relative in ('', '.', '..') or relative.startswith('../'):
            return None
        return relative, unquote(ref.fragment)
    except (TypeError, ValueError):
        return None


def _xml_file(book: zipfile.ZipFile, filename: str) -> ET.Element:
    try:
        info = book.getinfo(filename)
    except KeyError as exc:
        raise EpubError(f'Missing EPUB metadata: {filename}') from exc
    if info.file_size > MAX_XML_BYTES:
        raise EpubError('EPUB XML metadata is unexpectedly large.')
    if SafeET is None:
        raise EpubError('EPUB support requires python3-defusedxml. '
                        'Install it with: sudo apt install python3-defusedxml')
    try:
        data = book.read(info)
        # Accept normal XML declarations and standard EPUB DOCTYPEs. Never load
        # external resources, expand entities, or resolve referenced DTDs.
        return SafeET.fromstring(data, forbid_dtd=False,
                                 forbid_entities=True, forbid_external=True)
    except DefusedXmlException as exc:
        raise EpubError(f'Unsafe XML entity or external reference in EPUB metadata: '
                        f'{filename}') from exc
    except (ET.ParseError, RuntimeError, OSError, zipfile.BadZipFile) as exc:
        raise EpubError(f'Invalid EPUB metadata: {filename}') from exc


def _localname(tag: str) -> str:
    return tag.rpartition('}')[2]


def _elements(root: ET.Element, localname: str):
    return (node for node in root.iter() if _localname(node.tag) == localname)


def _text(element: ET.Element) -> str:
    return ' '.join(''.join(element.itertext()).split()).strip()


def _get_package_path(book: zipfile.ZipFile) -> str:
    root = _xml_file(book, 'META-INF/container.xml')
    for element in _elements(root, 'rootfile'):
        candidate = element.attrib.get('full-path', '')
        try:
            candidate = _checked_name(candidate)
        except EpubError:
            continue
        if candidate.lower().endswith('.opf'):
            return candidate
    raise EpubError('No OPF package document found in this EPUB.')


def _epub3_toc(book: zipfile.ZipFile, nav_name: str) -> list[EpubTocItem]:
    xml = _xml_file(book, nav_name)
    for nav in _elements(xml, 'nav'):
        kind = ' '.join(value for key, value in nav.attrib.items()
                        if _localname(key) == 'type' or key == 'role')
        if 'toc' not in kind.split() and 'doc-toc' not in kind.split():
            continue
        entries: list[EpubTocItem] = []

        def visit(node: ET.Element, depth=0):
            if len(entries) >= MAX_MEMBERS:
                return
            for child in node:
                tag = _localname(child.tag)
                if tag in ('ol', 'ul'):
                    visit(child, depth)
                elif tag == 'li':
                    anchor = next((x for x in child if _localname(x.tag) == 'a'), None)
                    if anchor is not None:
                        ref = _reference(nav_name, anchor.attrib.get('href', ''))
                        if ref and Path(ref[0]).suffix.lower() in PAGE_EXTENSIONS:
                            entries.append(EpubTocItem(_text(anchor) or 'Chapter', *ref, level=depth))
                    for sub in child:
                        if _localname(sub.tag) in ('ol', 'ul'):
                            visit(sub, depth + 1)

        visit(nav)
        if entries:
            return entries
    return []


def _epub2_toc(book: zipfile.ZipFile, ncx_name: str) -> list[EpubTocItem]:
    xml = _xml_file(book, ncx_name)
    results: list[EpubTocItem] = []

    def visit(node: ET.Element, depth=0):
        for point in node:
            if _localname(point.tag) != 'navPoint':
                continue
            if len(results) >= MAX_MEMBERS:
                return
            label = next((_text(n) for n in point.iter() if _localname(n.tag) == 'navLabel'), 'Chapter')
            content = next((n for n in point if _localname(n.tag) == 'content'), None)
            if content is not None:
                ref = _reference(ncx_name, content.attrib.get('src', ''))
                if ref and Path(ref[0]).suffix.lower() in PAGE_EXTENSIONS:
                    results.append(EpubTocItem(label or 'Chapter', *ref, level=depth))
            visit(point, depth + 1)

    for navmap in _elements(xml, 'navMap'):
        visit(navmap)
        break
    return results


def _read_manifest(book: zipfile.ZipFile):
    package_name = _get_package_path(book)
    package = _xml_file(book, package_name)
    title = next((_text(node) for node in _elements(package, 'title') if _text(node)), '')
    manifest: dict[str, tuple[str, str, set[str]]] = {}
    for item in _elements(package, 'item'):
        item_id = item.attrib.get('id', '')
        target = _reference(package_name, item.attrib.get('href', ''))
        if item_id and target:
            manifest[item_id] = (target[0], item.attrib.get('media-type', ''),
                                 set(item.attrib.get('properties', '').split()))
    spine = next(_elements(package, 'spine'), None)
    if spine is None:
        raise EpubError('This EPUB has no reading order (spine).')
    chapters: list[EpubChapter] = []
    for itemref in spine:
        if _localname(itemref.tag) != 'itemref':
            continue
        item = manifest.get(itemref.attrib.get('idref', ''))
        if item and Path(item[0]).suffix.lower() in PAGE_EXTENSIONS:
            chapters.append(EpubChapter(Path(item[0]).stem.replace('_', ' '), item[0]))
    if not chapters:
        raise EpubError('This EPUB contains no readable XHTML/HTML chapters.')
    toc: list[EpubTocItem] = []
    for path, _mime, props in manifest.values():
        if 'nav' in props:
            toc = _epub3_toc(book, path)
            if toc:
                break
    if not toc and spine.attrib.get('toc') in manifest:
        path = manifest[spine.attrib['toc']][0]
        toc = _epub2_toc(book, path)
    if not toc:
        toc = [EpubTocItem(ch.label, ch.archive_path) for ch in chapters]
    return title, chapters, toc


def _validate_source(path: str, allowed_root: str | None) -> Path:
    raw = Path(path)
    if raw.is_symlink():
        raise EpubError('Symbolic-link documents cannot be opened.')
    try:
        source = raw.resolve(strict=True)
        if not source.is_file() or source.suffix.lower() != '.epub':
            raise EpubError('This is not a readable EPUB file.')
        if allowed_root:
            root = Path(allowed_root).resolve(strict=True)
            if not source.is_relative_to(root):
                raise EpubError('EPUB is outside the selected disc or folder.')
        if source.stat().st_size > MAX_EPUB_BYTES:
            raise EpubError('EPUB exceeds the 256 MiB opening limit for 4 GB computers.')
        return source
    except OSError as exc:
        raise EpubError(f'Cannot read the EPUB. Was the disc removed? ({exc})') from exc


def prepare_epub(path: str, allowed_root: str | None = None,
                 cancelled: threading.Event | None = None) -> EpubPreview:
    """Read the package and unpack *renderable* assets into RAM, cancellably.

    The caller owns `preview.temp_directory`. No file in the EPUB is executed.
    """
    cancel = cancelled or threading.Event()
    _check_cancelled(cancel)
    source = _validate_source(path, allowed_root)
    try:
        parent = ram_temp_root()
    except Exception as exc:
        raise EpubError(str(exc)) from exc
    destination = Path(tempfile.mkdtemp(prefix=EPUB_PREFIX, dir=parent))
    succeeded = False
    try:
        with zipfile.ZipFile(source, 'r') as archive:
            infos = archive.infolist()
            if len(infos) > MAX_MEMBERS:
                raise EpubError('EPUB contains too many archive entries for this computer.')
            names = set()
            renderable = []
            total_bytes = 0
            for info in infos:
                _check_cancelled(cancel)
                name = _checked_name(info.filename)
                if name in names:
                    raise EpubError('EPUB contains duplicate archive entries.')
                names.add(name)
                if info.flag_bits & 1:
                    raise EpubError('Encrypted EPUB files are not supported.')
                file_mode = (info.external_attr >> 16) & 0xffff
                if stat.S_IFMT(file_mode) == stat.S_IFLNK:
                    raise EpubError('EPUB contains a symbolic link, which is not allowed.')
                if info.is_dir() or Path(name).suffix.lower() not in RENDER_EXTENSIONS:
                    continue
                if info.file_size > MAX_MEMBER_BYTES:
                    raise EpubError('An EPUB resource exceeds the 64 MiB safety limit.')
                total_bytes += info.file_size
                if total_bytes > MAX_UNPACKED_BYTES:
                    raise EpubError('EPUB would use more than 384 MiB of temporary RAM.')
                renderable.append(info)
            if 'META-INF/encryption.xml' in names:
                raise EpubError('Encrypted or obfuscated EPUB content is not supported.')
            display_title, chapters, toc = _read_manifest(archive)
            renderable_names = {info.filename for info in renderable}
            if any(ch.archive_path not in renderable_names for ch in chapters):
                raise EpubError('EPUB reading order references a missing or unsupported chapter.')
            for info in renderable:
                _check_cancelled(cancel)
                target = destination.joinpath(*info.filename.split('/'))
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with archive.open(info, 'r') as inp, target.open('xb') as out:
                    while True:
                        _check_cancelled(cancel)
                        chunk = inp.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        out.write(chunk)
            _check_cancelled(cancel)
        succeeded = True
        return EpubPreview(str(destination), display_title or source.stem,
                           tuple(chapters), tuple(t for t in toc if t.archive_path in renderable_names))
    except EpubCancelled:
        raise
    except EpubError:
        raise
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, EOFError) as exc:
        raise EpubError(f'Could not open the EPUB: {exc}') from exc
    finally:
        if not succeeded:
            cleanup_epub(str(destination))
