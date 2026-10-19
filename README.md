# DiscShelf v4 — PDF selection + zoom slider + Markdown / TXT readers

A **manual-launch, completely offline** Debian 13 bookshelf application. Shows documents on a CD/DVD as coloured filename-labeled spines and opens PDF, Markdown, and TXT **inside DiscShelf**. It does not install a service, index document contents, connect to the internet, or create a persistent library database.

## v4 changes

- **PDF zoom slider (25–400%)** with live percent display, `+`, `−`, and **Fit width**.
- **PDF text selection:** click-and-drag across text **on a page** to show a temporary **blue** selection overlay. Press `Ctrl+C`, use the **Copy text** button, or right-click **Copy selected text**. Does *not* write yellow highlights, annotations, or modifications to the PDF.
- **Markdown reader (`.md`):** native Qt rich-text/Markdown rendering with headings, emphasis, lists, and supported embedded images; selection and copying work like a normal text reader. Qt supports a *subset* of Markdown; particularly complex Markdown extensions may not render identically to browser Markdown engines.
- **Plain text reader (`.txt`):** monospace text, selectable and copyable. UTF-8, UTF-16 with byte-order mark, and a Windows-1252 fallback are recognized.
- Both text readers have adjustable font size. External web links cannot launch a browser; Markdown images are restricted to files beneath the currently selected root directory / disc.

## System requirements / install (Debian 13)

No new packages beyond those used by v3:

```bash
sudo apt install python3-pyside6.qtwidgets python3-pyside6.qtpdfwidgets
```

Install packages **before disconnecting the internet** if necessary; DiscShelf itself doesn't use the network.

## Run

From inside the extracted `discshelf-mvp` folder:

```bash
/usr/bin/python3 main.py
```

For an immediate test without a disc:

```bash
/usr/bin/python3 main.py tests/fixtures
```

This sample folder contains a 3-page selectable PDF, Markdown file, and plain text file.

You can alternatively open any local folder / already-mounted disc:

```bash
/usr/bin/python3 main.py ~/Documents
```

**Usage:** Single-click a red PDF spine for its reader, a purple `.md` spine for Markdown, or a slate `.txt` spine for the text reader. `Back to bookshelf` returns to the original catalog. Book titles can still be inspected on hover.

## v4 limitations

- PDF selection works with actual text embedded in PDFs. **Scanned image-only PDFs need OCR**, which is *not* included.
- To avoid misleading cross-page selection, PDF drag-selection is currently **limited to one page at a time**. PDF scrolling remains multi-page.
- In Qt 6.8's QWidget PDF reader, normal text selection isn't native. We add a selectable QPdfView layer based on the Qt PDF page-layout calculations. Its selection geometry should be visually tested on your Debian screen, especially at custom scaling / DPI.
- Markdown uses Qt's native Markdown subset rather than a browser. Some advanced syntax (and full CSS layout) isn't supported. Markdown images cannot use network addresses and can only reference supported image types on the same selected disc / folder.
- Markdown/TXT files larger than **16 MiB** cannot be opened by the current simple text reader. This limit prevents locking up old 4 GB laptops with giant text layouts; it doesn't restrict PDFs.
- `.doc`, `.docx`, `.htm`, `.html`, `.rtf`, `.odt`, `.epub` are still indexed as book spines but don't have readers yet.
- DiscShelf detects **already mounted** discs, not unmounted ones. Debian may need to mount the disc first, or you can manually choose its mounted directory.
- No auto-start/daemon. Disc checks occur every 3 seconds **only while the DiscShelf window is running**.

## Design notes

- All original documents stay where they are; **no copies or modifications**.
- Filename-only scanning; metadata catalog is in RAM and cleared on disc removal or app exit.
- The larger Qt PDF component is imported only when a PDF opens.
- The Markdown/TXT viewer uses Qt Widgets; it does **not** require Qt WebEngine / Chromium.
- Large or corrupted files should be closed with **Back to bookshelf** before ejecting a disc.

## Tests

```bash
/usr/bin/python3 -m unittest discover -s tests -v
```

Unit tests run without a GUI; the PDF and text reader smoke tests require installed PySide6 and a graphical session. Check PDF selection with the included sample: select some text, confirm a blue overlay appears, and press `Ctrl+C` to test the clipboard.

## Files

| File | Role |
|---|---|
| `main.py` | Bookshelf UI, scanning, reader dispatch |
| `pdf_reader.py` | Page navigation + zoom slider + copy button |
| `pdf_selection.py` | Blue PDF mouse text selection and clipboard |
| `text_reader.py` | Markdown/TXT native Qt reader |
| `text_format.py` | Text encoding fallback and memory guard |
| `catalog.py` | Ten document extensions, names and paths |
| `book_colors.py` | Book spine colors |
| `disc_detection.py` | Mounted optical-drive detection |
| `tests/` | Catalog/reader tests, example files |
