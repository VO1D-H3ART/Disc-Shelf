"""Offline Markdown+MathJax source safety and delimiter tests; no Qt required."""
import importlib.util
import unittest
from pathlib import Path
from math_markdown import likely_has_math, make_math_page

HAS_MD = importlib.util.find_spec('markdown_it') is not None


@unittest.skipUnless(HAS_MD, 'python3-markdown-it missing')
class MarkdownMathTests(unittest.TestCase):
    def render(self, content):
        from math_markdown import render_math_markdown
        return render_math_markdown(content)

    def test_inline_dollars(self):
        result, used = self.render('A $E=mc^2$ formula.')
        self.assertTrue(used)
        self.assertIn('class="math-inline">$E=mc^2$</span>', result)

    def test_display_dollars_multiline(self):
        result, used = self.render('$$\n\\frac{a}{b}=c\n$$')
        self.assertTrue(used)
        self.assertIn('class="math-display">$$\n\\frac{a}{b}=c\n$$</span>', result)

    def test_parenthesis_math(self):
        result, used = self.render(r'Power: \(x^2 + y^2\)')
        self.assertTrue(used)
        self.assertIn(r'\(x^2 + y^2\)', result)

    def test_bracket_math(self):
        result, used = self.render(r'\[\sum_i x_i\]')
        self.assertTrue(used)
        self.assertIn('class="math-display"', result)
        self.assertIn(r'\sum_i x_i', result)

    def test_fenced_math_remains_code(self):
        result, used = self.render('```latex\n$$x^2$$\n```')
        self.assertFalse(used)
        self.assertIn('$$x^2$$', result)

    def test_inline_code_remains_code(self):
        result, used = self.render('The literal `$$not math$$` stays code.')
        self.assertFalse(used)
        self.assertIn('$$not math$$', result)

    def test_escaped_dollar(self):
        result, used = self.render(r'The cost is \$4, not math.')
        self.assertFalse(used)
        self.assertIn('$4', result)

    def test_html_script_from_disc_is_escaped(self):
        result, used = self.render('<script>alert("evil")</script>\n\n$x$')
        self.assertTrue(used)
        self.assertNotIn('<script>', result)
        self.assertIn('&lt;script&gt;', result)

    def test_math_html_escaping(self):
        result, used = self.render('$x < y$')
        self.assertTrue(used)
        self.assertIn('x &lt; y', result)

    def test_ordinary_markdown_not_math(self):
        result, used = self.render('# Hello\n\n- **bold**')
        self.assertFalse(used)
        self.assertIn('<h1>Hello</h1>', result)


class MathPageTests(unittest.TestCase):
    def test_preflight(self):
        self.assertFalse(likely_has_math('# Heading\n\nText only'))
        self.assertTrue(likely_has_math('$$\\alpha$$'))

    def test_mathjax_is_a_local_file(self):
        html = make_math_page('BODY', Path('/usr/share/javascript/mathjax/MathJax.js'))
        self.assertIn('file:///usr/share/javascript/mathjax/MathJax.js?config=TeX-AMS_SVG', html)
        self.assertNotIn('https://', html)
        self.assertNotIn('http://', html)
        self.assertIn('BODY', html)


if __name__ == '__main__':
    unittest.main()
