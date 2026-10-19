#!/usr/bin/env python3
"""DiscShelf first milestone: a manual-launch, in-memory, offline bookshelf.

Requires Debian 13 package python3-pyside6.qtwidgets.
No background process is installed or started by this application.
"""
import hashlib
import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import (QAbstractListModel, QModelIndex, QObject,
                            QSortFilterProxyModel, Qt, QThread, QTimer,
                            QSize, QRect, Signal, Slot)
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QLinearGradient,
                           QPainter, QPen)
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QListView, QMainWindow, QMessageBox,
                               QPushButton, QStyledItemDelegate, QStyle, QVBoxLayout,
                               QWidget)

from catalog import Document, document_from_path
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
    COLORS = {
        '.pdf': '#964b51',
        '.doc': '#37678a', '.docx': '#37678a',
        '.md': '#a56e43', '.txt': '#87765f',
        '.htm': '#477c78', '.html': '#477c78',
        '.rtf': '#7b617c', '.odt': '#5e688e',
        '.epub': '#617c51',
    }

    def sizeHint(self, option, index):
        return QSize(91, 230)

    def paint(self, painter, option, index):
        book = index.data(Qt.UserRole)
        if book is None:
            return
        rect = option.rect
        digest = hashlib.blake2b(book.path.encode('utf-8', 'replace'), digest_size=3).digest()
        width = 47 + digest[0] % 18
        height = 149 + digest[1] % 35
        shelf_y = rect.bottom() - 19
        left = rect.left() + (rect.width() - width) // 2
        top = shelf_y - height - 4
        spine = QRect(left, top, width, height)
        base = QColor(self.COLORS.get(book.extension, '#655e59'))

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(rect, QColor('#211c1a'))
        # One continuous shelf strip across every item in each row.
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
        painter.fillRect(QRect(left+3, top+7, width-6, 2), QColor('#d8b98c'))
        painter.fillRect(QRect(left+3, top+height-12, width-6, 2), QColor('#d8b98c'))
        # Rotated filename, clipped to available spine height.
        painter.translate(left + width / 2, top + height - 19)
        painter.rotate(-90)
        text_font = QFont('Sans Serif', 9, QFont.DemiBold)
        painter.setFont(text_font)
        painter.setPen(QColor('#fbecce'))
        title = book.title
        title = QFontMetrics(text_font).elidedText(title, Qt.ElideRight, height - 45)
        painter.drawText(QRect(0, -11, height - 42, 22), Qt.AlignVCenter | Qt.AlignHCenter, title)
        painter.restore()


STYLE = """
QMainWindow, QWidget { background-color: #211c1a; color: #eee1ca; }
QLabel#title { color: #f0d2a1; font-size: 24px; font-weight: 700; }
QLabel#subtitle { color: #bdad96; font-size: 12px; }
QPushButton { background: #594535; color: #fff1de; border: 1px solid #7c6144;
              padding: 9px 16px; border-radius: 7px; }
QPushButton:hover { background: #6a523b; }
QPushButton:disabled { background: #36302c; color: #82776b; }
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
        self.books_view.setGridSize(QSize(91, 230))
        self.books_view.setWordWrap(False)
        self.books_view.setSelectionMode(QListView.SingleSelection)
        self.books_view.doubleClicked.connect(self.book_clicked)
        root.addWidget(self.books_view, 1)
        footer = QHBoxLayout()
        self.status_label = QLabel('Insert a disc or choose a folder to see your library.')
        footer.addWidget(self.status_label, 1)
        self.counter_label = QLabel('0 books')
        footer.addWidget(self.counter_label)
        root.addLayout(footer)
        self.setCentralWidget(central)

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
            self.stop_scan()
            self.root = None
            self.root_kind = None
            if self.scan_thread is None:
                self.model.clear()
                self.counter_label.setText('0 books')
            self.status_label.setText('Disc removed. Insert another or choose a folder.')
        if found:
            if self.scan_thread is not None:
                self.stop_scan()
                self.pending_disc = found
            else:
                self.begin_scan(found, 'disc')
        else:
            self.pending_disc = None

    def book_clicked(self, proxy_index):
        book = proxy_index.data(Qt.UserRole)
        if book is None:
            return
        QMessageBox.information(
            self, book.name,
            f'{book.name}\n\nType: {book.extension.upper()}\nSource: {book.path}\n\n'
            'The integrated document readers are the next milestone.\n'
            'This first build proves the bookshelf and filename scanning.'
        )

    def closeEvent(self, event):
        self.disc_timer.stop()
        self.stop_scan()
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
