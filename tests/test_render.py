"""Pipeline Markdown -> HTML: features de GFM, indice y deteccion de recursos."""

import unittest

from mdreader.render import MarkdownRenderer
from mdreader.toc import build_tree, slugify


class TestFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = MarkdownRenderer()

    def test_tabla_gfm(self):
        html = self.r.render("| a | b |\n|---|---|\n| 1 | 2 |").html
        self.assertIn("<table>", html)
        self.assertIn("<th>a</th>", html)

    def test_alineacion_de_columna(self):
        html = self.r.render("| a |\n|--:|\n| 1 |").html
        self.assertIn("text-align:right", html)

    def test_tachado_y_tareas(self):
        self.assertIn("<s>x</s>", self.r.render("~~x~~").html)
        html = self.r.render("- [x] hecho\n- [ ] no").html
        self.assertIn("task-list-item", html)
        self.assertIn("checked", html)

    def test_nota_al_pie(self):
        html = self.r.render("texto[^1]\n\n[^1]: la nota").html
        self.assertIn("footnote-ref", html)
        self.assertIn("la nota", html)

    def test_codigo_con_pygments(self):
        html = self.r.render("```python\ndef f(): pass\n```").html
        self.assertIn('class="highlight"', html)
        self.assertIn('data-lang="python"', html)

    def test_codigo_sin_lenguaje_no_se_adivina(self):
        # Adivinar sobre pocas lineas colorea mal y se nota mas que no colorear.
        html = self.r.render("```\nsin lenguaje\n```").html
        self.assertIn("no-lang", html)

    def test_lenguaje_desconocido_no_revienta(self):
        html = self.r.render("```lenguajeinventadoxyz\nfoo\n```").html
        self.assertIn("foo", html)

    def test_mermaid_no_pasa_por_pygments(self):
        result = self.r.render("```mermaid\ngraph TD; A-->B;\n```")
        self.assertTrue(result.has_mermaid)
        self.assertIn('<pre class="mermaid">', result.html)
        self.assertNotIn("highlight", result.html)

    def test_math_inline_y_bloque(self):
        result = self.r.render("$E=mc^2$\n\n$$\\int x\n$$")
        self.assertTrue(result.has_math)
        self.assertIn('class="math inline"', result.html)
        self.assertIn('class="math block"', result.html)

    def test_math_se_escapa(self):
        # Sin escapar, "$a < script>$" seria una via de inyeccion.
        html = self.r.render("$a < b$").html
        self.assertIn("&lt;", html)
        self.assertNotIn("<b>", html)

    def test_front_matter(self):
        result = self.r.render("---\ntitle: Hola\nautor: ezer\n---\n\n# H")
        self.assertEqual(result.front_matter.get("title"), "Hola")
        self.assertEqual(result.title, "Hola")

    def test_front_matter_roto_no_tira_el_documento(self):
        result = self.r.render("---\n: : : mal\n\t- yaml\n---\n\n# Titulo")
        self.assertIn("Titulo", result.html)

    def test_titulo_cae_al_primer_h1(self):
        self.assertEqual(self.r.render("# Primero\n\n# Segundo").title, "Primero")


class TestIndice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = MarkdownRenderer()

    def test_anclas_en_el_html_y_en_el_indice(self):
        result = self.r.render("# Instalacion")
        self.assertEqual(result.headings[0].anchor, "instalacion")
        self.assertIn('id="instalacion"', result.html)

    def test_acentos_dan_ancla_ascii(self):
        # Asi un `#instalacion` escrito a mano sigue funcionando.
        self.assertEqual(slugify("Instalación"), "instalacion")

    def test_duplicados_reciben_sufijo(self):
        result = self.r.render("# Notas\n\n# Notas\n\n# Notas")
        self.assertEqual([h.anchor for h in result.headings], ["notas", "notas-1", "notas-2"])

    def test_texto_del_indice_sin_marcas(self):
        result = self.r.render("## Instalar **rapido** con `pip`")
        self.assertEqual(result.headings[0].text, "Instalar rapido con pip")

    def test_anidado(self):
        result = self.r.render("# A\n\n## B\n\n### C\n\n## D")
        self.assertEqual(len(result.toc), 1)
        self.assertEqual(len(result.toc[0].children), 2)
        self.assertEqual(result.toc[0].children[0].children[0].heading.text, "C")

    def test_documento_que_arranca_en_h2(self):
        result = self.r.render("## A\n\n## B")
        self.assertEqual(len(result.toc), 2)

    def test_salto_de_nivel_no_inventa_intermedios(self):
        result = self.r.render("# A\n\n### C")
        self.assertEqual(len(result.toc), 1)
        self.assertEqual(result.toc[0].children[0].heading.text, "C")

    def test_sin_encabezados(self):
        self.assertEqual(build_tree([]), [])


class TestRecursosRemotos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = MarkdownRenderer()

    def test_cuenta_imagenes_remotas(self):
        result = self.r.render("![a](https://x/y.png) ![b](http://z/w.png) ![c](local.png)")
        self.assertEqual(result.remote_images, 2)

    def test_protocol_relative_cuenta_como_remota(self):
        self.assertEqual(self.r.render("![a](//cdn/x.png)").remote_images, 1)

    def test_data_uri_no_es_remota(self):
        self.assertEqual(self.r.render("![a](data:image/png;base64,AA)").remote_images, 0)


if __name__ == "__main__":
    unittest.main()
