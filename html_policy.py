"""Platform-neutral safety rules for the DiscShelf HTML/HTM reader.

Only regular resources from the currently selected DVD/directory may be loaded;
no network or files elsewhere on the host. The Qt WebEngine adapter enforces
these rules on EVERY request and top-level navigation.
"""
from pathlib import Path
from urllib.parse import unquote, urlsplit

# HTML pages and the static assets they commonly need. Intentionally exclude
# JavaScript, media streaming, office documents, plugins, and other programs.
HTML_EXTENSIONS = frozenset({'.html', '.htm', '.xhtml'})
STATIC_EXTENSIONS = frozenset({
    '.css', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.avif',
    '.svg', '.ico', '.woff', '.woff2', '.ttf', '.otf', '.eot',
})
RESOURCE_EXTENSIONS = HTML_EXTENSIONS | STATIC_EXTENSIONS
# data: URLs allow embedded base64 icons/images and some CSS-generated assets;
# javascript: and every network protocol remain rejected.
EMBEDDED_SCHEMES = frozenset({'data'})


def safe_local_file(path: str | Path, root: str | Path, allowed_extensions=RESOURCE_EXTENSIONS) -> bool:
    """Check existing regular file, inside root after resolving symbolic links."""
    try:
        candidate = Path(path).resolve(strict=True)
        base = Path(root).resolve(strict=True)
        return (candidate.is_file() and candidate.is_relative_to(base)
                and candidate.suffix.lower() in allowed_extensions)
    except (OSError, ValueError, RuntimeError):
        return False


def safe_file_url(url: str, root: str | Path, allowed_extensions=RESOURCE_EXTENSIONS) -> bool:
    """Pure-Python counterpart to Qt's QUrl checks; used in policy tests."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() != 'file' or parsed.netloc not in ('', 'localhost'):
            return False
        # A relative path is never a valid file:// resource.
        raw_path = unquote(parsed.path)
        if not raw_path.startswith('/') or '\x00' in raw_path:
            return False
        return safe_local_file(raw_path, root, allowed_extensions)
    except (ValueError, TypeError):
        return False


def is_allowed_url(url: str, root: str | Path, *, navigation=False) -> bool:
    """Document resource policy; navigation is limited to HTML/HTM documents."""
    try:
        scheme = urlsplit(url).scheme.lower()
    except (ValueError, TypeError):
        return False
    if scheme in EMBEDDED_SCHEMES and not navigation:
        return True
    return safe_file_url(url, root, HTML_EXTENSIONS if navigation else RESOURCE_EXTENSIONS)
