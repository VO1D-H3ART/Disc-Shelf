"""Build small EPUB 2 and EPUB 3 fixtures from scratch; standard library only."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

OUTPUT = Path(__file__).parent / 'fixtures' / 'epub_library'
OUTPUT.mkdir(exist_ok=True, parents=True)

CONTAINER = '''<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>'''

CH1 = '''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Welcome</title>
<link rel="stylesheet" type="text/css" href="styles/book.css" /></head>
<body><h1>Chapter One: Welcome</h1><p>DiscShelf EPUB test collection.</p>
<p class="feature">This sentence should appear green.</p>
<p>Select and copy this sentence. No JavaScript is needed.</p>
<p><a href="chapter2.xhtml">Go to Chapter Two</a>.</p>
<img src="art/leaf.svg" alt="Green leaf logo"/></body></html>'''
CH2 = '''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Another chapter</title>
<link rel="stylesheet" href="styles/book.css"/></head><body>
<h1>Chapter Two: Styling and Navigation</h1><p>This book is entirely offline.</p>
<p style="color:#b54048">This sentence is red.</p>
<p><a href="chapter1.xhtml#top">Return to chapter one</a>.</p>
</body></html>'''
STYLE = 'body { color: #282722; background: #fffdf2; font-family: serif; margin: 3em auto; max-width: 44em; line-height: 1.6; } .feature { color: #17843c; font-weight: bold; }'
SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="60" height="60"><circle cx="30" cy="30" r="24" fill="green"/></svg>'

EPUB3_OPF = '''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">demo-v3</dc:identifier><dc:title>DiscShelf EPUB 3 Example</dc:title><dc:language>en</dc:language></metadata>
<manifest><item id="a" href="chapter1.xhtml" media-type="application/xhtml+xml"/><item id="b" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
<item id="toc" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>
<item id="style" href="styles/book.css" media-type="text/css"/>
<item id="image" href="art/leaf.svg" media-type="image/svg+xml"/></manifest>
<spine><itemref idref="a"/><itemref idref="b"/></spine></package>'''

NAV = '''<?xml version="1.0"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>Navigation</title></head><body>
<nav epub:type="toc"><h2>Contents</h2><ol><li><a href="chapter1.xhtml">Welcome</a>
<ol><li><a href="chapter1.xhtml#part">The details</a></li></ol></li>
<li><a href="chapter2.xhtml">Styling and Navigation</a></li></ol></nav>
</body></html>'''

EPUB2_OPF = '''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">demo-v2</dc:identifier><dc:title>DiscShelf EPUB 2 Example</dc:title><dc:language>en</dc:language></metadata>
<manifest><item id="a" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
<item id="b" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
<item id="style" href="styles/book.css" media-type="text/css"/>
<item id="image" href="art/leaf.svg" media-type="image/svg+xml"/></manifest>
<spine toc="ncx"><itemref idref="a"/><itemref idref="b"/></spine></package>'''

NCX = '''<?xml version="1.0"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head></head>
<docTitle><text>DiscShelf EPUB2</text></docTitle>
<navMap><navPoint id="c1" playOrder="1"><navLabel><text>Welcome</text></navLabel><content src="chapter1.xhtml"/>
<navPoint id="c1a" playOrder="2"><navLabel><text>The details</text></navLabel><content src="chapter1.xhtml#part"/></navPoint>
</navPoint><navPoint id="c2" playOrder="3"><navLabel><text>Styling and Navigation</text></navLabel><content src="chapter2.xhtml"/></navPoint></navMap></ncx>'''


def make_epub(path, version=3):
    with ZipFile(path, 'w') as z:
        z.writestr('mimetype', 'application/epub+zip', compress_type=ZIP_STORED)
        content = {
            'META-INF/container.xml': CONTAINER,
            'OEBPS/content.opf': EPUB3_OPF if version == 3 else EPUB2_OPF,
            'OEBPS/chapter1.xhtml': CH1,
            'OEBPS/chapter2.xhtml': CH2,
            'OEBPS/styles/book.css': STYLE,
            'OEBPS/art/leaf.svg': SVG,
            'OEBPS/nav.xhtml' if version == 3 else 'OEBPS/toc.ncx': NAV if version == 3 else NCX,
        }
        for k, v in content.items():
            z.writestr(k, v.encode('utf-8'), compress_type=ZIP_DEFLATED)


if __name__ == '__main__':
    make_epub(OUTPUT / 'Offline-EPUB3.epub', 3)
    make_epub(OUTPUT / 'Offline-EPUB2.epub', 2)
    print('Created EPUB test books in', OUTPUT)
