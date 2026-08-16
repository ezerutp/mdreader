"""Armado de la pagina: carga condicional de assets, CSP y front matter."""

import unittest

from mdreader.page import ASSET_SCHEME, PageBuilder, PageOptions, has_vendor
from mdreader.render import MarkdownRenderer


class TestPagina(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = MarkdownRenderer()
        cls.b = PageBuilder()

    def build(self, source: str, **kwargs) -> str:
        return self.b.build(self.r.render(source), PageOptions(**kwargs))

    def test_estructura_minima(self):
        html = self.build("# Hola")
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn('<div class="paper">', html)
        self.assertIn("Hola", html)

    def test_tema_en_el_atributo_raiz(self):
        self.assertIn('data-theme="dark"', self.build("x", theme="dark"))
        self.assertIn('data-theme="light"', self.build("x", theme="light"))
        # Cualquier valor raro cae a claro en vez de romper la hoja de estilos.
        self.assertIn('data-theme="light"', self.build("x", theme="ninguno"))

    def test_katex_solo_si_hay_formulas(self):
        if not has_vendor("katex.min.js"):
            self.skipTest("assets no descargados (scripts/fetch_assets.py)")
        self.assertNotIn("katex.min.js", self.build("sin formulas"))
        self.assertIn("katex.min.js", self.build("$x^2$"))

    def test_mermaid_solo_si_hay_diagramas(self):
        if not has_vendor("mermaid.min.js"):
            self.skipTest("assets no descargados (scripts/fetch_assets.py)")
        self.assertNotIn("mermaid.min.js", self.build("sin diagramas"))
        self.assertIn("mermaid.min.js", self.build("```mermaid\ngraph TD; A-->B;\n```"))

    def test_csp_presente_y_restrictiva(self):
        html = self.build("# x")
        self.assertIn("Content-Security-Policy", html)
        self.assertIn("default-src 'none'", html)
        self.assertIn("frame-src 'none'", html)
        self.assertIn("object-src 'none'", html)

    def test_titulo_escapado(self):
        html = self.build("# x", title='<script>"')
        self.assertNotIn("<script>", html.split("</head>")[0].split("<title>")[1])

    def test_front_matter_como_ficha(self):
        html = self.build("---\ntitle: T\nautor: e\n---\n\n# H")
        self.assertIn("front-matter", html)
        self.assertIn("<dt>autor</dt>", html)

    def test_front_matter_roto_se_muestra_crudo(self):
        html = self.build("---\n: : :\n\t- x\n---\n\n# H")
        self.assertIn("front-matter", html)

    def test_documento_vacio(self):
        self.assertIn("empty-doc", self.build(""))

    def test_ancho_completo(self):
        self.assertIn('class="full-width"', self.build("x", full_width=True))

    def test_assets_usan_el_esquema_propio(self):
        html = self.build("$x$")
        for tag in ("<script src=", '<link rel="stylesheet"'):
            for line in html.splitlines():
                if line.startswith(tag) and "vendor" in line:
                    self.assertIn(f"{ASSET_SCHEME}:/", line)


if __name__ == "__main__":
    unittest.main()
