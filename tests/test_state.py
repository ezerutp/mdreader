"""Estado persistente. Lo importante: nunca impedir que la app arranque."""

import json
import tempfile
import unittest
from pathlib import Path

from mdreader.state import MAX_TRACKED, ReaderState


class TestPersistencia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_ida_y_vuelta(self):
        doc = Path(self.tmp.name) / "a.md"
        doc.write_text("# a")

        state = ReaderState(self.path)
        state.prefs.theme = "dark"
        state.prefs.zoom = 1.25
        state.remember(doc, scroll=0.42, opened_at=100.0)
        state.push_recent(doc)
        state.save()

        again = ReaderState(self.path)
        self.assertEqual(again.prefs.theme, "dark")
        self.assertEqual(again.prefs.zoom, 1.25)
        self.assertAlmostEqual(again.get(doc).scroll, 0.42)
        self.assertEqual(again.existing_recent(), [doc.resolve()])

    def test_archivo_corrupto_no_lanza(self):
        self.path.write_text("{ esto no es json")
        state = ReaderState(self.path)
        self.assertEqual(state.prefs.theme, "system")

    def test_archivo_inexistente_no_lanza(self):
        state = ReaderState(Path(self.tmp.name) / "no" / "existe.json")
        self.assertEqual(state.documents, {})

    def test_clave_desconocida_se_ignora(self):
        # Un state.json de una version futura no debe romper una vieja.
        self.path.write_text(json.dumps({"prefs": {"theme": "dark", "inventado": 1}}))
        self.assertEqual(ReaderState(self.path).prefs.theme, "dark")

    def test_scroll_se_recorta_al_rango(self):
        state = ReaderState(self.path)
        doc = Path(self.tmp.name) / "a.md"
        state.remember(doc, scroll=5.0)
        self.assertEqual(state.get(doc).scroll, 1.0)
        state.remember(doc, scroll=-3.0)
        self.assertEqual(state.get(doc).scroll, 0.0)

    def test_escritura_atomica_no_deja_temporales(self):
        state = ReaderState(self.path)
        state.save()
        sobrantes = [p.name for p in self.path.parent.iterdir() if p.suffix == ".tmp"]
        self.assertEqual(sobrantes, [])

    def test_poda_por_antiguedad(self):
        state = ReaderState(self.path)
        for i in range(MAX_TRACKED + 40):
            state.remember(Path(self.tmp.name) / f"d{i}.md", scroll=0.1, opened_at=float(i))
        state.save()
        again = ReaderState(self.path)
        self.assertLessEqual(len(again.documents), MAX_TRACKED)
        # Sobrevive el mas reciente, no el primero que entro.
        reciente = Path(self.tmp.name) / f"d{MAX_TRACKED + 39}.md"
        self.assertIn(str(reciente.resolve()), again.documents)

    def test_recientes_sin_duplicar_y_reordenando(self):
        state = ReaderState(self.path)
        a = Path(self.tmp.name) / "a.md"
        b = Path(self.tmp.name) / "b.md"
        state.push_recent(a)
        state.push_recent(b)
        state.push_recent(a)
        self.assertEqual(state.recent[0], str(a.resolve()))
        self.assertEqual(len(state.recent), 2)

    def test_recientes_borrados_no_se_listan(self):
        state = ReaderState(self.path)
        state.push_recent(Path(self.tmp.name) / "fantasma.md")
        self.assertEqual(state.existing_recent(), [])

    def test_permiso_remoto_por_documento(self):
        state = ReaderState(self.path)
        doc = Path(self.tmp.name) / "a.md"
        self.assertFalse(state.get(doc).allow_remote)
        state.remember(doc, allow_remote=True)
        self.assertTrue(state.get(doc).allow_remote)


if __name__ == "__main__":
    unittest.main()
