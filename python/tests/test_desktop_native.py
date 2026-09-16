"""Opt-in real Explorer test, using only temporary game data.

Run with BLOOM_TEST_NATIVE_DESKTOP=1 and QT_QPA_PLATFORM=windows.
Does not restart Explorer or modify desktop icons/wallpaper settings.
"""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from morning_bloom.app import Window
from morning_bloom.model import Garden
from morning_bloom.storage import Store


@unittest.skipUnless(sys.platform == 'win32' and os.environ.get('BLOOM_TEST_NATIVE_DESKTOP') == '1',
                     'opt-in Windows desktop integration')
class NativeDesktop(unittest.TestCase):
    def test_real_parent_styles_move_opacity_collect_and_cleanup(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            now = time.time()
            garden = Garden(now)
            garden.plant(now)
            garden.care('water', now)
            garden.growth = garden.duration
            garden.harvest(now)
            owner = Window(Store(Path(tmp) / 'garden.json'), garden)
            owner.show()
            app.processEvents()
            try:
                item_id = garden.collection[0]['id']
                self.assertTrue(owner.desktop.place(item_id), owner.message.text())
                widget = owner.desktop.windows[item_id]
                hwnd, host = int(widget.winId()), widget.host
                app.processEvents()
                self.assertEqual(host.api.GetParent(hwnd), host.parent)
                self.assertTrue(host.get_style(hwnd, -16) & 0x40000000)  # WS_CHILD
                self.assertFalse(host.get_style(hwnd, -20) & 0x00000008)  # not TOPMOST
                old_x, old_y = host.position(hwnd)
                host.move(widget, old_x + 8, old_y + 8)
                self.assertNotEqual(host.position(hwnd), (old_x, old_y))
                owner.desktop_opacity.setValue(45)
                self.assertAlmostEqual(widget.windowOpacity(), .45, delta=.01)
                point = next(iter(widget.suns.values()))
                QTest.mouseClick(widget, Qt.LeftButton, pos=point.toPoint())
                self.assertEqual(garden.sunlight, 1)
                self.assertEqual(garden.sun_tokens, [])
                self.assertTrue(owner.desktop.place(item_id))
                self.assertEqual(owner.desktop.windows, {})
            finally:
                owner.close()
                owner.deleteLater()
                app.processEvents()


if __name__ == '__main__':
    unittest.main()
