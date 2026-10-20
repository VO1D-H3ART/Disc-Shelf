#!/usr/bin/env bash
# Build a Debian package for DiscShelf v0.9.3 without PyInstaller or pip.
# Usage: ./packaging/build-deb.sh [output_directory]
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="${1:-$PROJECT_DIR/dist}"
mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

PACKAGE='discshelf'
VERSION='0.9.3-1'
ARCH='all'
OUTPUT="$OUTPUT_DIR/${PACKAGE}_${VERSION}_${ARCH}.deb"
STAGE="$(mktemp -d)"
chmod 755 "$STAGE"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p \
  "$STAGE/DEBIAN" \
  "$STAGE/usr/share/discshelf" \
  "$STAGE/usr/bin" \
  "$STAGE/usr/share/applications" \
  "$STAGE/usr/share/icons/hicolor/scalable/apps" \
  "$STAGE/usr/share/doc/discshelf"

# The application imports its modules from its script directory, not the cwd.
# Deliberately exclude tests, fixtures, pycache, and development assets.
find "$PROJECT_DIR" -maxdepth 1 -type f -name '*.py' -exec cp -- '{}' "$STAGE/usr/share/discshelf/" \;
if [[ ! -f "$STAGE/usr/share/discshelf/main.py" ]]; then
  echo 'Error: main.py missing from source directory' >&2
  exit 1
fi

cat > "$STAGE/usr/bin/discshelf" <<'LAUNCHER'
#!/bin/sh
# No daemon/autostart: launches only when explicitly invoked.
exec /usr/bin/python3 /usr/share/discshelf/main.py "$@"
LAUNCHER
chmod 755 "$STAGE/usr/bin/discshelf"

install -m 644 "$SCRIPT_DIR/discshelf.desktop" "$STAGE/usr/share/applications/discshelf.desktop"
install -m 644 "$SCRIPT_DIR/discshelf.svg" "$STAGE/usr/share/icons/hicolor/scalable/apps/discshelf.svg"
install -m 644 "$PROJECT_DIR/README.md" "$STAGE/usr/share/doc/discshelf/README.md"

cat > "$STAGE/DEBIAN/control" <<'CONTROL'
Package: discshelf
Version: 0.9.3-1
Section: office
Priority: optional
Architecture: all
Maintainer: DiscShelf Project <discshelf@localhost>
Depends: python3 (>= 3.13), python3-pyside6.qtwidgets (>= 6.8), python3-pyside6.qtpdfwidgets (>= 6.8), python3-pyside6.qtwebenginewidgets (>= 6.8), python3-markdown-it, python3-defusedxml, libjs-mathjax, libreoffice-writer
Description: Offline CD/DVD document bookshelf and reader
 DiscShelf displays files on mounted optical discs as book spines,
 searches filenames, and opens PDF, Markdown, text, HTML, EPUB, and
 Office documents with integrated viewers.
 .
 DiscShelf launches manually and does not install a background service.
CONTROL

# README and .desktop are intentionally data, not executable.
# dpkg-deb preserves user-level permissions and owners via --root-owner-group.
dpkg-deb --root-owner-group --build "$STAGE" "$OUTPUT"
echo "Built: $OUTPUT"
