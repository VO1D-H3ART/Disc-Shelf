"""JavaScript-free, offline HTML/HTM reader for DiscShelf.

Qt WebEngine opens original source files on the disc so relative CSS, images,
fonts and links work without rewriting document paths or making local copies.
No HTML from the disc can execute JS, send network requests, or read files
outside the selected disc root. All browser storage is in-memory only.
"""
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from html_policy import HTML_EXTENSIONS, RESOURCE_EXTENSIONS, safe_local_file


def _file_from_qurl(url: QUrl) -> str | None:
    if url.scheme().lower() != 'file' or url.host().lower() not in ('', 'localhost'):
        return None
    try:
        path = url.toLocalFile()
        return path if path and Path(path).is_absolute() else None
    except (OSError, ValueError):
        return None


def _qt_resource_allowed(url: QUrl, root: Path, *, navigation=False) -> bool:
    if not navigation and url.scheme().lower() == 'data':
        return True
    path = _file_from_qurl(url)
    return bool(path and safe_local_file(
        path, root, HTML_EXTENSIONS if navigation else RESOURCE_EXTENSIONS
    ))


class DiscOnlyInterceptor(QWebEngineUrlRequestInterceptor):
    """Block requests before Qt WebEngine's network stack can fetch them."""

    def __init__(self, root: Path, parent=None):
        super().__init__(parent)
        self.root = root

    def interceptRequest(self, info):
        url = info.requestUrl()
        scheme = url.scheme().lower()
        # Empty internal page needed to clear reader when a disc is ejected.
        if scheme == 'about' and url.toString() == 'about:blank':
            return
        if _qt_resource_allowed(url, self.root):
            return
        info.block(True)


class DiscOnlyPage(QWebEnginePage):
    """Allow same-disc HTML navigation; reject all other page locations."""

    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.root = None

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if url.toString() == 'about:blank':
            return True
        if self.root is None:
            return False
        if is_main_frame:
            return _qt_resource_allowed(url, self.root, navigation=True)
        # Nested frames also cannot load HTTP/HTTPS or non-disc HTML.
        return _qt_resource_allowed(url, self.root)

    def createWindow(self, _type):
        # target=_blank and window.open() may not open browser windows.
        return None


class HtmlReader(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = None
        self.source_path = None
        self.setObjectName('htmlReader')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(9)
        toolbar = QHBoxLayout()
        back_to_shelf = QPushButton('← Back to bookshelf')
        back_to_shelf.clicked.connect(self.back_requested.emit)
        toolbar.addWidget(back_to_shelf)
        self.filename = QLabel('')
        self.filename.setObjectName('readerFilename')
        self.filename.setToolTip('')
        toolbar.addWidget(self.filename, 1)
        layout.addLayout(toolbar)

        controls = QHBoxLayout()
        self.previous = QPushButton('← Page')
        self.forward = QPushButton('Page →')
        self.previous.setToolTip('Previous HTML page')
        self.forward.setToolTip('Next HTML page')
        self.previous.clicked.connect(lambda: self.web.back())
        self.forward.clicked.connect(lambda: self.web.forward())
        controls.addWidget(self.previous)
        controls.addWidget(self.forward)
        controls.addStretch()
        controls.addWidget(QLabel('Zoom'))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setMinimum(50)
        self.zoom_slider.setMaximum(200)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(175)
        self.zoom_slider.setToolTip('HTML page zoom')
        controls.addWidget(self.zoom_slider)
        self.zoom_display = QLabel('100%')
        controls.addWidget(self.zoom_display)
        layout.addLayout(controls)

        self.web = QWebEngineView(self)
        # Anonymous profile has no persistent disk cache, cookies or storage.
        # A fresh profile is assigned to this reader; never use the default.
        self.profile = QWebEngineProfile(self.web)
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
        )
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        self.interceptor = DiscOnlyInterceptor(Path('/nonexistent-discshelf-root'), self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.page = DiscOnlyPage(self.profile, self.web)
        self.web.setPage(self.page)
        settings = self.page.settings()
        for attribute in (
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
            settings.setAttribute(attribute, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        layout.addWidget(self.web, 1)
        self.info = QLabel('HTML/CSS only • JavaScript off • Ctrl+C copies selected text')
        self.info.setObjectName('readerInfo')
        layout.addWidget(self.info)
        self.zoom_slider.valueChanged.connect(self._zoom_changed)
        self.web.urlChanged.connect(self._url_changed)
        self.web.loadFinished.connect(self._loaded)
        self._refresh_navigation()

    def _zoom_changed(self, value):
        self.web.setZoomFactor(value / 100.0)
        self.zoom_display.setText(f'{value}%')

    def _refresh_navigation(self):
        self.previous.setEnabled(self.web.history().canGoBack())
        self.forward.setEnabled(self.web.history().canGoForward())

    def _url_changed(self, url):
        self._refresh_navigation()
        if url.isLocalFile() and self.root is not None:
            # Page links may navigate from one HTML file to another.
            self.filename.setText(Path(url.toLocalFile()).name)
            self.filename.setToolTip(url.toLocalFile())

    def _loaded(self, success):
        self._refresh_navigation()
        if not success and self.source_path is not None:
            self.info.setText('Unable to load the HTML page or one of its resources.')
        elif self.source_path is not None:
            self.info.setText('HTML/CSS only • JavaScript off • Ctrl+C copies selected text')

    def open_file(self, path: str, allowed_root: str | None = None) -> tuple[bool, str]:
        source = Path(path)
        root = Path(allowed_root or source.parent)
        if not safe_local_file(source, root, HTML_EXTENSIONS):
            return False, ('Cannot open HTML document. The file is missing, is not HTML/HTM, '
                           'or is outside the currently selected disc.')
        self.close_file()
        self.root = root.resolve()
        self.source_path = str(source.resolve())
        # The interceptor and navigation page both require an explicit root.
        self.interceptor.root = self.root
        self.page.root = self.root
        self.filename.setText(source.name)
        self.filename.setToolTip(str(source))
        self.zoom_slider.setValue(100)
        self.web.setUrl(QUrl.fromLocalFile(self.source_path))
        return True, ''

    def close_file(self):
        # Clear the current document BEFORE resetting its permissions, so
        # navigation history and resources are no longer available on ejection.
        self.web.setUrl(QUrl('about:blank'))
        self.web.history().clear()
        self.root = None
        self.page.root = None
        self.interceptor.root = Path('/nonexistent-discshelf-root')
        self.source_path = None
        self.filename.clear()
        self.filename.setToolTip('')
        self.info.setText('HTML/CSS only • JavaScript off • Ctrl+C copies selected text')
        self._refresh_navigation()
