"""Pure decoding tests and optional Qt Markdown/TXT view smoke test."""
import os
import importlib.util
import unittest
from pathlib import Path

from text_format import decode_text, MAX_TEXT_BYTES

class TextDecodingTests(unittest.TestCase):
    def test_utf8_bom(self):
        self.assertEqual(decode_text(b'\xef\xbb\xbfhello'), 'hello')

    def test_utf16(self):
        self.assertEqual(decode_text('café'.encode('utf-16')), 'café')

    def test_cp1252(self):
        self.assertEqual(decode_text(b'Caf\xe9'), 'Café')

    def test_size_threshold(self):
        self.assertEqual(MAX_TEXT_BYTES, 16 * 1024 * 1024)


HAS_DISPLAY = bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')
                   or os.environ.get('QT_QPA_PLATFORM') == 'offscreen')


@unittest.skipUnless(HAS_DISPLAY and importlib.util.find_spec('PySide6'), 'Qt GUI needed')
class TextReaderSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_markdown_and_txt(self):
        try:
            from text_reader import TextReader
        except ImportError:
            self.skipTest('PySide6 Qt Widgets not installed')
        fixture = Path(__file__).parent / 'fixtures'
        reader = TextReader()
        ok, error = reader.open_file(str(fixture / 'sample.md'), str(fixture))
        self.assertTrue(ok, error)
        self.assertIn('Sample Markdown', reader.view.toPlainText())
        ok, error = reader.open_file(str(fixture / 'sample.txt'), str(fixture))
        self.assertTrue(ok, error)
        self.assertEqual(reader.view.toPlainText().strip(), 'DiscShelf text reader works.')
        reader.close_file()
        reader.deleteLater()


if __name__ == '__main__':
    unittest.main()
