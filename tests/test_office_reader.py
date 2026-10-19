"""Optional GUI integration test for the Office -> Qt PDF path."""
import os
import time
import unittest
from pathlib import Path

try:
    from PySide6.QtWidgets import QApplication
    from main import MainWindow
    from catalog import Document
    HAS_QT = True
except ImportError:
    HAS_QT = False

HAS_DISPLAY = bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')
                   or os.environ.get('QT_QPA_PLATFORM') == 'offscreen')


@unittest.skipUnless(HAS_QT and HAS_DISPLAY, 'Qt and graphical session required')
class OfficeReaderGuiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_office_opens_in_existing_pdf_reader(self):
        root = Path(__file__).parent / 'fixtures' / 'office_library'
        window = MainWindow()
        window.root = str(root.resolve())
        window.root_kind = 'folder'
        source = root / 'Office-Demo.docx'
        window._open_office(Document(str(source.resolve()), source.name, '.docx'))
        end = time.monotonic() + 20
        while window.office_requested_book is not None and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.03)
        self.assertIsNotNone(window.pdf_reader)
        self.assertEqual(window.page_stack.currentWidget(), window.pdf_reader)
        self.assertEqual(window.pdf_reader.filename.text(), 'Office-Demo.docx')
        ramdir = window.office_temp_directory
        self.assertIsNotNone(ramdir)
        window.return_to_shelf()
        self.assertFalse(Path(ramdir).exists())
        while window.office_thread is not None and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.03)
        window.close()


if __name__ == '__main__':
    unittest.main()
