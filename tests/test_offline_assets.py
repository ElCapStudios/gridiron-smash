import unittest
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SCRIPTS = ["vendor/three.min.js", "game.js"]


class ScriptSourceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []
        self.has_base_href = False
        self.has_script_href = False
        self.has_inline_script = False
        self.has_foreign_markup = False
        self.has_inline_event_handler = False
        self.has_srcdoc = False
        self.has_embedded_document = False
        self.has_active_script_url = False
        self.has_unknown_declaration = False
        self.has_markup_in_comment = False

    def handle_starttag(self, tag, attrs):
        if tag in ("svg", "math"):
            self.has_foreign_markup = True
        if tag in ("iframe", "frame", "object", "embed"):
            self.has_embedded_document = True
        for name, value in attrs:
            if name.startswith("on"):
                self.has_inline_event_handler = True
            if name == "srcdoc":
                self.has_srcdoc = True
            if value is not None:
                normalized = value.translate(
                    str.maketrans("", "", "\t\r\n")
                ).lstrip("".join(chr(code) for code in range(0x21))).lower()
                if normalized.startswith(("javascript:", "data:text/html")):
                    self.has_active_script_url = True
        if tag == "base" and any(name == "href" for name, _ in attrs):
            self.has_base_href = True
        if tag == "script":
            if any(name in ("href", "xlink:href") for name, _ in attrs):
                self.has_script_href = True
            for name, source in attrs:
                if name == "src":
                    self.sources.append(source or "")
                    break
            else:
                self.has_inline_script = True

    def unknown_decl(self, data):
        self.has_unknown_declaration = True

    def handle_comment(self, data):
        if "<" in data:
            self.has_markup_in_comment = True


def local_script_sources(markup, root):
    parser = ScriptSourceParser()
    parser.feed(markup)
    has_unprocessed_markup = bool(parser.rawdata)
    parser.close()
    if has_unprocessed_markup:
        raise ValueError("incomplete markup at end of document")
    if parser.has_markup_in_comment:
        raise ValueError("markup inside comments is not allowed")
    if parser.has_base_href:
        raise ValueError("base href is not allowed for offline scripts")
    if parser.has_inline_event_handler:
        raise ValueError("inline event handlers are not allowed for offline scripts")
    if parser.has_srcdoc:
        raise ValueError("srcdoc is not allowed for offline scripts")
    if parser.has_embedded_document:
        raise ValueError("embedded documents are not allowed in offline scripts")
    if parser.has_active_script_url:
        raise ValueError("active script URLs are not allowed in offline scripts")
    if parser.has_unknown_declaration:
        raise ValueError("unknown markup declarations are not allowed in offline scripts")
    if parser.has_script_href:
        raise ValueError("script href is not allowed for offline scripts")
    if parser.has_foreign_markup:
        raise ValueError("SVG and MathML are not allowed in offline scripts")
    if parser.has_inline_script:
        raise ValueError("scripts must use a local src")
    base = root.resolve()

    for source in parser.sources:
        url = urlsplit(source)
        if (
            url.scheme
            or url.netloc
            or not url.path
            or url.path.startswith("/")
        ):
            raise ValueError("script source must be a local relative path")

        target = (base / unquote(url.path)).resolve()
        try:
            target.relative_to(base)
        except ValueError as exc:
            raise ValueError("script source must stay inside the repository") from exc
        if not target.is_file():
            raise ValueError("script source does not name a local file")

    return parser.sources


def game_script_sources(markup, root):
    sources = local_script_sources(markup, root)
    if sources != EXPECTED_SCRIPTS:
        raise ValueError("game scripts must load Three.js before game.js")
    return sources


class OfflineAssetTests(unittest.TestCase):
    def test_game_loads_local_scripts_in_dependency_order(self):
        markup = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertEqual(
            EXPECTED_SCRIPTS,
            game_script_sources(markup, ROOT),
        )

    def test_rejects_a_remote_script(self):
        markup = '<script src="https://cdn.example.test/game.js"></script>'
        with self.assertRaisesRegex(ValueError, "local relative path"):
            local_script_sources(markup, ROOT)

    def test_rejects_a_protocol_relative_script(self):
        markup = '<script src="//cdn.example.test/game.js"></script>'
        with self.assertRaisesRegex(ValueError, "local relative path"):
            local_script_sources(markup, ROOT)

    def test_rejects_a_base_href(self):
        markup = (
            '<base href="https://cdn.example.test/">'
            '<script src="vendor/three.min.js"></script>'
            '<script src="game.js"></script>'
        )
        with self.assertRaisesRegex(ValueError, "base href"):
            game_script_sources(markup, ROOT)

    def test_rejects_svg_script_href(self):
        for attribute in ("href", "xlink:href"):
            with self.subTest(attribute=attribute):
                markup = (
                    '<script src="vendor/three.min.js"></script>'
                    '<script src="game.js"></script>'
                    f'<svg><script {attribute}="https://cdn.example.test/x.js">'
                    "</script></svg>"
                )
                with self.assertRaisesRegex(ValueError, "script href"):
                    game_script_sources(markup, ROOT)

    def test_rejects_inline_module_script(self):
        markup = (
            '<script src="vendor/three.min.js"></script>'
            '<script src="game.js"></script>'
            '<script type="module">'
            'import "https://cdn.example.test/x.js";'
            "</script>"
        )
        with self.assertRaisesRegex(ValueError, "local src"):
            game_script_sources(markup, ROOT)

    def test_rejects_inline_event_handlers(self):
        scripts = (
            '<script src="vendor/three.min.js"></script>'
            '<script src="game.js"></script>'
        )
        handlers = (
            '<body onload="import(\'https://cdn.example.test/x.js\')"></body>',
            '<img src="pixel.png" onerror="import(\'https://cdn.example.test/x.js\')">',
        )
        for markup in handlers:
            with self.subTest(markup=markup):
                with self.assertRaisesRegex(ValueError, "inline event handlers"):
                    game_script_sources(scripts + markup, ROOT)

    def test_rejects_iframe_srcdoc(self):
        markup = (
            '<script src="vendor/three.min.js"></script>'
            '<script src="game.js"></script>'
            '<iframe srcdoc="&lt;script src=&quot;https://cdn.example.test/x.js&quot;'
            '&gt;&lt;/script&gt;"></iframe>'
        )
        with self.assertRaisesRegex(ValueError, "srcdoc"):
            game_script_sources(markup, ROOT)

    def test_rejects_embedded_document_elements(self):
        scripts = (
            '<script src="vendor/three.min.js"></script>'
            '<script src="game.js"></script>'
        )
        elements = (
            '<iframe src="https://cdn.example.test/page"></iframe>',
            '<frame src="https://cdn.example.test/page">',
            '<object data="https://cdn.example.test/page"></object>',
            '<embed src="https://cdn.example.test/page">',
        )
        for element in elements:
            with self.subTest(element=element):
                with self.assertRaisesRegex(ValueError, "embedded documents"):
                    game_script_sources(scripts + element, ROOT)

    def test_rejects_javascript_and_html_data_urls(self):
        scripts = (
            '<script src="vendor/three.min.js"></script>'
            '<script src="game.js"></script>'
        )
        links = (
            '<a href="  JaVaScRiPt:import(\'https://cdn.example.test/x.js\')">run</a>',
            '<a href="\x01javascript:import(\'https://cdn.example.test/x.js\')">run</a>',
            '<a href="data:text/html,%3Cscript%20src=https%3A%2F%2Fcdn.example.test%2Fx.js%3E%3C%2Fscript%3E">open</a>',
        )
        for link in links:
            with self.subTest(link=link):
                with self.assertRaisesRegex(ValueError, "active script URLs"):
                    game_script_sources(scripts + link, ROOT)

    def test_rejects_cdata_markup_declarations(self):
        markup = (
            '<script src="vendor/three.min.js"></script>'
            '<script src="game.js"></script>'
            '<![CDATA[ x ><script src="https://cdn.example.test/x.js"></script>]]>'
        )
        with self.assertRaisesRegex(ValueError, "unknown markup declarations"):
            game_script_sources(markup, ROOT)

    def test_rejects_unterminated_cdata_markup(self):
        markup = (
            '<script src="vendor/three.min.js"></script>'
            '<script src="game.js"></script>'
            '<![CDATA[><script src="https://cdn.example.test/x.js"></script>'
        )
        with self.assertRaisesRegex(ValueError, "incomplete markup"):
            game_script_sources(markup, ROOT)

    def test_rejects_malformed_comments_that_hide_scripts(self):
        scripts = (
            '<script src="vendor/three.min.js"></script>'
            '<script src="game.js"></script>'
        )
        comments = (
            '<!--><script src="https://cdn.example.test/x.js"></script>-->',
            '<!-- x --!><script src="https://cdn.example.test/x.js"></script>-->',
        )
        for comment in comments:
            with self.subTest(comment=comment):
                with self.assertRaises(ValueError):
                    game_script_sources(scripts + comment, ROOT)

    def test_rejects_svg_and_mathml_markup(self):
        scripts = (
            '<script src="vendor/three.min.js"></script>'
            '<script src="game.js"></script>'
        )
        nested_scripts = {
            "svg": '<style><script href="https://cdn.example.test/x.js">'
            "</script></style>",
            "math": '<style><script>import("https://cdn.example.test/x.js")'
            "</script></style>",
        }
        for tag, nested_script in nested_scripts.items():
            with self.subTest(tag=tag):
                markup = f"{scripts}<{tag}>{nested_script}</{tag}>"
                with self.assertRaisesRegex(ValueError, "SVG and MathML"):
                    game_script_sources(markup, ROOT)

    def test_rejects_an_absolute_script_path(self):
        markup = '<script src="/game.js"></script>'
        with self.assertRaisesRegex(ValueError, "local relative path"):
            local_script_sources(markup, ROOT)

    def test_uses_the_first_duplicate_script_source(self):
        markup = (
            '<script src="https://cdn.example.test/game.js" src="game.js"></script>'
        )
        with self.assertRaisesRegex(ValueError, "local relative path"):
            local_script_sources(markup, ROOT)

    def test_rejects_a_path_outside_the_repository(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "site"
            root.mkdir()
            markup = '<script src="../outside.js"></script>'
            with self.assertRaisesRegex(ValueError, "stay inside the repository"):
                local_script_sources(markup, root)

    def test_rejects_a_missing_local_script(self):
        with TemporaryDirectory() as directory:
            markup = '<script src="missing.js"></script>'
            with self.assertRaisesRegex(ValueError, "local file"):
                local_script_sources(markup, Path(directory))

    def test_rejects_reversed_dependency_order(self):
        markup = (
            '<script src="game.js"></script>'
            '<script src="vendor/three.min.js"></script>'
        )
        with self.assertRaisesRegex(ValueError, "Three.js before game.js"):
            game_script_sources(markup, ROOT)


if __name__ == "__main__":
    unittest.main()
