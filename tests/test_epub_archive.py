"""Tests for real EPUB2/3 book parsing, RAM extraction and archive defenses."""
import os
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from epub_archive import (EpubCancelled, EpubError, cleanup_epub, prepare_epub,
                          _checked_name, _reference)
from office_conversion import _mount_type, ram_temp_root

FIXTURE = Path(__file__).parent / 'fixtures' / 'epub_library'


class EpubArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Existing Office conversion has the same tmpfs dependency.
        cls.tmpfs = ram_temp_root()

    def test_epub3_opens_two_chapters_with_styling_and_toc(self):
        source = FIXTURE / 'Offline-EPUB3.epub'
        original = source.read_bytes()
        result = prepare_epub(str(source), str(FIXTURE))
        try:
            self.assertEqual(result.display_title, 'DiscShelf EPUB 3 Example')
            self.assertEqual(len(result.chapters), 2)
            self.assertEqual(result.chapters[0].archive_path, 'OEBPS/chapter1.xhtml')
            self.assertEqual([t.label for t in result.toc],
                             ['Welcome', 'The details', 'Styling and Navigation'])
            self.assertEqual([t.level for t in result.toc], [0, 1, 0])
            self.assertTrue((Path(result.temp_directory) / 'OEBPS/styles/book.css').exists())
            self.assertTrue((Path(result.temp_directory) / 'OEBPS/art/leaf.svg').exists())
            self.assertFalse((Path(result.temp_directory) / 'OEBPS/content.opf').exists())
            self.assertEqual(_mount_type(Path(result.temp_directory)), 'tmpfs')
        finally:
            cleanup_epub(result.temp_directory)
        self.assertFalse(Path(result.temp_directory).exists())
        self.assertEqual(source.read_bytes(), original)

    def test_epub2_ncx_toc(self):
        result = prepare_epub(str(FIXTURE / 'Offline-EPUB2.epub'), str(FIXTURE))
        try:
            self.assertEqual(result.display_title, 'DiscShelf EPUB 2 Example')
            self.assertEqual(len(result.chapters), 2)
            self.assertEqual([t.label for t in result.toc],
                             ['Welcome', 'The details', 'Styling and Navigation'])
        finally:
            cleanup_epub(result.temp_directory)

    def test_cancelled_before_opening(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(EpubCancelled):
            prepare_epub(str(FIXTURE / 'Offline-EPUB3.epub'), str(FIXTURE), cancel)

    def test_reject_outside_selected_root(self):
        with self.assertRaisesRegex(EpubError, 'outside'):
            prepare_epub(str(FIXTURE / 'Offline-EPUB3.epub'), '/dev/shm')

    def test_path_resolution(self):
        self.assertEqual(_reference('OPS/nav/toc.xhtml', '../chapter.xhtml#hello'),
                         ('OPS/chapter.xhtml', 'hello'))
        self.assertIsNone(_reference('OPS/nav.xhtml', '../../../etc/passwd'))
        self.assertIsNone(_reference('OPS/nav.xhtml', 'https://example.com/other.xhtml'))
        self.assertIsNone(_reference('OPS/nav.xhtml', '/etc/passwd'))
        self.assertIsNone(_reference('OPS/nav.xhtml', '%2e%2e/%2e%2e/secret'))

    def test_zip_member_path_safety(self):
        for path in ('../evil.xhtml', '/absolute.xhtml', 'OPS/../evil.xhtml',
                     'OPS\\bad.xhtml', 'OPS//bad.xhtml', './bad.xhtml'):
            with self.assertRaises(EpubError):
                _checked_name(path)

    def test_reject_zip_slip_and_do_not_write_a_file(self):
        with tempfile.TemporaryDirectory(dir=self.tmpfs) as temp:
            source = Path(temp) / 'bad.epub'
            with zipfile.ZipFile(source, 'w') as z:
                z.writestr('../outside.xhtml', 'TEST')
            with self.assertRaisesRegex(EpubError, 'unsafe'):
                prepare_epub(str(source), temp)
            self.assertFalse((Path(temp).parent / 'outside.xhtml').exists())

    def test_reject_encryption_and_cleanup(self):
        with tempfile.TemporaryDirectory(dir=self.tmpfs) as temp:
            source = Path(temp) / 'encrypted.epub'
            fixture = FIXTURE / 'Offline-EPUB3.epub'
            with zipfile.ZipFile(fixture) as inp, zipfile.ZipFile(source, 'w') as out:
                for name in inp.namelist():
                    out.writestr(name, inp.read(name))
                out.writestr('META-INF/encryption.xml', 'DRM')
            with self.assertRaisesRegex(EpubError, 'Encrypted'):
                prepare_epub(str(source), temp)

    def test_cleanup_does_not_delete_arbitrary_directories(self):
        with tempfile.TemporaryDirectory(dir=self.tmpfs) as temp:
            keeper = Path(temp) / 'something_else'
            keeper.mkdir()
            (keeper / 'safe.txt').write_text('do not remove')
            cleanup_epub(str(keeper))
            self.assertTrue((keeper / 'safe.txt').exists())


if __name__ == '__main__':
    unittest.main()
