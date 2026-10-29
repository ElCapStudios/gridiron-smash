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

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            source = dict(attrs).get("src")
            if source is not None:
                self.sources.append(source)


def local_script_sources(markup, root):
    parser = ScriptSourceParser()
    parser.feed(markup)
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

    def test_rejects_an_absolute_script_path(self):
        markup = '<script src="/game.js"></script>'
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
