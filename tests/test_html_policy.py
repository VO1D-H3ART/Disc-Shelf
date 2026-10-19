"""Offline HTML allowlist regression tests; do not require a Qt installation."""
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote
from html_policy import HTML_EXTENSIONS, is_allowed_url, safe_file_url, safe_local_file


class HtmlPolicyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name, 'disc')
        (self.root / 'assets').mkdir(parents=True)
        self.index = self.root / 'index.html'
        self.index.write_text('<h1>Hello</h1>', encoding='utf-8')
        self.chapter = self.root / 'Chapter 2.HTM'
        self.chapter.write_text('<p>Chapter 2</p>', encoding='utf-8')
        self.css = self.root / 'assets' / 'style.css'
        self.css.write_text('body{color:red}', encoding='utf-8')
        self.image = self.root / 'assets' / 'image.svg'
        self.image.write_text('<svg/>', encoding='utf-8')
        self.js = self.root / 'assets' / 'injected.js'
        self.js.write_text('alert(1)', encoding='utf-8')
        self.outside = Path(self.temp.name, 'private.html')
        self.outside.write_text('secret', encoding='utf-8')

    def test_local_html_allowed_for_navigation(self):
        self.assertTrue(is_allowed_url(self.index.as_uri(), self.root, navigation=True))
        self.assertTrue(is_allowed_url(self.chapter.as_uri() + '#top', self.root, navigation=True))

    def test_local_css_and_images_allowed_only_as_resources(self):
        self.assertTrue(is_allowed_url(self.css.as_uri(), self.root))
        self.assertTrue(is_allowed_url(self.image.as_uri(), self.root))
        self.assertFalse(is_allowed_url(self.css.as_uri(), self.root, navigation=True))
        self.assertTrue(is_allowed_url('data:image/png;base64,AAA=', self.root))
        self.assertFalse(is_allowed_url('data:text/html,hello', self.root, navigation=True))

    def test_never_allow_network_or_scripts(self):
        for url in ('https://example.org/', 'http://example.org/a.css',
                    'ftp://example.org/a.png', 'javascript:alert(1)',
                    'ws://example.org/socket', 'file://evilhost/share/a.html'):
            with self.subTest(url=url):
                self.assertFalse(is_allowed_url(url, self.root))
                self.assertFalse(is_allowed_url(url, self.root, navigation=True))
        self.assertFalse(is_allowed_url(self.js.as_uri(), self.root))

    def test_cannot_read_files_outside_root(self):
        self.assertFalse(is_allowed_url(self.outside.as_uri(), self.root))
        self.assertFalse(is_allowed_url(self.outside.as_uri(), self.root, navigation=True))
        self.assertFalse(safe_local_file(self.outside, self.root, HTML_EXTENSIONS))

    def test_cannot_escape_via_symlink(self):
        (self.root / 'escape.htm').symlink_to(self.outside)
        self.assertFalse(is_allowed_url((self.root / 'escape.htm').as_uri(), self.root))

    def test_cannot_open_missing_resource(self):
        self.assertFalse(safe_file_url((self.root / 'missing.html').as_uri(), self.root))

    def test_encoded_spaces_and_case_insensitivity(self):
        url = self.chapter.as_uri()
        self.assertIn('%20', url)
        self.assertTrue(safe_file_url(url, self.root))
        self.assertTrue(safe_local_file(self.chapter, self.root, HTML_EXTENSIONS))


if __name__ == '__main__':
    unittest.main()
