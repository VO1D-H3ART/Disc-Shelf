"""Read-only Markdown and plain-text readers; native Qt Widgets only.

No browser engine, Javascript, network operations or persistent storage.
The actual text is read from its source file only when the user opens it.
"""
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QFont, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

from text_format import MAX_TEXT_BYTES, decode_text
ALLOWED_IMAGE_TYPES = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'}


class DiscBoundTextDocument(QTextDocument):
    """Allow embedded Markdown images only from the selected disc/folder."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.allowed_root = None

    def loadResource(self, resource_type, url):
        if resource_type != QTextDocument.ResourceType.ImageResource:
            return None  # No external stylesheets or document-file loading.
        if self.allowed_root is None or url.scheme() not in ('', 'file'):
            return None
        try:
            base = Path(self.baseUrl().toLocalFile())
            path = Path(url.toLocalFile()) if url.isLocalFile() else base / url.path()
            resolved = path.resolve(strict=True)
            resolved.relative_to(self.allowed_root)
            if (not resolved.is_file() or resolved.suffix.lower() not in ALLOWED_IMAGE_TYPES
                    or resolved.stat().st_size > MAX_TEXT_BYTES):
                return None
        except (OSError, ValueError):
            return None
        # Load through Qt's local image loader; no network or outside-disc paths.
        return super().loadResource(resource_type, QUrl.fromLocalFile(str(resolved)))



class TextReader(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source_path = None
        self._is_markdown = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)
        bar = QHBoxLayout()
        back = QPushButton('← Back to bookshelf')
        back.clicked.connect(self.back_requested.emit)
        bar.addWidget(back)
        self.filename = QLabel('')
        self.filename.setObjectName('readerFilename')
        self.filename.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bar.addWidget(self.filename, 1)
        self.smaller = QPushButton('A−')
        self.larger = QPushButton('A+')
        self.smaller.setToolTip('Decrease reading font size')
        self.larger.setToolTip('Increase reading font size')
        bar.addWidget(self.smaller)
        bar.addWidget(self.larger)
        outer.addLayout(bar)

        self.view = QTextBrowser(self)
        self.view.setReadOnly(True)
        self.safe_doc = DiscBoundTextDocument(self.view)
        self.view.setDocument(self.safe_doc)
        self.view.setOpenLinks(False)
        self.view.setOpenExternalLinks(False)
        self.view.anchorClicked.connect(lambda _url: None)
        self.view.setStyleSheet('''
            QTextBrowser { background: #f6f0e5; color: #292522;
                border: 1px solid #c4a983; border-radius: 5px;
                selection-background-color: #79a8f3; selection-color: #191919;
                padding: 20px; }
        ''')
        self.view.setFont(QFont('DejaVu Sans', 12))
        outer.addWidget(self.view, 1)
        self.info = QLabel('Drag to select text. Ctrl+C copies the selection.')
        self.info.setObjectName('readerInfo')
        outer.addWidget(self.info)

        self.smaller.clicked.connect(lambda: self._adjust_font(-1))
        self.larger.clicked.connect(lambda: self._adjust_font(1))

    def _adjust_font(self, change):
        # QTextBrowser.zoomIn() increases type size without modifying the file.
        if change > 0:
            self.view.zoomIn(1)
        else:
            self.view.zoomOut(1)

    def open_file(self, path: str, allowed_root: str | None = None) -> tuple[bool, str]:
        self.close_file()
        source = Path(path)
        if source.suffix.lower() not in {'.md', '.txt'}:
            return False, 'Unsupported text document type.'
        try:
            # One extra byte distinguishes a 16 MiB document from larger files.
            with source.open('rb') as handle:
                blob = handle.read(MAX_TEXT_BYTES + 1)
            if len(blob) > MAX_TEXT_BYTES:
                return False, ('This text file is larger than 16 MiB. '
                               'To protect 4 GB systems, v4 does not open very large text files.')
            content = decode_text(blob)
        except (OSError, UnicodeError) as exc:
            return False, f'Unable to read document from disc: {exc}'

        self.source_path = str(source)
        self._is_markdown = source.suffix.lower() == '.md'
        self.filename.setText(source.name)
        self.filename.setToolTip(str(source))
        self.view.setSearchPaths([str(source.parent)])
        self.safe_doc.allowed_root = Path(allowed_root or source.parent).resolve()
        self.safe_doc.setBaseUrl(QUrl.fromLocalFile(str(source.parent) + '/'))
        if self._is_markdown:
            # QTextDocument uses Qt's built-in Markdown subset. No JavaScript.
            self.view.setMarkdown(content)
            self.view.document().setDefaultStyleSheet('''
                h1 {color:#3c315c;} h2 {color:#514078;}
                a {color:#385c92;} code {color:#4a3458;}
            ''')
            self.info.setText('Markdown • drag to select text • Ctrl+C to copy')
        else:
            self.view.setPlainText(content)
            self.view.setFont(QFont('DejaVu Sans Mono', 11))
            self.info.setText('Plain text • drag to select text • Ctrl+C to copy')
        if self._is_markdown:
            self.view.setFont(QFont('DejaVu Sans', 12))
        self.view.moveCursor(QTextCursor.MoveOperation.Start)
        return True, ''

    def close_file(self):
        self.source_path = None
        self.safe_doc.allowed_root = None
        self.view.clear()
        self.filename.setText('')
        self.info.setText('')
