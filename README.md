# DiscShelf v0.9.3 — PDF slider handle spacing

**Debian 13 (Trixie)** | Offline bookshelf | **Manual launch** | No resident service

DiscShelf discovers filenames on **already mounted** CDs/DVDs (or an explicitly selected folder) and displays them as colored book spines. Search filters **filenames only**. Files are read on demand when selected. No permanent catalog is written to disk, and the application only polls for mounted optical media *while the window is open*.

## NEW — PDF navigation improvements (v9.2)

The standalone Previous page button has been removed. The PDF page number
field remains directly editable: type a number and press Enter to jump there.
Its two small in-field buttons now show clear arrows: **▲ decreases** the page
number and **▼ increases** the page number. Keyboard Up/Down and wheel stepping
are reversed consistently. Arrows are disabled at the first/last page.

This release also retains the EPUB XML metadata compatibility improvements
introduced in v9.1.

## EPUB metadata compatibility fix (v9.1)

EPUB 2 NCX and EPUB 3 navigation documents may contain normal XML declarations
and `<!DOCTYPE ...>` headers. v9 mistakenly rejected these with the message
“EPUB metadata contains unsupported XML declarations.” v9.1 accepts these
standard declarations while continuing to reject XML entity declarations and
external entity expansion via `defusedxml`. No data is fetched from DTD URLs.

This adds one small Debian dependency: `python3-defusedxml`. If it is missing,
EPUB opening shows an installation instruction rather than preventing DiscShelf
from launching. The PDF, Markdown, TXT, HTML, and Office readers are unchanged.

## EPUB reader

Green `.epub` spines now open in DiscShelf. The reader provides:

- EPUB 2 (NCX) and EPUB 3 (navigation XHTML) table of contents, with indented nested sections.
- **Previous chapter** / **Next chapter** buttons, a clickable table of contents, a zoom slider (50–200%), text selection and Ctrl+C.
- Styled XHTML/HTML pages, embedded images, local CSS and fonts; internal chapter links and anchor links.
- Fully local viewing with **JavaScript disabled**, request interception for all non-book files/network resources, and an anonymous **in-memory-only WebEngine profile**.
- A background worker that extracts *only renderable* selected-book resources to a **tmpfs** (RAM-backed) directory. The book's ZIP, XML package, and reading order are validated first. All temporary files are deleted when returning to the bookshelf, changing discs, or exiting normally.
- EPUB ZIP entry limits, no symbolic links or path traversal, and limits on compressed/unpacked sizes to reduce memory exhaustion on older computers.

The original EPUB stays on the disc and is never changed. EPUB metadata parsing also uses the lightweight `python3-defusedxml` package for secure compatibility with standard XML declarations and DOCTYPE headers. The EPUB reader does not use MathJax or run any scripts from a book.

### Supported formats — complete

| Extension | Book spine | Integrated reader |
|---|---|---|
| `.pdf` | Red | Qt PDF, zoom and selection |
| `.doc`, `.docx` | Blue | LibreOffice Writer → RAM-based PDF preview |
| `.md` | Purple | Native Markdown or offline MathJax for math; colored spans |
| `.html`, `.htm` | Teal | Offline HTML/CSS, no document JavaScript |
| `.txt` | Slate | Selectable native text reader |
| `.rtf` | Copper | LibreOffice Writer → RAM-based PDF preview |
| `.odt` | Ocean blue | LibreOffice Writer → RAM-based PDF preview |
| `.epub` | Green | **EPUB 2/3 chapters and table of contents** |

All **10 extensions** now have integrated readers.

## Install dependencies (Debian 13)

From your Debian package repository while online (or use pre-downloaded local packages):

```bash
sudo apt install python3-pyside6.qtwidgets python3-pyside6.qtpdfwidgets \
  python3-pyside6.qtwebenginewidgets python3-markdown-it libjs-mathjax \
  libreoffice-writer python3-defusedxml
```

These are dependencies for the complete application, not services started at login. DiscShelf itself **never needs the internet to open a disc**.

## Run

Extract the ZIP archive. From inside `discshelf-mvp/`:

```bash
/usr/bin/python3 main.py
```

To test four bundled sample EPUBs (including two with standard DOCTYPE declarations; all have two chapters, a TOC, local color styling, links, and an embedded SVG):

```bash
/usr/bin/python3 main.py tests/fixtures/epub_library
```

Try `Offline-EPUB3-DOCTYPE.epub` and `Offline-EPUB2-DOCTYPE.epub` to confirm the v9 XML fix, or the original `Offline-EPUB3.epub` and `Offline-EPUB2.epub`. All appear as green spines. Verify:

1. The chapter title and green styled sentence display properly.
2. The table of contents includes **Welcome**, **The details**, and **Styling and Navigation**.
3. Previous/Next chapter and TOC links work, including chapters with anchors.
4. The zoom slider changes the text size; selecting and copying text works.
5. Back to bookshelf cleans up the temporary book.

You can also browse other fixtures with `main.py tests/fixtures`.

## Resource and compatibility limits

- EPUB archives up to **256 MiB compressed**, **384 MiB of extracted eligible resources**, **4,000 ZIP entries**, and **64 MiB per renderable resource**. These limits are deliberate for 4 GB laptops. Extraction uses RAM-backed tmpfs only, and is cancelled when leaving or closing the app. Large or damaged books will display a friendly error rather than trying to use all available RAM.
- The reader supports ordinary, **unprotected EPUB 2/3 books**. DRM/encrypted/obfuscated resources, interactive JavaScript books, media overlays, embedded audio/video, and complex EPUB fixed-layout semantics are not supported in v9. Most reflowable text-based ebooks should display well, though rendering is not guaranteed to exactly match every publisher's preferred application.
- The app uses `/run/user/$UID` or `/dev/shm` **only if verified as tmpfs**. If neither exists it will refuse EPUB extraction rather than silently writing document contents to a persistent `/tmp` directory. Note: the Linux kernel may swap tmpfs pages if swapping is enabled; DiscShelf never explicitly stores a persistent copy.
- The PDF / HTML / Markdown / TXT / Word readers retain their previous behavior. For Office files, LibreOffice must be installed; its conversion has some font/layout limitations. The LibreOffice subprocess is not yet placed in a kernel-enforced network sandbox.
- **Automatic mounting is still planned.** This release detects optical discs that Debian has *already mounted*, or you can select a folder manually. It does not start a background daemon or autostart when a disc is inserted.

## Tests

```bash
python -m unittest discover -s tests -v
```

The test suite includes EPUB 2/3 parsing, standard XML DOCTYPE compatibility, malicious XML entity rejection, and temporary cleanup, unsafe-path and encrypted archive rejection, previous readers, and real LibreOffice conversion fixtures where available. Qt GUI tests require a graphical Debian session and the PySide6 packages. The release was not visually tested on a physical Debian laptop in the packaging environment; check the UI and EPUB CSS/link rendering on your machine.

## Source overview

- `main.py`: bookshelf and integrated reader routing
- `epub_archive.py`: EPUB2/3 metadata, safe archive handling and RAM extraction
- `epub_loading.py`: cancellable background book preparation
- `epub_reader.py`: table of contents, chapter navigation, offline Qt rendering
- `html_reader.py` / `html_policy.py`: shared offline WebEngine policy, including EPUB `.xhtml`
- `office_conversion.py`: shared tmpfs verification and Office PDF converter
- `tests/fixtures/epub_library/`: example EPUB2 and EPUB3 books


### v0.9.3 UI fix

The PDF zoom slider now has a 24-pixel minimum height to prevent the circular handle from being clipped at the top. The global Qt slider stylesheet and the HTML/EPUB controls are unchanged.
