"""Opt-in real always-on-top overlay test, using temporary game data.

Run with BLOOM_TEST_NATIVE_DESKTOP=1 and QT_QPA_PLATFORM=windows.
Does not restart Explorer or modify desktop icons/wallpaper settings.
"""
import os
import sys
import tempfile
import time
import unittest
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from morning_bloom.app import Window
from morning_bloom.model import Garden
from morning_bloom.storage import Store


@unittest.skipUnless(sys.platform == 'win32' and os.environ.get('BLOOM_TEST_NATIVE_DESKTOP') == '1',
                     'opt-in Windows desktop integration')
class NativeDesktop(unittest.TestCase):
    def test_topmost_style_move_opacity_collect_and_cleanup(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            now = time.time()
            garden = Garden(now)
            garden.plant(now)
            garden.care('water', now)
            owner = Window(Store(Path(tmp) / 'garden.json'), garden)
            owner.show()
            app.processEvents()
            cover = None
            try:
                item_id = garden.pot['plant_id']
                self.assertTrue(owner.desktop.place(item_id), owner.message.text())
                widget = owner.desktop.windows[item_id]
                self.assertTrue(widget.growing)
                self.assertEqual(widget.suns, {})
                hwnd, host = int(widget.winId()), widget.host
                app.processEvents()
                self.assertFalse(host.api.GetParent(hwnd))
                self.assertFalse(host.get_style(hwnd, -16) & 0x40000000)  # not WS_CHILD
                self.assertTrue(host.get_style(hwnd, -20) & 0x00000008)  # WS_EX_TOPMOST
                cover = QWidget(None, Qt.Window)
                cover.setGeometry(widget.geometry())
                cover.show()
                cover.raise_()
                app.processEvents()
                cover_hwnd = int(cover.winId())
                self.assertFalse(host.get_style(cover_hwnd, -20) & 0x00000008)
                host.api.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
                host.api.GetWindow.restype = wintypes.HWND
                below, current = set(), hwnd
                for _ in range(512):
                    current = int(host.api.GetWindow(current, 2) or 0)  # GW_HWNDNEXT
                    if not current or current in below:
                        break
                    below.add(current)
                self.assertIn(cover_hwnd, below, 'normal overlapping window must remain below the flower')
                owner.showMinimized()
                app.processEvents()
                self.assertTrue(owner.isMinimized())
                self.assertTrue(widget.isVisible(), 'floating flower must remain visible while main window is minimized')
                self.assertTrue(host.valid(hwnd))
                owner.showNormal()
                app.processEvents()
                self.assertFalse(owner.isMinimized())
                old_x, old_y = host.position(hwnd)
                host.move(widget, old_x + 8, old_y + 8)
                self.assertNotEqual(host.position(hwnd), (old_x, old_y))
                owner.desktop_opacity.setValue(45)
                self.assertAlmostEqual(widget.windowOpacity(), .45, delta=.01)
                garden.growth = garden.duration
                self.assertTrue(owner.act(owner.harvest_flower))
                self.assertIs(owner.desktop.windows[item_id], widget)
                self.assertFalse(widget.growing)
                point = next(iter(widget.suns.values()))
                QTest.mouseClick(widget, Qt.LeftButton, pos=point.toPoint())
                self.assertEqual(garden.sunlight, 1)
                self.assertEqual(garden.sun_tokens, [])
                self.assertTrue(owner.desktop.place(item_id))
                self.assertEqual(owner.desktop.windows, {})
            finally:
                if cover is not None:
                    cover.close()
                    cover.deleteLater()
                owner.close()
                owner.deleteLater()
                app.processEvents()


if __name__ == '__main__':
    unittest.main()
