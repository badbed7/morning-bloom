import tempfile
import time
import unittest
from pathlib import Path

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QScrollArea

from morning_bloom.app import SHOP_PAGE, Window
from morning_bloom.cosmetics import POT_SKINS, THEMES
from morning_bloom.locked_catalog import LOCKED_COLLECTIONS, catalog_sheet, preview_image
from morning_bloom.model import Garden
from morning_bloom.plant_catalog import PLANTS
from morning_bloom.storage import Store


class LockedCatalogTests(unittest.TestCase):
    def test_reference_items_have_artwork_and_cannot_be_acquired_or_equipped(self):
        self.assertEqual({key: len(items) for key, items in LOCKED_COLLECTIONS.items()},
                         {'식물': 8, '정원': 79, '화분': 41})
        garden = Garden(100, coins=10000, sunlight=10000)
        before = garden.to_dict()
        seen = set()
        for items in LOCKED_COLLECTIONS.values():
            for item in items:
                with self.subTest(item=item.key):
                    self.assertNotIn(item.key, seen | set(PLANTS) | set(THEMES) | set(POT_SKINS))
                    seen.add(item.key)
                    sheet = catalog_sheet(item.sheet)
                    self.assertFalse(sheet.isNull())
                    self.assertTrue(sheet.rect().contains(QRect(*item.bounds)))
                    self.assertFalse(preview_image(item).isNull())
                    self.assertFalse(garden.buy_seed(item.key))
                    self.assertFalse(garden.plant(100, item.key))
                    self.assertFalse(garden.buy_theme(item.key))
                    self.assertFalse(garden.equip_theme(item.key))
                    self.assertFalse(garden.buy_skin(item.key))
                    self.assertFalse(garden.equip_skin(item.key))
        self.assertEqual(garden.to_dict(), before)

    def test_browsing_all_categories_and_pages_fits_without_changing_save(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temp:
            window = Window(Store(Path(temp) / 'garden.json'), Garden(time.time()))
            window.clock.stop()
            window.autosave.stop()
            window.pages.setCurrentIndex(SHOP_PAGE)
            window.show()
            before = window.garden.to_dict()
            catalog = window.locked_catalog
            scroll = window.pages.widget(SHOP_PAGE).findChild(QScrollArea)
            try:
                for side in (320, 384, 520):
                    window.setFixedSize(side, side)
                    app.processEvents()
                    for button, (category, items) in zip(catalog.tabs.buttons(), LOCKED_COLLECTIONS.items()):
                        button.click()
                        self.assertEqual(catalog.page, 0)
                        self.assertFalse(catalog.previous.isEnabled())
                        app.processEvents()
                        navigation_y = catalog.next.y()
                        displayed = []
                        while True:
                            app.processEvents()
                            self.assertEqual(catalog.next.y(), navigation_y)
                            self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
                            for card, picture, name in catalog.cards:
                                if not card.isHidden():
                                    displayed.append(name.text())
                                    self.assertFalse(picture.pixmap().isNull())
                                    self.assertTrue(catalog.rect().contains(card.geometry()))
                                    self.assertGreaterEqual(picture.width(), picture.pixmap().width())
                            if not catalog.next.isEnabled():
                                break
                            catalog.next.click()
                        self.assertEqual(displayed, [item.name for item in items])
                        last_page = catalog.page
                        catalog.change_page(1)
                        self.assertEqual(catalog.page, last_page)
                        catalog.previous.click()
                        self.assertEqual(catalog.page, last_page - 1)
                    self.assertEqual(window.garden.to_dict(), before)
            finally:
                window.hide()
                window.deleteLater()
                app.processEvents()


if __name__ == '__main__':
    unittest.main()
