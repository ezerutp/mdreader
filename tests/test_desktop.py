"""Integracion con el escritorio.

Estas pruebas escriben en directorios temporales via MDREADER_APPLICATIONS_DIR
y MDREADER_ICON_ROOT: nunca tocan el `~/.local/share` real ni cambian el
handler por defecto del sistema.
"""

import os
import tempfile
import unittest
from pathlib import Path

try:
    from PySide6.QtGui import QGuiApplication

    QT = True
except ImportError:  # pragma: no cover
    QT = False


@unittest.skipUnless(QT, "PySide6 no instalado")
class TestLanzador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QGuiApplication.instance() or QGuiApplication(["test"])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.env = {
            "MDREADER_APPLICATIONS_DIR": str(root / "applications"),
            "MDREADER_ICON_ROOT": str(root / "icons"),
            "MDREADER_EXEC": "/opt/prueba/mdreader",
        }
        self._saved = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def test_desktop_declara_el_mime_y_recibe_archivos(self):
        from mdreader_ui.desktop import desktop_file, install_desktop_entry

        # set_default=False: la prueba no debe tocar las asociaciones del usuario.
        install_desktop_entry(set_default=False)
        content = desktop_file().read_text(encoding="utf-8")

        # Sin MimeType el doble click nunca llega a la app.
        self.assertIn("MimeType=text/markdown;", content)
        # Sin %F el escritorio lanza la app pero no le pasa la ruta.
        self.assertIn("%F", content)
        self.assertIn("Exec=/opt/prueba/mdreader %F", content)
        self.assertIn("Type=Application", content)
        self.assertIn("Terminal=false", content)
        # StartupWMClass es lo que agrupa la ventana con su icono en GNOME.
        self.assertIn("StartupWMClass=mdreader", content)

    def test_iconos_en_todos_los_tamaños(self):
        from mdreader_ui.desktop import ICON_SIZES, icons_root, install_desktop_entry

        install_desktop_entry(set_default=False)
        for size in ICON_SIZES:
            path = icons_root() / f"{size}x{size}" / "apps" / "mdreader.png"
            with self.subTest(size=size):
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 0)

    def test_desinstalar_deja_todo_limpio(self):
        from mdreader_ui.desktop import (
            desktop_file,
            install_desktop_entry,
            uninstall_desktop_entry,
        )

        install_desktop_entry(set_default=False)
        self.assertTrue(desktop_file().exists())
        uninstall_desktop_entry()
        self.assertFalse(desktop_file().exists())

    def test_desinstalar_dos_veces_no_lanza(self):
        from mdreader_ui.desktop import uninstall_desktop_entry

        uninstall_desktop_entry()
        uninstall_desktop_entry()


@unittest.skipUnless(QT, "PySide6 no instalado")
class TestEsquemaDeAssets(unittest.TestCase):
    def test_no_se_puede_salir_de_assets(self):
        from mdreader_ui.assets import AssetSchemeHandler

        handler = AssetSchemeHandler.__new__(AssetSchemeHandler)
        from mdreader.page import assets_dir

        handler._root = assets_dir().resolve()

        for intento in ("../../../etc/passwd", "/etc/passwd", "..%2f..%2fetc", ""):
            with self.subTest(intento=intento):
                self.assertIsNone(handler._resolve(intento))

    def test_sirve_lo_que_esta_adentro(self):
        from mdreader.page import assets_dir
        from mdreader_ui.assets import AssetSchemeHandler

        handler = AssetSchemeHandler.__new__(AssetSchemeHandler)
        handler._root = assets_dir().resolve()
        self.assertIsNotNone(handler._resolve("reader.css"))
        self.assertIsNotNone(handler._resolve("reader.js"))


if __name__ == "__main__":
    unittest.main()
