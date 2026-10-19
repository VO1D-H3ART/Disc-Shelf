"""Stable document-type palette for the DiscShelf bookshelf (no Qt dependency)."""

# Extensions are lowercased by catalog.document_from_path().
SPINE_COLORS = {
    '.pdf': '#B54048',       # Red
    '.doc': '#326EB0',       # Blue
    '.docx': '#326EB0',      # Blue
    '.md': '#7851AD',        # Purple
    '.html': '#357D79',      # Teal
    '.htm': '#357D79',       # Teal
    '.txt': '#687380',       # Slate
    '.rtf': '#A86437',       # Copper
    '.odt': '#3C829D',       # Ocean blue
    '.epub': '#577B49',      # Green
}


def spine_color(extension: str) -> str:
    """Return the book-spine color, with a neutral fallback."""
    return SPINE_COLORS.get(extension.lower(), '#655E59')
