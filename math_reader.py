"""On-demand, OFFLINE MathJax renderer for safe Markdown with math.

Qt WebEngine is imported only for Markdown containing valid math delimiters.
No scripts or HTML from the DVD execute: markdown-it disables raw HTML.
The only executable script comes from the locally installed MathJax.
"""
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView

from math_markdown import make_math_page

# Debian uses MathJax 2; Arch ships MathJax 4. No CDN or network fallback.
MATHJAX_CANDIDATES = (
    Path('/usr/share/javascript/mathjax/MathJax.js'),  # Debian libjs-mathjax
    Path('/usr/share/mathjax/tex-svg.js'),              # Arch mathjax (v4)
    Path('/usr/share/mathjax/MathJax.js'),              # older Arch MathJax 2
    Path('/usr/share/mathjax2/MathJax.js'),
)
MATHJAX_FILE = next((p for p in MATHJAX_CANDIDATES if p.is_file()), MATHJAX_CANDIDATES[0])
ALLOWED_IMAGE_TYPES = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'}


class OfflineOnlyInterceptor(QWebEngineUrlRequestInterceptor):
    """Before network requests reach Chromium, reject anything not allowlisted."""

    def __init__(self, disc_root: Path, mathjax_root: Path, parent=None):
        super().__init__(parent)
        self.disc_root = disc_root.resolve()
        self.mathjax_root = mathjax_root.resolve()

    def interceptRequest(self, info):
        url = info.requestUrl()
        # setHtml() generates a data: main frame document. MathJax outputs SVG
        # in the page and may use data: URLs as well; no network access.
        if url.scheme() in ('data', 'about'):
            return
        if url.scheme() != 'file':
            info.block(True)
            return
        try:
            location = Path(url.toLocalFile()).resolve(strict=True)
            if not location.is_file():
                info.block(True)
                return
            if location.is_relative_to(self.mathjax_root):
                # Trusted local MathJax resources (JS/SVG/font data).
                return
            if (location.is_relative_to(self.disc_root)
                    and location.suffix.lower() in ALLOWED_IMAGE_TYPES):
                return
        except (ValueError, OSError):
            pass
        info.block(True)


class LockedMathPage(QWebEnginePage):
    """Prevent clicking links or navigating the reader to other documents."""

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if navigation_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            return False
        # HTML is loaded with setHtml(), which internally uses data:.
        if is_main_frame and url.scheme() not in ('data', 'about'):
            return False
        return True


def create_math_view(fragment: str, source_path: Path, disc_root: Path, parent=None):
    """Create a disposable view with a private, memory-only WebEngine profile."""
    if not MATHJAX_FILE.is_file():
        raise RuntimeError('Missing local MathJax: install mathjax (Arch) or libjs-mathjax (Debian).')

    view = QWebEngineView(parent)
    # No storageName means the profile is off-the-record (no persistent cache).
    profile = QWebEngineProfile(view)
    profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
    interceptor = OfflineOnlyInterceptor(disc_root, MATHJAX_FILE.parent, profile)
    profile.setUrlRequestInterceptor(interceptor)
    page = LockedMathPage(profile, view)
    view.setPage(page)
    settings = page.settings()
    for attribute in (
        QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
        QWebEngineSettings.WebAttribute.LocalStorageEnabled,
        QWebEngineSettings.WebAttribute.WebGLEnabled,
        QWebEngineSettings.WebAttribute.DnsPrefetchEnabled,
        QWebEngineSettings.WebAttribute.PluginsEnabled,
        QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,
    ):
        settings.setAttribute(attribute, False)
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    # MathJax needs JS. Only the trusted, locally installed MathJax and app
    # configuration execute; there is no DVD-supplied executable JavaScript.
    settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
    view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    html = make_math_page(fragment, MATHJAX_FILE)
    if len(html.encode('utf-8')) > 1_750_000:
        view.deleteLater()
        raise RuntimeError('Math-enabled Markdown document is too large for the 2 MiB Qt HTML loader.')
    view.setHtml(html, QUrl.fromLocalFile(str(source_path)))
    return view
