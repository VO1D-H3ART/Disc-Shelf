"""Safety and rendering regressions for DiscShelf coloured Markdown spans."""
import unittest
import importlib.util
from markdown_colors import render_colored_markdown
from math_markdown import render_math_markdown


@unittest.skipUnless(importlib.util.find_spec('markdown_it') is not None,
                     'python3-markdown-it missing')
class ColorMarkdownTests(unittest.TestCase):
    def test_standard_color_span(self):
        html, used = render_colored_markdown('Hello <span style="color: red">red</span> world.')
        self.assertTrue(used)
        self.assertIn('<span style="color: red">red</span>', html)
        self.assertNotIn('&lt;span', html)

    def test_hex_color_and_markdown_formatting(self):
        html, used = render_colored_markdown("<span style='color: #a08F3D'>**Bold**</span>")
        self.assertTrue(used)
        self.assertIn('<span style="color: #a08F3D"><strong>Bold</strong></span>', html)

    def test_rgb_and_hsl_colors(self):
        html, used = render_colored_markdown(
            '<span style="color: rgb(255, 0, 0)">Red</span> '
            '<span style="color: hsl(270, 50%, 40%)">Purple</span>')
        self.assertTrue(used)
        self.assertIn('color: rgb(255, 0, 0)', html)
        self.assertIn('color: hsl(270, 50%, 40%)', html)

    def test_nested_spans(self):
        html, used = render_colored_markdown(
            '<span style="color: blue">Outer <span style="color: green">Inner</span> tail</span>')
        self.assertTrue(used)
        self.assertIn('color: blue">Outer <span style="color: green">Inner</span> tail</span>', html)

    def test_unclosed_spans_escaped(self):
        html, used = render_colored_markdown('<span style="color: green">Unclosed')
        self.assertFalse(used)
        self.assertIn('&lt;span', html)

    def test_rejects_unsafe_color_and_drops_other_attrs(self):
        html, used = render_colored_markdown(
            '<span style="color: red; background: url(https://example.org)" '
            'onmouseenter="alert(1)">safe</span>')
        self.assertTrue(used)
        self.assertIn('<span style="color: red">safe</span>', html)
        self.assertNotIn('onmouseenter', html)
        self.assertNotIn('background:', html)
        html, used = render_colored_markdown(
            '<span style="color: url(javascript:evil)">bad</span>')
        self.assertFalse(used)
        self.assertIn('&lt;span', html)

    def test_disallows_other_raw_html(self):
        html, _ = render_colored_markdown(
            '<span style="color: teal">safe</span><script>alert(1)</script>')
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>', html)

    def test_code_shows_literal_spans(self):
        html, used = render_colored_markdown('`<span style="color: red">code</span>`')
        self.assertFalse(used)
        self.assertIn('&lt;span', html)
        self.assertIn('<code>', html)

    def test_math_and_colored_text_together(self):
        html, has_math = render_math_markdown(
            '<span style="color: purple">Equation $E=mc^2$</span>')
        self.assertTrue(has_math)
        self.assertIn('<span style="color: purple">Equation ', html)
        self.assertIn('class="math-inline">$E=mc^2$</span></span>', html)

    def test_math_and_malicious_html_together(self):
        html, has_math = render_math_markdown(
            '<span style="color:#F70">Note</span> $x$ <img src=x onerror=alert(1)>')
        self.assertTrue(has_math)
        self.assertIn('<span style="color: #F70">Note</span>', html)
        self.assertIn('&lt;img', html)


if __name__ == '__main__':
    unittest.main()
