"""Optional GUI smoke test: run in a proper Debian graphical environment."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@unittest.skipUnless(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'),
                     'EPUB Qt smoke test needs a graphical session')
class EpubReaderGuiTest(unittest.TestCase):
    def test_open_epub_and_chapter_buttons(self):
        try:
            from PySide6.QtWidgets import QApplication
            from epub_archive import prepare_epub
            from epub_reader import EpubReader
        except ImportError as exc:
            self.skipTest(f'Qt WebEngine/PySide6 unavailable: {exc}')
        app = QApplication.instance() or QApplication(['discshelf-test'])
        fixture = Path(__file__).parent / 'fixtures' / 'epub_library' / 'Offline-EPUB3.epub'
        preview = prepare_epub(str(fixture), str(fixture.parent))
        widget = EpubReader()
        try:
            opened, error = widget.open_preview(preview, fixture.name)
            self.assertTrue(opened, error)
            self.assertEqual(len(widget.preview.chapters), 2)
            self.assertEqual(widget.toc_view.topLevelItemCount(), 3)
            self.assertFalse(widget.previous.isEnabled())
            self.assertTrue(widget.next.isEnabled())
            widget._change_chapter(1)
            self.assertTrue(widget.previous.isEnabled())
            self.assertFalse(widget.next.isEnabled())
        finally:
            widget.close_file()
            widget.deleteLater()
            app.processEvents()
        self.assertFalse(Path(preview.temp_directory).exists())


if __name__ == '__main__':
    unittest.main()
