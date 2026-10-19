"""On-demand LibreOffice Writer to PDF conversion in a Linux tmpfs.

No documents are indexed/read until opened; only the requested Office source is
passed to LibreOffice. No output or LibreOffice user profile goes to home or /tmp.
This module does not import Qt, so it can be tested independently.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

OFFICE_EXTENSIONS = frozenset({'.doc', '.docx', '.rtf', '.odt'})
MAX_SOURCE_BYTES = 128 * 1024 * 1024
MAX_PDF_BYTES = 256 * 1024 * 1024
TIMEOUT_SECONDS = 180
PREFIX = 'discshelf-office-'


class ConversionError(Exception):
    """Expected, user-presentable failure to create an Office preview."""


class ConversionCancelled(ConversionError):
    pass


@dataclass(frozen=True)
class OfficePreview:
    pdf_path: str
    temp_directory: str


def _mount_type(path: Path) -> str | None:
    """Find the longest Linux mount covering path (including tmpfs subdirs)."""
    try:
        target = path.resolve(strict=True)
        best = (0, None)
        for line in Path('/proc/self/mountinfo').read_text().splitlines():
            before, after = line.split(' - ', 1)
            fields = before.split()
            fstype = after.split()[0]
            # mountinfo uses octal escapes for whitespace/backslashes.
            name = fields[4]
            for escaped, literal in ((r'\040', ' '), (r'\011', '\t'), (r'\012', '\n'), (r'\134', '\\')):
                name = name.replace(escaped, literal)
            mp = Path(name)
            if (target == mp or mp in target.parents) and len(name) > best[0]:
                best = (len(name), fstype)
        return best[1]
    except (OSError, ValueError, IndexError):
        return None


def ram_temp_root() -> Path:
    """Require an actual tmpfs; refuse to fall back to persistent /tmp."""
    candidates = []
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if runtime:
        candidates.append(Path(runtime))
    candidates.append(Path('/dev/shm'))
    for candidate in candidates:
        try:
            directory = candidate.resolve(strict=True)
            if not directory.is_dir() or not os.access(directory, os.W_OK | os.X_OK):
                continue
            if _mount_type(directory) != 'tmpfs':
                continue
            return directory
        except OSError:
            continue
    raise ConversionError('No writable RAM-backed tmpfs found (usually /run/user/$UID or /dev/shm). '
                          'Conversion has been cancelled rather than writing a document preview to disk.')


def _validate_source(path: str, allowed_root: str | None) -> Path:
    source = Path(path)
    if source.is_symlink():
        raise ConversionError('Symbolic-link documents cannot be opened from the disc.')
    try:
        resolved = source.resolve(strict=True)
        if not resolved.is_file():
            raise ConversionError('This document is not a readable file.')
        if allowed_root:
            root = Path(allowed_root).resolve(strict=True)
            if resolved != root and root not in resolved.parents:
                raise ConversionError('The selected document is outside the current disc or folder.')
        if resolved.suffix.lower() not in OFFICE_EXTENSIONS:
            raise ConversionError('This document is not a supported Office format.')
        size = resolved.stat().st_size
        if size > MAX_SOURCE_BYTES:
            raise ConversionError('This Office document exceeds the 128 MiB preview safety limit '
                                  'for computers with 4 GB of RAM.')
        return resolved
    except OSError as exc:
        raise ConversionError(f'Cannot access the original document. Was the disc removed? ({exc})') from exc


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    # start_new_session makes it safe to stop LibreOffice and its child processes.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        process.terminate()
    try:
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()
        process.communicate()


def cleanup_preview(temp_directory: str | None) -> None:
    """Remove only our own ram-backed temporary directory, never a source."""
    if not temp_directory:
        return
    p = Path(temp_directory)
    try:
        if (not p.is_symlink() and p.name.startswith(PREFIX)
                and _mount_type(p) == 'tmpfs'):
            shutil.rmtree(p)
    except OSError:
        pass


def convert_office_document(path: str, allowed_root: str | None,
                            cancelled: threading.Event | None = None,
                            timeout_seconds: float = TIMEOUT_SECONDS,
                            binary: str | None = None) -> OfficePreview:
    """Run one isolated, cancellable Writer PDF conversion.

    Only the returned temp directory is owned by the caller. On every failure
    or cancellation it is cleaned here. The caller must close Qt PDF before
    calling cleanup_preview() after successful conversion.
    """
    if cancelled is None:
        cancelled = threading.Event()
    if cancelled.is_set():
        raise ConversionCancelled('Office conversion cancelled.')
    source = _validate_source(path, allowed_root)
    converter = binary or shutil.which('libreoffice') or shutil.which('soffice')
    if not converter:
        raise ConversionError('LibreOffice Writer is not installed. Run:\n\n'
                              'sudo apt install libreoffice-writer')
    parent = ram_temp_root()
    work_dir = Path(tempfile.mkdtemp(prefix=PREFIX, dir=parent))
    process = None
    success = False
    try:
        out = work_dir / 'out'
        out.mkdir(mode=0o700)
        for name in ('home', 'cache', 'config', 'data', 'tmp', 'profile'):
            (work_dir / name).mkdir(mode=0o700)
        # Isolate converter profile, configuration, caches, and temporary files
        # from the user's home and system /tmp. No source is copied to disk.
        env = os.environ.copy()
        env.update({
            'HOME': str(work_dir / 'home'),
            'XDG_CACHE_HOME': str(work_dir / 'cache'),
            'XDG_CONFIG_HOME': str(work_dir / 'config'),
            'XDG_DATA_HOME': str(work_dir / 'data'),
            'TMPDIR': str(work_dir / 'tmp'),
            'TMP': str(work_dir / 'tmp'),
            'TEMP': str(work_dir / 'tmp'),
            'SAL_DISABLE_OPENCL': '1',
        })
        command = [
            converter,
            '-env:UserInstallation=' + (work_dir / 'profile').as_uri(),
            '--headless', '--nologo', '--nodefault', '--norestore',
            '--convert-to', 'pdf:writer_pdf_Export',
            '--outdir', str(out), str(source)
        ]
        if cancelled.is_set():
            raise ConversionCancelled('Office conversion cancelled.')
        try:
            process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=env, cwd=str(work_dir),
                start_new_session=True,
            )
        except OSError as exc:
            raise ConversionError(f'Could not start LibreOffice: {exc}') from exc
        deadline = time.monotonic() + timeout_seconds
        while True:
            if cancelled.is_set():
                raise ConversionCancelled('Office conversion cancelled.')
            if time.monotonic() >= deadline:
                raise ConversionError('LibreOffice took too long to convert this document. '
                                      'The conversion was stopped to protect system resources.')
            try:
                stdout, stderr = process.communicate(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode != 0:
            details = (stderr or stdout or b'').decode('utf-8', 'replace').strip()[-700:]
            raise ConversionError('LibreOffice could not convert this file. '
                                  + (details or 'It may be damaged, encrypted or unsupported.'))
        pdfs = [p for p in out.iterdir() if p.is_file() and p.suffix.lower() == '.pdf']
        if len(pdfs) != 1:
            raise ConversionError('LibreOffice did not produce a PDF. '
                                  'The document may be corrupt, password-protected or unsupported.')
        pdf = pdfs[0]
        if pdf.stat().st_size > MAX_PDF_BYTES:
            raise ConversionError('Converted document exceeds the 256 MiB preview safety limit.')
        with pdf.open('rb') as stream:
            if stream.read(5) != b'%PDF-':
                raise ConversionError('LibreOffice returned an invalid PDF preview.')
        if cancelled.is_set():
            raise ConversionCancelled('Office conversion cancelled.')
        success = True
        return OfficePreview(pdf_path=str(pdf), temp_directory=str(work_dir))
    finally:
        if process is not None and process.poll() is None:
            _stop_process(process)
        if not success:
            cleanup_preview(str(work_dir))
