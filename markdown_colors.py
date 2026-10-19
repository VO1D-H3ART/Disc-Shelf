"""Safe, lightweight Markdown inline colour spans.

Allow user documents to colour text using only the CSS ``color`` property:
    <span style="color: #e63946">Important</span>

This is deliberately NOT general HTML support. MarkdownIt's HTML parsing remains
OFF; other HTML tags are escaped, event handlers are discarded, and no disc
scripts or stylesheets execute. Shared by native Qt and MathJax Markdown views.
"""

import re
from html import escape

_OPEN = re.compile(r'<span\b([^<>]{0,1024})>', re.IGNORECASE)
_CLOSE = re.compile(r'</span\s*>', re.IGNORECASE)
_STYLE = re.compile(r'(?<![\w-])style\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))', re.IGNORECASE)
_HEX = re.compile(r'\#(?:[a-fA-F0-9]{3}|[a-fA-F0-9]{4}|[a-fA-F0-9]{6}|[a-fA-F0-9]{8})\Z')
_NAME = re.compile(r'[a-zA-Z]{1,30}\Z')
_RGB = re.compile(r'rgba?\(\s*[\d.%\s,]+\)\Z', re.IGNORECASE)
_HSL = re.compile(r'hsla?\(\s*[\d.%\s,]+\)\Z', re.IGNORECASE)


def _validated_color(attributes: str) -> str | None:
    style = _STYLE.search(attributes)
    if not style:
        return None
    declarations = next((group for group in style.groups() if group is not None), '')
    if len(declarations) > 512:
        return None
    value = None
    for declaration in declarations.split(';'):
        key, sep, candidate = declaration.partition(':')
        if sep and key.strip().lower() == 'color':
            value = candidate.strip()
    if not value or len(value) > 80:
        return None
    if not any(regex.fullmatch(value) for regex in (_HEX, _NAME, _RGB, _HSL)):
        return None
    return value


def _color_span_rule(state, silent: bool) -> bool:
    """Insert only sanitized span tags into MarkdownIt's HTML-disabled stream."""
    pos = state.pos
    if state.src[pos:pos + 2] != '</' and state.src[pos:pos + 5].lower() != '<span':
        return False
    if state.src.startswith('</', pos):
        match = _CLOSE.match(state.src, pos)
        if not match or not getattr(state, '_discshelf_color_stack', None):
            return False
        if not silent:
            state._discshelf_color_stack.pop()
            token = state.push('html_inline', '', 0)
            token.content = '</span>'
        state.pos = match.end()
        return True

    match = _OPEN.match(state.src, pos)
    if not match:
        return False
    color = _validated_color(match.group(1))
    if color is None:
        return False
    # Do not colour the rest of a paragraph accidentally with an unclosed span.
    if not _CLOSE.search(state.src, match.end()):
        return False
    if not silent:
        if not hasattr(state, '_discshelf_color_stack'):
            state._discshelf_color_stack = []
        state._discshelf_color_stack.append(color)
        token = state.push('html_inline', '', 0)
        token.content = '<span style="color: ' + escape(color, quote=True) + '">'
    state.pos = match.end()
    return True


def enable_safe_colors(parser) -> None:
    """Install before ordinary Markdown escaping; never enable raw HTML."""
    parser.inline.ruler.before('escape', 'discshelf_color_span', _color_span_rule)


def render_colored_markdown(source: str) -> tuple[str, bool]:
    """Return sanitized HTML and whether usable coloured spans were produced."""
    from markdown_it import MarkdownIt

    parser = MarkdownIt('commonmark', {'html': False, 'linkify': False})
    parser.enable('table')
    parser.enable('strikethrough')
    enable_safe_colors(parser)
    fragment = parser.render(source)
    return fragment, '<span style="color: ' in fragment
