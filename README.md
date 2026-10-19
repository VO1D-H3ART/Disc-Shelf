# DiscShelf — Debian 13 bookshelf prototype

This is **milestone 1**, not the complete reader application.

## Features now
- A native Qt bookshelf with filename-labelled colored book spines.
- Filename-only, case-insensitive searching across 10 extensions:
  `.pdf`, `.docx`, `.doc`, `.md`, `.html`, `.htm`, `.txt`, `.rtf`, `.odt`, `.epub`.
- Recursive directory scanning on a worker thread (no required folder structure).
- Detection of **already mounted** CD/DVD media on launch and when inserted while the app runs.
- A manual 'Choose folder / mounted disc' button for testing and for optical media not auto-mounted by Debian.
- No files copied to the hard disk; the catalog exists in memory only.
- No network calls or services, no app autostart or background process when closed.

## Missing on purpose (subsequent milestones)
- In-app PDF, DOC/DOCX/RTF/ODT, HTML, EPUB, Markdown, and TXT readers.
- Automatic **mounting** of previously unmounted discs using UDisks2 (this version detects mounted media; it doesn't itself request a mount).
- Ejection handling refinements for media removed during an active scan.
- Full `.deb` installer and Windows build.

## Debian 13 installation

    sudo apt update
    sudo apt install python3-pyside6.qtwidgets

The package must be installed **once** ahead of offline use. After installation, running DiscShelf does not require internet access.

## Run

Open a terminal in this extracted folder:

    /usr/bin/python3 main.py

Or start it pointed at any test directory (no disc required):

    /usr/bin/python3 main.py ~/Documents

Debian might mount optical media automatically at `/media/$USER/...`. If the application doesn't detect your disc automatically, use **Choose folder / mounted disc** to choose its mountpoint.

## Test

    /usr/bin/python3 -m unittest discover -s tests -v

## Security / privacy constraints

DiscShelf currently reads filenames and directory entries only. It does not read file contents, persist a catalog, transmit data, or create a local service. Symlinks are skipped so nested links can't escape the selected directory. The document readers will need separate restrictions against external URLs, scripts, and untrusted document content.

## Notes about performance

Even a 4.7 GB DVD can contain many thousands of small files. Reading its directory tree involves optical seek latency and can take time. The background scan leaves the UI interactive; the bookshelf model contains only filenames, paths, and extensions.
