"""Nonblocking Office conversion workflow for the Qt bookshelf."""
import threading

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QProgressBar,
                               QPushButton, QVBoxLayout, QWidget)

from office_conversion import ConversionCancelled, ConversionError, convert_office_document


class OfficeConversionWorker(QObject):
    converted = Signal(str, str)  # preview PDF path, temporary RAM directory
    failed = Signal(str)
    finished = Signal()

    def __init__(self, document_path: str, root: str):
        super().__init__()
        self.document_path = document_path
        self.root = root
        self.cancel_event = threading.Event()

    @Slot()
    def run(self):
        try:
            result = convert_office_document(self.document_path, self.root, self.cancel_event)
            self.converted.emit(result.pdf_path, result.temp_directory)
        except ConversionCancelled:
            self.failed.emit('Conversion cancelled.')
        except (ConversionError, OSError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            # Keep broken documents from terminating the whole application.
            self.failed.emit('Unexpected LibreOffice conversion error: ' + str(exc))
        finally:
            self.finished.emit()


class OfficeLoadingView(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        self.back_button = QPushButton('← Back to bookshelf')
        self.back_button.clicked.connect(self.back_requested.emit)
        row.addWidget(self.back_button)
        row.addStretch()
        root.addLayout(row)
        root.addStretch()
        self.title = QLabel('Preparing Office document…')
        self.title.setObjectName('readerFilename')
        self.title.setWordWrap(True)
        root.addWidget(self.title)
        self.message = QLabel('LibreOffice is converting this document to a PDF preview in RAM.\n'
                              'The original document is not changed.')
        self.message.setWordWrap(True)
        root.addWidget(self.message)
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)  # indeterminate; no fictional progress estimate
        root.addWidget(self.busy)
        root.addStretch()

    def show_document(self, filename):
        self.title.setText('Opening ' + filename)
        self.message.setText('Converting with LibreOffice Writer in the background…\n'
                             'The preview and conversion profile are stored temporarily in RAM.')
        self.busy.setRange(0, 0)
