"""Offline, read-only EPUB reader with chapter controls and table of contents.

Only a vetted RAM-extracted EPUB is shown in an anonymous WebEngine profile.
JavaScript and network access are disabled; pages and resources must be in the
selected book's temporary directory. All data is cleared on return to shelf.
"""
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSlider, QSplitter,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from epub_archive import EpubPreview, cleanup_epub
from html_reader import DiscOnlyInterceptor, DiscOnlyPage


class EpubReader(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.preview: EpubPreview | None = None
        self.chapter_index = 0
        self._toc_widgets = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        head = QHBoxLayout()
        back = QPushButton('← Back to bookshelf')
        back.clicked.connect(self.back_requested.emit)
        head.addWidget(back)
        self.book_label = QLabel('')
        self.book_label.setObjectName('readerFilename')
        head.addWidget(self.book_label, 1)
        layout.addLayout(head)

        controls = QHBoxLayout()
        self.previous = QPushButton('← Previous chapter')
        self.next = QPushButton('Next chapter →')
        self.previous.clicked.connect(lambda: self._change_chapter(-1))
        self.next.clicked.connect(lambda: self._change_chapter(1))
        controls.addWidget(self.previous)
        controls.addWidget(self.next)
        self.chapter_label = QLabel('')
        self.chapter_label.setObjectName('readerInfo')
        controls.addWidget(self.chapter_label, 1)
        controls.addWidget(QLabel('Zoom'))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(50, 200)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(150)
        controls.addWidget(self.zoom_slider)
        self.zoom_percent = QLabel('100%')
        controls.addWidget(self.zoom_percent)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.toc_view = QTreeWidget()
        self.toc_view.setHeaderHidden(True)
        self.toc_view.setMinimumWidth(145)
        self.toc_view.setMaximumWidth(380)
        self.toc_view.setToolTip('EPUB table of contents')
        self.toc_view.itemClicked.connect(self._toc_clicked)
        splitter.addWidget(self.toc_view)

        self.web = QWebEngineView(self)
        # Passing a parent constructs an off-the-record profile: no disk cache.
        self.profile = QWebEngineProfile(self.web)
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        self.interceptor = DiscOnlyInterceptor(Path('/nonexistent-discshelf-epub-root'), self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.page = DiscOnlyPage(self.profile, self.web)
        self.web.setPage(self.page)
        for attr in (
            QWebEngineSettings.WebAttribute.JavascriptEnabled,
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            QWebEngineSettings.WebAttribute.LocalStorageEnabled,
            QWebEngineSettings.WebAttribute.WebGLEnabled,
            QWebEngineSettings.WebAttribute.DnsPrefetchEnabled,
            QWebEngineSettings.WebAttribute.PluginsEnabled,
            QWebEngineSettings.WebAttribute.HyperlinkAuditingEnabled,
        ):
            self.page.settings().setAttribute(attr, False)
        self.page.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        splitter.addWidget(self.web)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([235, 750])
        layout.addWidget(splitter, 1)
        self.info_label = QLabel('EPUB • local text/images/CSS • JavaScript disabled • Ctrl+C copies selected text')
        self.info_label.setObjectName('readerInfo')
        layout.addWidget(self.info_label)
        self.zoom_slider.valueChanged.connect(self._zoom_changed)
        self.web.urlChanged.connect(self._url_changed)
        self.web.loadFinished.connect(self._load_finished)
        self._update_controls()

    def open_preview(self, preview: EpubPreview, original_filename: str) -> tuple[bool, str]:
        self.close_file()
        source_dir = Path(preview.temp_directory)
        if not source_dir.is_dir() or not preview.chapters:
            return False, 'EPUB temporary preview is missing or has no chapters.'
        self.preview = preview
        self.book_label.setText(original_filename)
        self.book_label.setToolTip(f'{preview.display_title} — {original_filename}')
        self.interceptor.root = source_dir.resolve()
        self.page.root = source_dir.resolve()
        self._toc_widgets.clear()
        for entry in preview.toc:
            item = QTreeWidgetItem([entry.label])
            item.setToolTip(0, entry.label)
            item.setData(0, Qt.ItemDataRole.UserRole, (entry.archive_path, entry.fragment))
            # A simple indented TOC keeps even deeply nested EPUB nav readable.
            item.setText(0, '  ' * min(entry.level, 5) + entry.label)
            self.toc_view.addTopLevelItem(item)
            self._toc_widgets.append(item)
        self.zoom_slider.setValue(100)
        self._navigate_chapter(0)
        return True, ''

    def _zoom_changed(self, value):
        self.web.setZoomFactor(value / 100.0)
        self.zoom_percent.setText(f'{value}%')

    def _url_for(self, name: str, fragment: str = '') -> QUrl:
        assert self.preview is not None
        url = QUrl.fromLocalFile(str(Path(self.preview.temp_directory) / name))
        if fragment:
            url.setFragment(fragment)
        return url

    def _navigate_chapter(self, number: int):
        if not self.preview or not 0 <= number < len(self.preview.chapters):
            return
        self.chapter_index = number
        self.web.setUrl(self._url_for(self.preview.chapters[number].archive_path))
        self._update_controls()

    def _change_chapter(self, delta: int):
        self._navigate_chapter(self.chapter_index + delta)

    def _toc_clicked(self, item, _column):
        if not self.preview:
            return
        name, fragment = item.data(0, Qt.ItemDataRole.UserRole)
        if name:
            self.web.setUrl(self._url_for(name, fragment))

    def _url_changed(self, url):
        if not self.preview or not url.isLocalFile():
            return
        try:
            relative = Path(url.toLocalFile()).resolve().relative_to(
                Path(self.preview.temp_directory).resolve()).as_posix()
        except (OSError, ValueError):
            return
        for index, chapter in enumerate(self.preview.chapters):
            if chapter.archive_path == relative:
                self.chapter_index = index
                break
        for entry, item in zip(self.preview.toc, self._toc_widgets):
            if entry.archive_path == relative:
                self.toc_view.setCurrentItem(item)
                break
        self._update_controls()

    def _load_finished(self, success):
        if self.preview is not None:
            self.info_label.setText(
                'EPUB • local text/images/CSS • JavaScript disabled • Ctrl+C copies selected text'
                if success else 'Could not display this EPUB chapter.')

    def _update_controls(self):
        if not self.preview:
            self.previous.setEnabled(False)
            self.next.setEnabled(False)
            self.chapter_label.clear()
            return
        self.previous.setEnabled(self.chapter_index > 0)
        self.next.setEnabled(self.chapter_index + 1 < len(self.preview.chapters))
        self.chapter_label.setText(
            f'Chapter {self.chapter_index + 1} of {len(self.preview.chapters)}')

    def close_file(self):
        # Stop pending file loads before removing the RAM-backed source files.
        self.web.stop()
        self.web.setUrl(QUrl('about:blank'))
        self.web.history().clear()
        self.page.root = None
        self.interceptor.root = Path('/nonexistent-discshelf-epub-root')
        preview = self.preview
        self.preview = None
        self._toc_widgets.clear()
        self.toc_view.clear()
        self.chapter_index = 0
        self.book_label.clear()
        self.book_label.setToolTip('')
        self.info_label.setText('EPUB • offline • JavaScript disabled')
        self._update_controls()
        if preview is not None:
            cleanup_epub(preview.temp_directory)
