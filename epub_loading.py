"""Background EPUB extraction without starting Qt WebEngine until needed."""
import threading

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QLabel, QHBoxLayout, QProgressBar, QPushButton, QVBoxLayout, QWidget

from epub_archive import EpubCancelled, EpubError, prepare_epub


class EpubLoadingWorker(QObject):
    prepared = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, source: str, root: str):
        super().__init__()
        self.source = source
        self.root = root
        self.cancel_event = threading.Event()

    @Slot()
    def run(self):
        try:
            preview = prepare_epub(self.source, self.root, self.cancel_event)
            self.prepared.emit(preview)
        except EpubCancelled:
            self.failed.emit('EPUB opening cancelled.')
        except (EpubError, OSError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit('Unable to prepare EPUB: ' + str(exc))
        finally:
            self.finished.emit()


class EpubLoadingView(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        back = QPushButton('← Back to bookshelf')
        back.clicked.connect(self.back_requested.emit)
        top.addWidget(back)
        top.addStretch()
        layout.addLayout(top)
        layout.addStretch()
        self.title = QLabel('Preparing EPUB…')
        self.title.setObjectName('readerFilename')
        self.title.setWordWrap(True)
        layout.addWidget(self.title)
        self.message = QLabel('Extracting the selected book into RAM to display chapters and local images.')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        busy = QProgressBar()
        busy.setRange(0, 0)
        layout.addWidget(busy)
        layout.addStretch()

    def show_document(self, filename: str):
        self.title.setText('Opening ' + filename)
