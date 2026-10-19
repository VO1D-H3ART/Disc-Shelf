import tempfile
import unittest
from pathlib import Path

from catalog import SUPPORTED_EXTENSIONS, document_from_path
from disc_detection import mounted_optical_discs


class CatalogTests(unittest.TestCase):
    def test_exactly_ten_formats(self):
        self.assertEqual(len(SUPPORTED_EXTENSIONS), 10)

    def test_case_insensitive(self):
        doc = document_from_path('/disc/Research/MANUAL.PDF')
        self.assertEqual(doc.extension, '.pdf')
        self.assertEqual(doc.title, 'MANUAL')

    def test_unsupported_files_ignored(self):
        self.assertIsNone(document_from_path('/disc/photo.jpg'))
        self.assertIsNone(document_from_path('/disc/program.exe'))

    def test_all_formats(self):
        for ext in SUPPORTED_EXTENSIONS:
            with self.subTest(ext=ext):
                self.assertIsNotNone(document_from_path('/disc/readme' + ext))

    def test_mount_check_safe_without_disc(self):
        self.assertIsInstance(mounted_optical_discs(), list)


if __name__ == '__main__':
    unittest.main()
