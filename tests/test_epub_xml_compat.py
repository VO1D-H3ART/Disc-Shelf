"""Regression tests for valid EPUB XML declarations, DTDs and malicious entities."""
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from epub_archive import EpubError, cleanup_epub, prepare_epub
from office_conversion import ram_temp_root

FIXTURE = Path(__file__).parent / 'fixtures' / 'epub_library'

# A common EPUB2 NCX DOCTYPE. The external DTD must never be downloaded.
NCX_DOCTYPE = (b'<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" '
               b'"http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">')
XHTML_DOCTYPE = (b'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" '
                 b'"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">')


def custom_book(original: Path, dest: Path, edits: dict[str, bytes]):
    with zipfile.ZipFile(original) as z_in, zipfile.ZipFile(dest, 'w') as z_out:
        for info in z_in.infolist():
            data = edits.get(info.filename, z_in.read(info.filename))
            z_out.writestr(info, data)


class EpubXMLCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpfs = ram_temp_root()

    def make_book(self, directory: Path, version: int, edits: dict[str, bytes]):
        source = FIXTURE / f'Offline-EPUB{version}.epub'
        dest = directory / 'modified.epub'
        custom_book(source, dest, edits)
        return dest

    def test_epub2_ncx_public_doctype_is_accepted(self):
        with tempfile.TemporaryDirectory(dir=self.tmpfs) as td:
            directory = Path(td)
            with zipfile.ZipFile(FIXTURE / 'Offline-EPUB2.epub') as z:
                ncx = z.read('OEBPS/toc.ncx')
            ncx = ncx.replace(b'<ncx ', NCX_DOCTYPE + b'\n<ncx ', 1)
            source = self.make_book(directory, 2, {'OEBPS/toc.ncx': ncx})
            preview = prepare_epub(str(source), td)
            try:
                self.assertEqual(preview.display_title, 'DiscShelf EPUB 2 Example')
                self.assertEqual([item.label for item in preview.toc],
                                 ['Welcome', 'The details', 'Styling and Navigation'])
            finally:
                cleanup_epub(preview.temp_directory)
            self.assertFalse(Path(preview.temp_directory).exists())

    def test_epub3_nav_xhtml_doctype_is_accepted(self):
        with tempfile.TemporaryDirectory(dir=self.tmpfs) as td:
            directory = Path(td)
            with zipfile.ZipFile(FIXTURE / 'Offline-EPUB3.epub') as z:
                nav = z.read('OEBPS/nav.xhtml')
            nav = nav.replace(b'<html ', XHTML_DOCTYPE + b'\n<html ', 1)
            source = self.make_book(directory, 3, {'OEBPS/nav.xhtml': nav})
            preview = prepare_epub(str(source), td)
            try:
                self.assertEqual(len(preview.toc), 3)
                self.assertEqual(len(preview.chapters), 2)
            finally:
                cleanup_epub(preview.temp_directory)

    def test_epub_opf_can_contain_doctype_and_xml_comment(self):
        with tempfile.TemporaryDirectory(dir=self.tmpfs) as td:
            directory = Path(td)
            with zipfile.ZipFile(FIXTURE / 'Offline-EPUB3.epub') as z:
                package = z.read('OEBPS/content.opf')
            package = package.replace(b'<package ',
                    b'<!-- a comment mentioning <!ENTITY, no actual declaration -->\n'
                    b'<!DOCTYPE package>\n<package ', 1)
            source = self.make_book(directory, 3, {'OEBPS/content.opf': package})
            preview = prepare_epub(str(source), td)
            try:
                self.assertEqual(preview.display_title, 'DiscShelf EPUB 3 Example')
            finally:
                cleanup_epub(preview.temp_directory)

    def test_reject_internal_entity_expansion(self):
        with tempfile.TemporaryDirectory(dir=self.tmpfs) as td:
            directory = Path(td)
            with zipfile.ZipFile(FIXTURE / 'Offline-EPUB3.epub') as z:
                package = z.read('OEBPS/content.opf')
            package = package.replace(b'<package ',
                    b'<!DOCTYPE package [<!ENTITY injected "unsafe">]>\n<package ', 1)
            source = self.make_book(directory, 3, {'OEBPS/content.opf': package})
            with self.assertRaisesRegex(EpubError, 'Unsafe XML entity'):
                prepare_epub(str(source), td)

    def test_reject_external_entity(self):
        with tempfile.TemporaryDirectory(dir=self.tmpfs) as td:
            directory = Path(td)
            with zipfile.ZipFile(FIXTURE / 'Offline-EPUB3.epub') as z:
                package = z.read('OEBPS/content.opf')
            package = package.replace(b'<package ',
                    b'<!DOCTYPE package [<!ENTITY injected SYSTEM "file:///etc/passwd">]>\n<package ', 1)
            source = self.make_book(directory, 3, {'OEBPS/content.opf': package})
            with self.assertRaisesRegex(EpubError, 'Unsafe XML entity'):
                prepare_epub(str(source), td)

    def test_missing_dependency_is_epub_only_error(self):
        with tempfile.TemporaryDirectory(dir=self.tmpfs) as td:
            with patch('epub_archive.SafeET', None):
                with self.assertRaisesRegex(EpubError, 'python3-defusedxml'):
                    prepare_epub(str(FIXTURE / 'Offline-EPUB3.epub'), str(FIXTURE))


if __name__ == '__main__':
    unittest.main()
