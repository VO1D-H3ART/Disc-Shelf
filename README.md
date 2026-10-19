# DiscShelf v6 — Coloured Markdown + Offline MathJax

DiscShelf is a **manual-launch, fully offline** CD/DVD bookshelf for Debian 13. It scans **filenames only**, draws coloured book spines, and opens supported documents without launching external viewers. There is **no autostart, background daemon, document database, or network access**.

## v6: Inline Markdown text colours (FIX)

Inline HTML-style `<span>` text colours now render as actual colours, **not literal tags**, in both Markdown readers:

```markdown
This is <span style="color: red">red text</span>.
This is <span style="color: #4f46e5">indigo text</span>.
And this is <span style="color: forestgreen">**bold green text**</span>.
```

Supports named CSS colours, hex colours (`#RGB`, `#RRGGBB`, etc.) and basic `rgb()`/`hsl()` colour values. Other inline style properties and HTML attributes are deliberately discarded. Arbitrary source HTML, including `<script>` tags, continues to display as inert, escaped text for safety. Document-supplied JS cannot execute.

**Lightweight by default:** a Markdown file with colours but *without mathematics* uses the native Qt reader rather than starting Qt WebEngine. Math-containing files use the existing offline MathJax reader, now with coloured text too.

For a quick test:

```bash
/usr/bin/python3 main.py tests/fixtures
```

Click `colored_notes.md` to test the native Markdown renderer and `equations.md` to test MathJax plus inline coloured text. No additional packages are required if v5 dependencies were installed.

## Mathematical equations in Markdown

The Markdown reader also recognizes and typesets:

- Inline `$E=mc^2$` and `\(E=mc^2\)`
- Display math between `$$...$$` or `\[...\]` (including multiline equations)
- Common LaTeX such as `\frac`, `\sqrt`, `\int`, `\sum`, Greek letters, and superscripts/subscripts
- Regular Markdown headings, lists, tables, fenced code blocks, images, bold and italic alongside math

**Code blocks are preserved:** `$$...$$` appearing inside a fenced code block or inline backticks is shown as code, not rendered as an equation. Markdown filenames and the bookshelf behave exactly as in v4.

**Fully offline:** MathJax is loaded **from Debian's installed files** (`/usr/share/javascript/mathjax/MathJax.js`), not from a CDN. All HTTP/HTTPS/network requests from its Markdown page are blocked. Markdown HTML is escaped to prevent scripts from a DVD running. Only *application-controlled* JavaScript is enabled in the MathJax reader because MathJax itself requires it; the planned HTML reader will remain HTML/CSS-only, with disc JavaScript disabled.

**Memory-conscious:** Markdown without real equations continues to use the lightweight native Qt text reader. Qt WebEngine starts only if a Markdown document contains supported math. The browser is disposable and uses a private, off-the-record profile with no disk cache/cookies. MathJax rendering will use more RAM than the regular Markdown reader, so test on your 4 GB laptop.

## Installing on Debian 13

If you already installed the PDF and Qt Widget dependencies for v4, the new dependencies are:

```bash
sudo apt install python3-pyside6.qtwebenginewidgets python3-markdown-it libjs-mathjax
```

For a fresh install of DiscShelf's currently implemented readers:

```bash
sudo apt install python3-pyside6.qtwidgets python3-pyside6.qtpdfwidgets \
  python3-pyside6.qtwebenginewidgets python3-markdown-it libjs-mathjax
```

These can be installed via Debian's normal package manager before disconnecting from the internet. Once installed, **DiscShelf never needs internet access** to run or render equations. No Node.js service and no CDN are used.

## Run / test

Extract this ZIP and, in `discshelf-mvp/`, run:

```bash
/usr/bin/python3 main.py tests/fixtures
```

Click **equations.md** (purple spine). Expected examples include an inline equation (`E = mc²`) and a displayed integral and infinite sum. A file with ordinary Markdown and no equations keeps the v4 native reader. PDF/TXT features are unchanged.

To scan a folder or already-mounted CD/DVD:

```bash
/usr/bin/python3 main.py ~/Documents
```

Without a path, launch manually using:

```bash
/usr/bin/python3 main.py
```

Optical-disc detection only runs while this window is open. Debian must already mount the disc; automatic mounting is not implemented yet.

**If the equation reader displays a blank screen on very old graphics hardware:** try software rendering:

```bash
QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu /usr/bin/python3 main.py tests/fixtures
```

## Readers and file types

- PDF: integrated Qt PDF viewer, page navigation, zoom slider, text selection/copy.
- MD: native Qt viewer for ordinary Markdown; MathJax in a locked-down local WebEngine for math-containing Markdown.
- TXT: native selectable and copyable plain-text viewer.
- The remaining seven extensions (`.doc`, `.docx`, `.html`, `.htm`, `.rtf`, `.odt`, `.epub`) appear on the shelf, but **their readers are not implemented yet**.
- Filename-only search, no content indexing, no permanent document copies.
- TXT/Markdown source size limit 16 MiB; MathJax HTML page limit about 1.75 MB due to Qt `setHtml` constraints. Large math-heavy documents may require future chunking.

## Tests

Run:

```bash
/usr/bin/python3 -m unittest discover -s tests -v
```

The parser and catalog tests run without a graphical desktop. PDF/Qt WebEngine visual rendering must be validated on Debian 13; this archive has not been graphically exercised in this development environment.

## Project files

| File | Purpose |
|---|---|
| `main.py` | Bookshelf GUI, folder/disc scanning, reader selection |
| `pdf_reader.py` + `pdf_selection.py` | PDF rendering and text selection |
| `text_reader.py` | Lightweight Markdown/TXT reader and on-demand math reader integration |
| `math_markdown.py` | Safe Markdown-to-HTML conversion and LaTeX delimiter preservation |
| `markdown_colors.py` | Safe HTML-style inline text-colour support for Markdown |
| `math_reader.py` | Offline WebEngine view, MathJax integration, network/file restrictions |
| `catalog.py` + `book_colors.py` | All 10 file types and spine colors |
| `disc_detection.py` | Mounted optical-disc detection |
| `tests/fixtures/equations.md` | MathJax demo |

**Important:** MathJax uses locally installed scripts and only app-controlled script configuration. DiscShelf does not run JavaScript provided by files on a CD/DVD.
