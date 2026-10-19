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



class SpineColorTests(unittest.TestCase):
    def test_all_supported_extensions_have_colors(self):
        from book_colors import SPINE_COLORS
        self.assertEqual(set(SPINE_COLORS), SUPPORTED_EXTENSIONS)

    def test_requested_color_families(self):
        from book_colors import spine_color
        self.assertEqual(spine_color('.doc'), spine_color('.docx'))
        self.assertEqual(spine_color('.PDF'), spine_color('.pdf'))
        self.assertEqual(spine_color('.HTM'), spine_color('.html'))
        red = spine_color('.pdf')
        blue = spine_color('.docx')
        purple = spine_color('.md')
        self.assertNotEqual(red, blue)
        self.assertNotEqual(red, purple)
        self.assertNotEqual(blue, purple)


if __name__ == '__main__':
    unittest.main()
