#!/usr/bin/env python3
"""DiscShelf: manual-launch, offline bookshelf and ten-format document reader.

Debian 13: python3-pyside6.qtwidgets and python3-pyside6.qtpdfwidgets.
No background process is installed or started by this application.
"""
import hashlib
import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import (QAbstractListModel, QModelIndex, QObject,
                            QSortFilterProxyModel, Qt, QThread, QTimer,
                            QSize, QRect, QPointF, Signal, Slot)
from PySide6.QtGui import (QColor, QFont, QLinearGradient,
                           QPainter, QPen, QTextLayout, QTextOption)
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QListView, QMainWindow, QMessageBox,
                               QPushButton, QStackedWidget, QStyledItemDelegate, QStyle, QVBoxLayout,
                               QWidget)

from catalog import Document, document_from_path
from book_colors import spine_color
from disc_detection import mounted_optical_discs


class ScanWorker(QObject):
    batch_ready = Signal(object)
    finished = Signal(int)

    def __init__(self, root: str):
        super().__init__()
        self.root = root
        self.stop_requested = threading.Event()

    @Slot()
    def run(self):
        files = []
        count = 0
        pending = [self.root]
        visited = set()
        while pending and not self.stop_requested.is_set():
            directory = pending.pop()
            # Never follow symbolic-link directories, preventing traversal
            # outside the selected disc/folder and avoiding symlink loops.
            try:
                real_directory = os.path.realpath(directory)
                if real_directory in visited:
                    continue
                visited.add(real_directory)
                with os.scandir(directory) as iterator:
                    for entry in iterator:
                        if self.stop_requested.is_set():
                            break
                        try:
                            if entry.is_symlink():
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                pending.append(entry.path)
                            elif entry.is_file(follow_symlinks=False):
                                doc = document_from_path(entry.path)
                                if doc is not None:
                                    files.append(doc)
                                    count += 1
                                    if len(files) >= 100:
                                        self.batch_ready.emit(files)
                                        files = []
                        except OSError:
                            continue
            except OSError:  # read error, permission denied, or disc ejected
                continue
        if files and not self.stop_requested.is_set():
            self.batch_ready.emit(files)
        self.finished.emit(count)


class BooksModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self.books: list[Document] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.books)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.books):
            return None
        book = self.books[index.row()]
        if role == Qt.DisplayRole:
            return book.name
        if role == Qt.ToolTipRole:
            return f'{book.name}\n{book.path}'
        if role == Qt.UserRole:
            return book
        return None

    def add_batch(self, batch):
        if not batch:
            return
        start = len(self.books)
        self.beginInsertRows(QModelIndex(), start, start + len(batch) - 1)
        self.books.extend(batch)
        self.endInsertRows()

    def clear(self):
        self.beginResetModel()
        self.books.clear()
        self.endResetModel()


class BookshelfDelegate(QStyledItemDelegate):
    """Draw book spines without generating thumbnails or reading file contents.

    Spine titles wrap into multiple rotated lines. Short titles use a legible
    10-point font, while long ones gradually shrink. Names that physically
    cannot fit have a visible ellipsis, never a clipped final line; their full
    spelling is always available by hovering a book (and in its tooltip).
    """
    CELL_WIDTH = 113
    CELL_HEIGHT = 315

    def sizeHint(self, option, index):
        return QSize(self.CELL_WIDTH, self.CELL_HEIGHT)

    @staticmethod
    def _layout_text(title, line_width, max_lines_height):
        """Fit all ordinary-length titles using word/character wrapping.

        Returns a QTextLayout whose lines are positioned and guaranteed to fit
        within max_lines_height. Extraordinarily long file names are shortened
        with an explicit ellipsis at a minimum legible font size.
        """
        def create_layout(text, points):
            font = QFont('DejaVu Sans', points, QFont.DemiBold)
            option = QTextOption()
            option.setAlignment(Qt.AlignHCenter)
            option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
            layout = QTextLayout(text, font)
            layout.setTextOption(option)
            y = 0.0
            layout.beginLayout()
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(line_width)
                line.setPosition(QPointF(0, y))
                y += line.height()
            layout.endLayout()
            return layout, y

        for points in (10, 9, 8, 7):
            layout, used = create_layout(title, points)
            if used <= max_lines_height:
                return layout, used

        # Rare pathological filenames (e.g. >150 characters) cannot be drawn
        # legibly in their entirety on a physical-width spine. Never silently
        # clip: use an ellipsis and show the exact title below on hover.
        # Binary search makes this cheap even for 255-character filenames.
        low, high = 0, len(title)
        best = None
        best_height = 0.0
        while low <= high:
            mid = (low + high) // 2
            candidate = title[:mid] + '…'
            layout, used = create_layout(candidate, 7)
            if used <= max_lines_height:
                best, best_height = layout, used
                low = mid + 1
            else:
                high = mid - 1
        if best is None:
            return create_layout('…', 7)
        return best, best_height

    def paint(self, painter, option, index):
        book = index.data(Qt.UserRole)
        if book is None:
            return
        rect = option.rect
        digest = hashlib.blake2b(book.path.encode('utf-8', 'replace'), digest_size=3).digest()
        width = 70 + digest[0] % 11
        height = 236 + digest[1] % 34
        shelf_y = rect.bottom() - 20
        left = rect.left() + (rect.width() - width) // 2
        top = shelf_y - height - 4
        spine = QRect(left, top, width, height)
        base = QColor(spine_color(book.extension))

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.fillRect(rect, QColor('#211c1a'))
        # Continuous wooden shelf along each row.
        painter.fillRect(QRect(rect.left(), shelf_y - 3, rect.width(), 4), QColor('#120e0c'))
        painter.fillRect(QRect(rect.left(), shelf_y, rect.width(), 14), QColor('#94683f'))
        painter.fillRect(QRect(rect.left(), shelf_y + 13, rect.width(), 6), QColor('#51341f'))
        if option.state & QStyle.State_Selected:
            painter.setPen(QPen(QColor('#f3cf91'), 2))
            painter.setBrush(QColor('#b79665'))
            painter.drawRoundedRect(spine.adjusted(-4, -4, 4, 2), 5, 5)
        gradient = QLinearGradient(spine.topLeft(), spine.topRight())
        gradient.setColorAt(0, base.darker(150))
        gradient.setColorAt(.16, base.lighter(115))
        gradient.setColorAt(.65, base)
        gradient.setColorAt(1, base.darker(135))
        painter.setPen(QPen(base.darker(185), 1))
        painter.setBrush(gradient)
        painter.drawRoundedRect(spine, 3, 3)
        painter.fillRect(QRect(left + 3, top + 7, width - 6, 2), QColor('#d8b98c'))
        painter.fillRect(QRect(left + 3, top + height - 12, width - 6, 2), QColor('#d8b98c'))

        # Paint text rotated bottom-to-top. Unlike the original prototype,
        # it wraps across the spine width rather than forcibly clipping to
        # a single line of text.
        margin = 9
        available_length = height - 36
        available_thickness = width - 2 * margin
        layout, used_height = self._layout_text(book.title, available_length, available_thickness)
        painter.translate(left + margin, top + height - 19)
        painter.rotate(-90)
        painter.setPen(QColor('#FFF2DE'))
        layout.draw(painter, QPointF(0, (available_thickness - used_height) / 2))
        painter.restore()


STYLE = """
QMainWindow, QWidget { background-color: #211c1a; color: #eee1ca; }
QLabel#title { color: #f0d2a1; font-size: 24px; font-weight: 700; }
QLabel#subtitle { color: #bdad96; font-size: 12px; }
QLabel#fullFilename { color: #e9d1ac; font-size: 13px; padding: 4px 2px; }
QLabel#readerFilename { color: #f0d2a1; font-size: 15px; font-weight: 650; }
QLabel#readerInfo { color: #c7b69d; font-size: 12px; }
QSpinBox { background: #312824; color: #fff2df; border: 1px solid #675241;
           border-radius: 5px; padding: 5px; min-width: 58px; }
QPushButton { background: #594535; color: #fff1de; border: 1px solid #7c6144;
              padding: 9px 16px; border-radius: 7px; }
QPushButton:hover { background: #6a523b; }
QPushButton:disabled { background: #36302c; color: #82776b; }
QSlider::groove:horizontal { background: #5b4639; height: 6px; border-radius: 3px; }
QSlider::handle:horizontal { background: #e7ca97; width: 14px; margin: -5px 0px; border-radius: 7px; }
QLineEdit { background: #312824; color: #fff2df; border: 1px solid #675241;
            border-radius: 8px; padding: 9px 13px; font-size: 13px; }
QListView { background: #211c1a; border: 1px solid #44352c; border-radius: 9px; }
QScrollBar:vertical { background: #2f2621; width: 12px; }
QScrollBar::handle:vertical { background: #6c5643; border-radius: 5px; min-height: 24px; }
"""


class MainWindow(QMainWindow):
    def __init__(self, initial_directory=None):
        super().__init__()
        self.setWindowTitle('DiscShelf — Offline Library')
        self.resize(1050, 730)
        self.setMinimumSize(680, 450)
        self.model = BooksModel()
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(0)
        self.scan_thread = None
        self.worker = None
        self.root = None
        self.root_kind = None
        self.last_seen_disc = None
        self.pending_disc = None
        self.pdf_reader = None
        self.text_reader = None
        self.html_reader = None
        self.office_loading = None
        self.office_thread = None
        self.office_worker = None
        self.office_requested_book = None
        self.office_temp_directory = None
        self.epub_reader = None
        self.epub_loading = None
        self.epub_thread = None
        self.epub_worker = None
        self.epub_requested_book = None
        self._build_ui()
        self.setStyleSheet(STYLE)

        # Timer belongs to this GUI process. Closing DiscShelf stops all checks;
        # it has no startup service, tray process, daemon, or scheduler.
        self.disc_timer = QTimer(self)
        self.disc_timer.timeout.connect(self.check_discs)
        self.disc_timer.start(3000)
        if initial_directory:
            QTimer.singleShot(0, lambda: self.begin_scan(initial_directory, 'folder'))
        else:
            QTimer.singleShot(0, self.check_discs)

    def _build_ui(self):
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 17, 22, 14)
        root.setSpacing(12)
        top = QHBoxLayout()
        header = QVBoxLayout()
        title = QLabel('DiscShelf')
        title.setObjectName('title')
        subtitle = QLabel('Your offline library, one disc at a time.')
        subtitle.setObjectName('subtitle')
        header.addWidget(title)
        header.addWidget(subtitle)
        top.addLayout(header)
        top.addStretch()
        self.browse_button = QPushButton('Choose folder / mounted disc')
        self.browse_button.clicked.connect(self.choose_directory)
        top.addWidget(self.browse_button)
        self.stop_button = QPushButton('Stop scan')
        self.stop_button.clicked.connect(self.stop_scan)
        self.stop_button.setEnabled(False)
        top.addWidget(self.stop_button)
        root.addLayout(top)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText('Search filenames...')
        self.search_box.textChanged.connect(self.proxy.setFilterFixedString)
        root.addWidget(self.search_box)
        self.books_view = QListView()
        self.books_view.setModel(self.proxy)
        self.books_view.setItemDelegate(BookshelfDelegate(self.books_view))
        self.books_view.setViewMode(QListView.IconMode)
        self.books_view.setFlow(QListView.LeftToRight)
        self.books_view.setWrapping(True)
        self.books_view.setResizeMode(QListView.Adjust)
        self.books_view.setMovement(QListView.Static)
        self.books_view.setUniformItemSizes(True)
        self.books_view.setSpacing(0)
        self.books_view.setGridSize(QSize(BookshelfDelegate.CELL_WIDTH, BookshelfDelegate.CELL_HEIGHT))
        self.books_view.setWordWrap(True)
        self.books_view.setMouseTracking(True)
        self.books_view.entered.connect(self.show_book_title)
        self.books_view.clicked.connect(self.show_book_title)
        self.books_view.clicked.connect(self.open_book_on_click)
        self.books_view.setSelectionMode(QListView.SingleSelection)
        self.books_view.doubleClicked.connect(self.book_clicked)
        root.addWidget(self.books_view, 1)
        # Exact, selectable filename always appears here on hover/click, even
        # for names too long to fit physically onto a book spine.
        self.full_filename_label = QLabel('Hover over a spine to see its full filename.')
        self.full_filename_label.setObjectName('fullFilename')
        self.full_filename_label.setWordWrap(True)
        self.full_filename_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.full_filename_label)
        footer = QHBoxLayout()
        self.status_label = QLabel('Insert a disc or choose a folder to see your library.')
        footer.addWidget(self.status_label, 1)
        self.counter_label = QLabel('0 books')
        footer.addWidget(self.counter_label)
        root.addLayout(footer)
        self.page_stack = QStackedWidget(self)
        self.page_stack.addWidget(central)
        self.setCentralWidget(self.page_stack)

    def choose_directory(self):
        folder = QFileDialog.getExistingDirectory(self, 'Choose a folder or mounted disc')
        if folder:
            self.begin_scan(folder, 'folder')

    def begin_scan(self, folder, kind):
        if self.scan_thread is not None:
            return
        if not Path(folder).is_dir():
            self.status_label.setText('Folder or disc no longer available.')
            return
        self.root = str(Path(folder).resolve())
        self.root_kind = kind
        self.model.clear()
        self.search_box.clear()
        self.counter_label.setText('0 books')
        self.full_filename_label.setText('Hover over a spine to see its full filename.')
        self.full_filename_label.setToolTip('')
        self.return_to_shelf()
        self.status_label.setText(f'Scanning: {self.root}')
        self.browse_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        thread = QThread(self)
        worker = ScanWorker(self.root)
        worker.moveToThread(thread)
        self.scan_thread = thread
        self.worker = worker
        thread.started.connect(worker.run)
        worker.batch_ready.connect(self.add_books)
        worker.finished.connect(self.scan_completed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self.thread_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot(object)
    def add_books(self, batch):
        self.model.add_batch(batch)
        self.counter_label.setText(f'{self.proxy.rowCount():,} / {self.model.rowCount():,} books')

    @Slot(int)
    def scan_completed(self, count):
        self.status_label.setText(f'{count:,} supported documents • {self.root}')
        self.stop_button.setEnabled(False)
        self.counter_label.setText(f'{self.proxy.rowCount():,} / {self.model.rowCount():,} books')

    @Slot()
    def thread_finished(self):
        self.scan_thread = None
        self.worker = None
        self.browse_button.setEnabled(True)
        if self.root is None:
            self.model.clear()
            self.counter_label.setText('0 books')
        if self.pending_disc:
            disc = self.pending_disc
            self.pending_disc = None
            if Path(disc).is_dir():
                self.begin_scan(disc, 'disc')

    def stop_scan(self):
        if self.worker:
            self.worker.stop_requested.set()
            self.status_label.setText('Stopping scan...')
            self.stop_button.setEnabled(False)

    def check_discs(self):
        discs = mounted_optical_discs()
        found = discs[0] if discs else None
        if found == self.last_seen_disc:
            return
        previous = self.last_seen_disc
        self.last_seen_disc = found
        if previous and self.root_kind == 'disc' and previous != found:
            self.return_to_shelf()
            self.stop_scan()
            self.root = None
            self.root_kind = None
            if self.scan_thread is None:
                self.model.clear()
                self.counter_label.setText('0 books')
            self.full_filename_label.setText('Hover over a spine to see its full filename.')
            self.full_filename_label.setToolTip('')
            self.status_label.setText('Disc removed. Insert another or choose a folder.')
        if found:
            if self.scan_thread is not None:
                self.stop_scan()
                self.pending_disc = found
            else:
                self.begin_scan(found, 'disc')
        else:
            self.pending_disc = None

    @Slot(QModelIndex)
    def show_book_title(self, proxy_index):
        book = proxy_index.data(Qt.UserRole)
        if book is not None:
            self.full_filename_label.setText(book.name)
            self.full_filename_label.setToolTip(book.path)

    def open_book_on_click(self, proxy_index):
        """Single-click supported spines to open a reader inside DiscShelf."""
        book = proxy_index.data(Qt.UserRole)
        if book is None:
            return
        if book.extension == '.pdf':
            self._open_pdf(book)
        elif book.extension in ('.md', '.txt'):
            self._open_text(book)
        elif book.extension in ('.html', '.htm'):
            self._open_html(book)
        elif book.extension in ('.doc', '.docx', '.rtf', '.odt'):
            self._open_office(book)
        elif book.extension == '.epub':
            self._open_epub(book)

    def _open_pdf(self, book, source_note=None):
        if self.pdf_reader is None:
            try:
                # Qt PDF is optional until a PDF is actually opened.
                from pdf_reader import PdfReader
            except ImportError:
                QMessageBox.warning(
                    self, 'PDF reader dependency missing',
                    'Install the Debian 13 Qt PDF package:\n\n'
                    'sudo apt install python3-pyside6.qtpdfwidgets'
                )
                return
            self.pdf_reader = PdfReader(self)
            self.pdf_reader.back_requested.connect(self.return_to_shelf)
            self.page_stack.addWidget(self.pdf_reader)
        if not self.pdf_reader.open_file(book.path, display_name=book.name,
                                         source_note=source_note):
            QMessageBox.warning(self, 'Missing document',
                                'The document is no longer accessible. Is the disc still inserted?')
            return
        self.page_stack.setCurrentWidget(self.pdf_reader)

    def _open_text(self, book):
        if self.text_reader is None:
            from text_reader import TextReader
            self.text_reader = TextReader(self)
            self.text_reader.back_requested.connect(self.return_to_shelf)
            self.page_stack.addWidget(self.text_reader)
        ok, error = self.text_reader.open_file(book.path, allowed_root=self.root)
        if not ok:
            QMessageBox.warning(self, 'Unable to read document', error)
            return
        self.page_stack.setCurrentWidget(self.text_reader)

    def _open_html(self, book):
        if self.html_reader is None:
            try:
                # WebEngine stays unloaded until an HTML/HTM book is clicked.
                from html_reader import HtmlReader
            except ImportError as exc:
                QMessageBox.warning(
                    self, 'HTML reader dependency missing',
                    'Install the Debian 13 Qt WebEngine package:\n\n'
                    'sudo apt install python3-pyside6.qtwebenginewidgets\n\n'
                    f'{exc}'
                )
                return
            self.html_reader = HtmlReader(self)
            self.html_reader.back_requested.connect(self.return_to_shelf)
            self.page_stack.addWidget(self.html_reader)
        ok, error = self.html_reader.open_file(book.path, allowed_root=self.root)
        if not ok:
            QMessageBox.warning(self, 'Unable to open HTML', error)
            return
        self.page_stack.setCurrentWidget(self.html_reader)

    def _open_office(self, book):
        """Open a single Office document without freezing the bookshelf UI."""
        if self.office_thread is not None:
            QMessageBox.information(self, 'Conversion still finishing',
                                    'The previous Office conversion is stopping. Please try again shortly.')
            return
        # If an earlier preview is loaded, close PDF handles before cleanup.
        self.return_to_shelf()
        if self.office_loading is None:
            from office_reader import OfficeLoadingView
            self.office_loading = OfficeLoadingView(self)
            self.office_loading.back_requested.connect(self.return_to_shelf)
            self.page_stack.addWidget(self.office_loading)
        self.office_requested_book = book
        self.office_loading.show_document(book.name)
        self.page_stack.setCurrentWidget(self.office_loading)

        from office_reader import OfficeConversionWorker
        thread = QThread(self)
        worker = OfficeConversionWorker(book.path, self.root)
        worker.moveToThread(thread)
        self.office_thread = thread
        self.office_worker = worker
        thread.started.connect(worker.run)
        worker.converted.connect(self._office_converted)
        worker.failed.connect(self._office_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._office_thread_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot(str, str)
    def _office_converted(self, pdf_path, temp_directory):
        from office_conversion import cleanup_preview
        book = self.office_requested_book
        if book is None or not self.root or not Path(book.path).is_file() or self.page_stack.currentWidget() != self.office_loading:
            cleanup_preview(temp_directory)
            return
        # Take ownership of the RAM-backed PDF until the reader is closed.
        self.office_requested_book = None
        self.office_temp_directory = temp_directory
        from catalog import Document
        preview = Document(path=pdf_path, name=book.name, extension='.pdf')
        self._open_pdf(preview, source_note='temporary Office preview in RAM (original on disc)')
        if self.page_stack.currentWidget() != self.pdf_reader:
            self._remove_office_preview()
            self.page_stack.setCurrentIndex(0)

    @Slot(str)
    def _office_failed(self, message):
        if self.office_requested_book is not None:
            self.office_requested_book = None
            if self.page_stack.currentWidget() == self.office_loading:
                self.page_stack.setCurrentIndex(0)
                if message != 'Conversion cancelled.':
                    QMessageBox.warning(self, 'Unable to open Office document', message)

    @Slot()
    def _office_thread_finished(self):
        self.office_thread = None
        self.office_worker = None

    def _remove_office_preview(self):
        if self.office_temp_directory:
            from office_conversion import cleanup_preview
            cleanup_preview(self.office_temp_directory)
            self.office_temp_directory = None


    def _open_epub(self, book):
        """Prepare the EPUB in RAM without blocking the Qt GUI thread."""
        if self.epub_thread is not None:
            QMessageBox.information(self, 'EPUB still loading',
                                    'The previous EPUB is still being prepared or cancelled.')
            return
        self.return_to_shelf()
        if self.epub_loading is None:
            from epub_loading import EpubLoadingView
            self.epub_loading = EpubLoadingView(self)
            self.epub_loading.back_requested.connect(self.return_to_shelf)
            self.page_stack.addWidget(self.epub_loading)
        self.epub_requested_book = book
        self.epub_loading.show_document(book.name)
        self.page_stack.setCurrentWidget(self.epub_loading)

        from epub_loading import EpubLoadingWorker
        thread = QThread(self)
        worker = EpubLoadingWorker(book.path, self.root)
        worker.moveToThread(thread)
        self.epub_thread = thread
        self.epub_worker = worker
        thread.started.connect(worker.run)
        worker.prepared.connect(self._epub_prepared)
        worker.failed.connect(self._epub_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._epub_thread_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot(object)
    def _epub_prepared(self, preview):
        from epub_archive import cleanup_epub
        book = self.epub_requested_book
        if (book is None or not self.root or not Path(book.path).is_file()
                or self.page_stack.currentWidget() != self.epub_loading):
            cleanup_epub(preview.temp_directory)
            return
        self.epub_requested_book = None
        if self.epub_reader is None:
            try:
                from epub_reader import EpubReader
            except ImportError as exc:
                cleanup_epub(preview.temp_directory)
                self.page_stack.setCurrentIndex(0)
                QMessageBox.warning(self, 'EPUB reader dependency missing',
                                    'Install the Qt WebEngine package:\n\n'
                                    'sudo apt install python3-pyside6.qtwebenginewidgets\n\n'
                                    + str(exc))
                return
            self.epub_reader = EpubReader(self)
            self.epub_reader.back_requested.connect(self.return_to_shelf)
            self.page_stack.addWidget(self.epub_reader)
        try:
            ok, error = self.epub_reader.open_preview(preview, book.name)
        except Exception as exc:
            ok, error = False, str(exc)
        if not ok:
            cleanup_epub(preview.temp_directory)
            self.page_stack.setCurrentIndex(0)
            QMessageBox.warning(self, 'Unable to read EPUB', error)
            return
        self.page_stack.setCurrentWidget(self.epub_reader)

    @Slot(str)
    def _epub_failed(self, message):
        if self.epub_requested_book is not None:
            self.epub_requested_book = None
            if self.page_stack.currentWidget() == self.epub_loading:
                self.page_stack.setCurrentIndex(0)
                if message != 'EPUB opening cancelled.':
                    QMessageBox.warning(self, 'Unable to open EPUB', message)

    @Slot()
    def _epub_thread_finished(self):
        self.epub_thread = None
        self.epub_worker = None

    def book_clicked(self, proxy_index):
        # All ten planned formats now have single-click readers.
        book = proxy_index.data(Qt.UserRole)
        if book is None or book.extension in ('.pdf', '.md', '.txt', '.html', '.htm', '.doc', '.docx', '.rtf', '.odt', '.epub'):
            return
        QMessageBox.information(self, book.name, 'This document format could not be opened.')

    def return_to_shelf(self):
        self.epub_requested_book = None
        if self.epub_worker is not None:
            self.epub_worker.cancel_event.set()
        if self.epub_reader is not None:
            self.epub_reader.close_file()
        self.office_requested_book = None
        if self.office_worker is not None:
            self.office_worker.cancel_event.set()
        if self.pdf_reader is not None:
            self.pdf_reader.close_file()
        if self.text_reader is not None:
            self.text_reader.close_file()
        if self.html_reader is not None:
            self.html_reader.close_file()
        self._remove_office_preview()
        self.page_stack.setCurrentIndex(0)

    def closeEvent(self, event):
        self.disc_timer.stop()
        self.return_to_shelf()
        self.stop_scan()
        if self.epub_thread is not None:
            self.epub_thread.quit()
            if not self.epub_thread.wait(5000):
                self.status_label.setText('Stopping EPUB extraction before exit...')
                event.ignore()
                return
            # Process queued EPUB previews so late results are cleaned up.
            QApplication.processEvents()
        if self.office_thread is not None:
            self.office_thread.quit()
            if not self.office_thread.wait(5000):
                self.status_label.setText('Stopping Office conversion before exit...')
                event.ignore()
                return
            # Deliver queued completion/cleanup callbacks before quitting Qt.
            # A completed conversion may have emitted its preview just as the
            # application was closing. No RAM temporary folder should remain.
            QApplication.processEvents()
        if self.scan_thread is not None:
            self.scan_thread.quit()
            # Avoid destroying a running QThread (which can crash Qt).
            if not self.scan_thread.wait(5000):
                self.status_label.setText('Finishing optical scan before exit...')
                event.ignore()
                return
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('DiscShelf')
    directory = sys.argv[1] if len(sys.argv) > 1 else None
    if directory and not Path(directory).is_dir():
        print(f'Not a directory: {directory}', file=sys.stderr)
        return 2
    window = MainWindow(directory)
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
