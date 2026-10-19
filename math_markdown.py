"""Convert math-enabled Markdown to safe, browser-rendered HTML.

The browser receives HTML generated with markdown-it's raw-HTML parsing off.
Only safe inline span colours are permitted; arbitrary source HTML remains escaped.
Math tokens are preserved through Markdown parsing so Markdown cannot strip
LaTeX backslashes or interpret underscores/asterisks inside an equation.
"""

from html import escape
from pathlib import Path

from markdown_colors import enable_safe_colors

# Debian 13: sudo apt install python3-markdown-it
# Import only when opening a math-containing file (not during startup).


def _closing_delimiter(source: str, start: int, closing: str, multiline: bool) -> int:
    """Return the first unescaped closing marker, or -1."""
    end = source.find(closing, start)
    while end != -1:
        if not multiline and '\n' in source[start:end]:
            return -1
        # Odd backslash count means delimiter was escaped.
        backslashes = 0
        p = end - 1
        while p >= start and source[p] == '\\':
            backslashes += 1
            p -= 1
        if backslashes % 2 == 0:
            return end
        end = source.find(closing, end + len(closing))
    return -1


def _math_rule(state, silent: bool) -> bool:
    src = state.src
    pos = state.pos
    if src.startswith('$$', pos):
        opener, closer, display = '$$', '$$', True
    elif src.startswith(r'\[', pos):
        opener, closer, display = r'\[', r'\]', True
    elif src.startswith(r'\(', pos):
        opener, closer, display = r'\(', r'\)', False
    elif src.startswith('$', pos):
        opener, closer, display = '$', '$', False
    else:
        return False

    start = pos + len(opener)
    end = _closing_delimiter(src, start, closer, multiline=display)
    if end < 0 or end == start:
        return False
    inner = src[start:end]
    if not display and (inner[0].isspace() or inner[-1].isspace()):
        return False
    # '$$' at the start of a single-$ expression should never terminate it.
    if opener == '$' and (src.startswith('$$', end) or src[start] == '$'):
        return False

    if not silent:
        token = state.push('html_inline', '', 0)
        css_class = 'math-display' if display else 'math-inline'
        # The entire math expression remains escaped text, not user HTML.
        token.content = f'<span class="{css_class}">{escape(src[pos:end + len(closer)])}</span>'
    state.pos = end + len(closer)
    return True


def render_math_markdown(source: str) -> tuple[str, bool]:
    """Return (sanitized Markdown HTML, found real math tokens)."""
    from markdown_it import MarkdownIt

    parser = MarkdownIt('commonmark', {'html': False, 'linkify': False})
    parser.enable('table')
    parser.enable('strikethrough')
    enable_safe_colors(parser)
    parser.inline.ruler.before('escape', 'discshelf_math', _math_rule)
    html = parser.render(source)
    has_math = ('class="math-inline"' in html or 'class="math-display"' in html)
    return html, has_math


def likely_has_math(source: str) -> bool:
    """Cheap precheck; accurate check is done by render_math_markdown."""
    return '$' in source or r'\(' in source or r'\[' in source


CSS = r'''html { color-scheme: light; }
body { background: #f6f0e5; color: #292522; font: 17px/1.72 "DejaVu Sans", sans-serif;
  margin: 0 auto; max-width: 850px; padding: 26px 36px 100px; overflow-wrap: break-word; }
h1,h2,h3 { color: #3c315c; line-height: 1.27; margin-top: 1.7em; }
h1 { border-bottom: 1px solid #d9cbb5; padding-bottom: 10px; }
a { color: #385c92; }
pre,code { font-family: "DejaVu Sans Mono", monospace; background: #eee5d7; }
pre { padding: 14px; overflow-x: auto; border-radius: 6px; line-height: 1.5; }
code { padding: 1px 4px; } pre code { padding: 0; }
blockquote { border-left: 4px solid #a898d4; padding: 4px 18px; margin-left: 0; background: #f0e8dc; }
table { border-collapse: collapse; width: 100%; }
td,th { padding: 8px 11px; border: 1px solid #c9bca6; text-align: left; }
th { background: #e8ddce; }
img { max-width: 100%; height: auto; }
.math-display { display: block; overflow-x: auto; overflow-y: hidden; text-align: center; margin: 1.1em 0; }
.math-inline { display: inline; }
::selection { background: #79a8f3; color: #191919; }
'''

# This is trusted app-owned configuration, not code from the disc.
# Enable $...$, $$...$$, \(...\), and \[...\].
MATHJAX_CONFIG = r'''
MathJax.Hub.Config({
  showMathMenu: false,
  messageStyle: "none",
  tex2jax: {
    inlineMath: [['$','$'], ['\\(','\\)']],
    displayMath: [['$$','$$'], ['\\[','\\]']],
    processEscapes: true,
    skipTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code']
  },
  "SVG": {font: "TeX", useGlobalCache: false}
});
'''


def make_math_page(fragment: str, mathjax_js: Path) -> str:
    """Assemble a locally served (never remotely sourced) MathJax 2 page."""
    local_url = escape(mathjax_js.resolve().as_uri(), quote=True)
    # MathJax 2 config loads TeX and the SVG renderer from Debian's local lib.
    return ("<!doctype html><html><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<style>{CSS}</style>"
            f'<script type="text/x-mathjax-config">{MATHJAX_CONFIG}</script>'
            f'<script src="{local_url}?config=TeX-AMS_SVG"></script>'
            "</head><body>" + fragment + "</body></html>")
