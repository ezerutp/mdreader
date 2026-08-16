"""El saneado es la unica barrera entre un `.md` de origen desconocido y un
motor Chromium con JavaScript activo. Se prueba por vector, no por API."""

import unittest

from mdreader.sanitize import sanitize_html


class TestBloqueaEjecucion(unittest.TestCase):
    def test_script_se_descarta_con_su_contenido(self):
        out = sanitize_html("<script>alert(1)</script>despues")
        self.assertNotIn("alert", out)
        self.assertIn("despues", out)

    def test_style_se_descarta_con_su_contenido(self):
        out = sanitize_html("<style>body{display:none}</style>hola")
        self.assertNotIn("display", out)
        self.assertIn("hola", out)

    def test_iframe_object_embed(self):
        for tag in ("iframe", "object", "embed"):
            with self.subTest(tag=tag):
                out = sanitize_html(f"<{tag} src='https://x'></{tag}>")
                self.assertNotIn(tag, out)

    def test_atributos_on_se_eliminan(self):
        for attr in ("onerror", "onload", "onclick", "onmouseover"):
            with self.subTest(attr=attr):
                out = sanitize_html(f"<img src='a.png' {attr}='alert(1)'>")
                self.assertNotIn("alert", out)
                self.assertIn("a.png", out)

    def test_href_javascript(self):
        out = sanitize_html("<a href='javascript:alert(1)'>x</a>")
        self.assertNotIn("javascript", out)
        self.assertIn("<a>x</a>", out)

    def test_javascript_partido_por_salto_de_linea(self):
        # El navegador colapsa el "\n" del medio; el filtro tambien tiene que.
        out = sanitize_html("<a href='java\nscript:alert(1)'>x</a>")
        self.assertNotIn("alert", out)

    def test_data_text_html_bloqueado_data_image_permitido(self):
        self.assertNotIn("data:", sanitize_html("<img src='data:text/html,<b>x'>"))
        self.assertIn("data:image/png", sanitize_html("<img src='data:image/png;base64,AA'>"))

    def test_style_con_expression(self):
        out = sanitize_html("<div style='width:expression(alert(1))'>x</div>")
        self.assertNotIn("expression", out)
        self.assertIn("<div>x</div>", out)

    def test_comentario_con_markup_adentro(self):
        out = sanitize_html("<!-- <script>alert(1)</script> -->")
        self.assertNotIn("alert", out)

    def test_etiqueta_desconocida_se_escapa_no_se_borra(self):
        # Se muestra como la escribio el autor en vez de desaparecer sin aviso.
        out = sanitize_html("<svg onload=alert(1)></svg>")
        self.assertIn("&lt;svg", out)
        self.assertNotIn("<svg", out)


class TestPreservaDiseño(unittest.TestCase):
    def test_details_y_summary(self):
        out = sanitize_html("<details><summary>ver</summary>texto</details>")
        self.assertIn("<details>", out)
        self.assertIn("<summary>", out)

    def test_align_y_width_de_los_readme(self):
        out = sanitize_html('<p align="center"><img src="logo.png" width="200"></p>')
        self.assertIn('align="center"', out)
        self.assertIn('width="200"', out)

    def test_style_inocuo_sobrevive(self):
        out = sanitize_html("<div style='text-align:center'>x</div>")
        self.assertIn("text-align:center", out)

    def test_fragmento_incompleto(self):
        # markdown-it entrega los html_inline como tags sueltos.
        self.assertIn("<span", sanitize_html('<span class="x">'))
        self.assertEqual("</span>", sanitize_html("</span>"))

    def test_entidades_se_conservan(self):
        self.assertIn("&nbsp;", sanitize_html("a&nbsp;b"))

    def test_texto_plano_pasa_escapado(self):
        self.assertEqual("a &lt; b", sanitize_html("a < b"))


if __name__ == "__main__":
    unittest.main()
