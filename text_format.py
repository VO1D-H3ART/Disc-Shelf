"""Dependency-free decoding rules for text documents."""
MAX_TEXT_BYTES = 16 * 1024 * 1024


def decode_text(contents: bytes) -> str:
    """Handle UTF-8, UTF-16 BOM and typical legacy Windows text files."""
    if contents.startswith((b'\xff\xfe', b'\xfe\xff')):
        return contents.decode('utf-16')
    try:
        return contents.decode('utf-8-sig')
    except UnicodeDecodeError:
        return contents.decode('cp1252', errors='replace')
