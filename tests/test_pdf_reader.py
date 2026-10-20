"""Optional GUI smoke test: runs only with Qt PDF and a graphical session."""
import os
from pathlib import Path
import unittest

try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtPdf import QPdfDocument
    from pdf_reader import PdfReader, PageNumberSpin
    HAS_QT = True
except ImportError:
    HAS_QT = False

HAS_DISPLAY = bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')
                   or os.environ.get('QT_QPA_PLATFORM') == 'offscreen')


@unittest.skipUnless(HAS_QT and HAS_DISPLAY, 'Qt PDF and a graphical session required')
class PdfReaderSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_editable_page_selector_with_reversed_arrows(self):
        selector = PageNumberSpin()
        selector.setRange(1, 18)
        selector.setValue(3)
        self.assertTrue(selector.decrease_button.isEnabled())
        self.assertTrue(selector.increase_button.isEnabled())

        selector.decrease_button.click()  # ▲ decreases
        self.assertEqual(selector.value(), 2)
        selector.increase_button.click()  # ▼ increases
        self.assertEqual(selector.value(), 3)

        selector.stepBy(1)  # Keyboard Up / wheel up decreases
        self.assertEqual(selector.value(), 2)
        selector.stepBy(-1)  # Keyboard Down / wheel down increases
        self.assertEqual(selector.value(), 3)

        selector.lineEdit().setText('12')  # Type page directly
        selector.interpretText()  # Same validation used on Enter
        self.assertEqual(selector.value(), 12)

        selector.setValue(1)
        self.assertFalse(selector.decrease_button.isEnabled())
        self.assertTrue(selector.increase_button.isEnabled())
        selector.setValue(18)
        self.assertTrue(selector.decrease_button.isEnabled())
        self.assertFalse(selector.increase_button.isEnabled())
        selector.deleteLater()

    def test_local_three_page_pdf(self):
        source = Path(__file__).parent / 'fixtures' / 'sample.pdf'
        reader = PdfReader()
        self.assertTrue(reader.open_file(str(source)))
        import time
        deadline = time.monotonic() + 3
        while reader.document.status() == QPdfDocument.Status.Loading and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.02)
        self.assertEqual(reader.document.status(), QPdfDocument.Status.Ready)
        self.assertEqual(reader.document.pageCount(), 3)
        self.assertIn('DiscShelf', reader.document.getAllText(0).text())
        reader._slider_zoom_changed(150)
        self.assertEqual(reader.zoom_slider.value(), 150)
        self.assertAlmostEqual(reader.view.zoomFactor(), 1.5, places=2)
        reader._fit_to_width()
        self.assertEqual(reader.view.zoomMode(), reader.view.ZoomMode.FitToWidth)
        reader._go_to_page(2)
        self.app.processEvents()
        self.assertEqual(reader.navigator.currentPage(), 1)
        reader.close_file()
        self.assertIsNone(reader.source_path)
        reader.deleteLater()


if __name__ == '__main__':
    unittest.main()
