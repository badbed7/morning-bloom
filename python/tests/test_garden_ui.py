import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QListWidget, QScrollArea

from morning_bloom.app import GARDEN_PAGE, POT_PAGE, SETTINGS_PAGE, SHOP_PAGE, Window
from morning_bloom.garden_view import FLOWER_MIME
from morning_bloom.flower_art import paint_collection_flower, paint_potted_flower
from morning_bloom.model import Garden
from morning_bloom.storage import SaveError, Store


class LocalDrop(QDropEvent):
    def __init__(self, source, mime):
        super().__init__(QPointF(30, 20), Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
        self.origin = source

    def source(self):
        return self.origin


class LocalEnter(QDragEnterEvent):
    def __init__(self, source, mime):
        super().__init__(QPoint(30, 20), Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
        self.origin = source

    def source(self):
        return self.origin


def flower(index=0, species='daisy', price=50, bonus=5):
    return dict(id=f'flower-{index}', species=species, harvested_at=100,
                base_sale_g=price, misted=bool(bonus), bonus_g=bonus)


class GardenInterface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        font = Path(__file__).resolve().parents[2] / 'assets/fonts/NotoSansKR-Subset.otf'
        if font.exists():
            font_id = QFontDatabase.addApplicationFont(str(font))
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                cls.app.setFont(QFont(families[0], 10))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'garden.json')
        self.garden = Garden(time.time(), collection=[flower(), flower(1, 'tulip', 100, 10)])
        self.window = Window(self.store, self.garden)
        self.window.show()
        self.app.processEvents()
        self.meadow = self.window.collection_garden.meadow
        self.zone = self.window.collection_garden.sale_zone

    def tearDown(self):
        self.window.clock.stop()
        self.window.autosave.stop()
        self.window.hide()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def mime(self, item_id='flower-0'):
        data = QMimeData()
        data.setData(FLOWER_MIME, item_id.encode('utf-8'))
        return data

    def show_garden(self):
        self.window.navigate(-1)
        self.window.pages.finish_transition()
        self.app.processEvents()

    def test_right_and_left_navigation_wraps_and_skips_settings(self):
        for expected in (SHOP_PAGE, GARDEN_PAGE, POT_PAGE, SHOP_PAGE):
            self.window.next_page.click()
            self.assertEqual(self.window.pages.currentIndex(), expected)
        for expected in (POT_PAGE, GARDEN_PAGE, SHOP_PAGE, POT_PAGE):
            self.window.previous_page.click()
            self.assertEqual(self.window.pages.currentIndex(), expected)
        self.assertFalse(hasattr(self.window, 'navigation'))

    def test_settings_returns_to_each_origin(self):
        for origin in (POT_PAGE, SHOP_PAGE, GARDEN_PAGE):
            self.window.pages.slide_to(origin)
            self.window.settings_button.click()
            self.assertEqual(self.window.pages.currentIndex(), SETTINGS_PAGE)
            self.assertFalse(self.window.next_page.isEnabled())
            self.window.settings_button.click()
            self.assertEqual(self.window.pages.currentIndex(), origin)

    def test_slide_finishes_and_rapid_clicks_leave_no_overlay(self):
        self.window.next_page.click()
        self.assertIsNotNone(self.window.pages._animation)
        for _ in range(8):
            self.window.next_page.click()
        QTest.qWait(240)
        self.assertIsNone(self.window.pages._animation)
        self.assertEqual(self.window.pages._overlays, [])
        self.assertEqual(self.window.pages.currentIndex(), POT_PAGE)

    def test_navigation_does_not_write_or_mutate_inventory(self):
        before = self.garden.to_dict()
        with patch.object(self.store, 'save') as save:
            self.window.next_page.click()
            self.window.settings_button.click()
            self.window.settings_button.click()
            save.assert_not_called()
        self.assertEqual(before, self.garden.to_dict())

    def test_collection_uses_flowers_not_a_text_list(self):
        self.show_garden()
        self.assertEqual(self.window.findChildren(QListWidget), [])
        self.assertEqual([i['id'] for i in self.meadow.items], ['flower-0', 'flower-1'])
        self.assertEqual(self.meadow.item_at(self.meadow.item_rect(0).center())['id'], 'flower-0')
        self.assertIn('55G', self.meadow.tooltip_for(self.meadow.items[0]))

    def test_clicking_a_flower_never_sells(self):
        self.show_garden()
        before = (self.garden.coins, len(self.garden.collection))
        QTest.mouseClick(self.meadow, Qt.LeftButton, pos=self.meadow.item_rect(0).center().toPoint())
        self.assertEqual(before, (self.garden.coins, len(self.garden.collection)))

    def add_sun(self, token_id='sun-1'):
        self.garden.sun_tokens = [{
            'id': token_id, 'source_flower_id': 'flower-0',
            'created_at': self.garden.last_update,
        }]
        self.garden.sun_intro_claimed = True
        self.window.refresh()
        return self.meadow.sun_rect(0).center().toPoint()

    def test_clicking_sun_collects_once_persists_and_starts_burst(self):
        self.show_garden()
        point = self.add_sun()
        self.assertIsNone(self.meadow.item_at(point))
        QTest.mouseClick(self.meadow, Qt.LeftButton, pos=point)
        self.assertEqual(self.garden.sunlight, 1)
        self.assertEqual(self.garden.sun_tokens, [])
        self.assertEqual(len(self.meadow.bursts), 1)
        self.assertIn('햇빛 수집 +1', self.window.message.text())
        restored = self.store.load(self.garden.last_update)
        self.assertEqual(restored.sunlight, 1)
        self.assertEqual(restored.sun_tokens, [])
        QTest.mouseClick(self.meadow, Qt.LeftButton, pos=point)
        self.assertEqual(self.garden.sunlight, 1)

    def test_failed_sun_save_restores_token_without_burst(self):
        self.show_garden()
        point = self.add_sun()
        with patch.object(self.store, 'save', side_effect=SaveError('disk full')):
            QTest.mouseClick(self.meadow, Qt.LeftButton, pos=point)
        self.assertEqual(self.garden.sunlight, 0)
        self.assertEqual([token['id'] for token in self.garden.sun_tokens], ['sun-1'])
        self.assertEqual(self.meadow.bursts, [])
        self.assertIn('되돌렸습니다', self.window.message.text())

    def test_sun_slots_are_distinct_and_do_not_start_flower_drag(self):
        self.garden.sun_tokens = [
            {'id': f'sun-{index}', 'source_flower_id': 'flower-0',
             'created_at': self.garden.last_update}
            for index in range(9)
        ]
        self.garden.sun_intro_claimed = True
        self.window.refresh()
        points = [self.meadow.sun_rect(index).center().toPoint() for index in range(9)]
        self.assertEqual(len({(point.x(), point.y()) for point in points}), 9)
        for index, point in enumerate(points):
            self.assertEqual(self.meadow.sun_token_at(point)['id'], f'sun-{index}')
            self.assertIsNone(self.meadow.item_at(point))

    def test_cosmetic_shop_buys_applies_and_restores_background(self):
        self.garden.sunlight = 12
        self.window.refresh()
        self.window.navigate(1)
        self.window.pages.finish_transition()
        self.window.theme_picker.buttons['cream'].click()
        self.assertTrue(self.window.buy_theme_button.isEnabled())
        self.window.buy_theme_button.click()
        self.assertEqual(self.garden.sunlight, 0)
        self.assertIn('cream', self.garden.owned_themes)
        self.assertTrue(self.window.apply_theme_button.isEnabled())
        self.window.apply_theme_button.click()
        self.assertEqual(self.garden.equipped_theme, 'cream')
        self.assertIn('사용 중', self.window.theme_picker.buttons['cream'].text())
        self.assertFalse(self.window.theme_picker.buttons['cream'].icon().isNull())
        self.assertEqual(self.store.load(self.garden.last_update).equipped_theme, 'cream')
        self.window.pages.slide_to(GARDEN_PAGE)
        self.window.pages.finish_transition()
        self.assertFalse(self.meadow.grab().isNull())

    def test_failed_cosmetic_purchase_restores_sunlight_and_ownership(self):
        self.garden.sunlight = 12
        self.window.theme_picker.buttons['cream'].click()
        self.window.refresh()
        with patch.object(self.store, 'save', side_effect=SaveError('disk full')):
            self.window.buy_theme_button.click()
        self.assertEqual(self.garden.sunlight, 12)
        self.assertEqual(self.garden.owned_themes, ['grass'])
        self.assertIn('되돌렸습니다', self.window.message.text())

    def test_skin_purchase_apply_and_failure_restore_money_and_saved_appearance(self):
        self.garden.sunlight = 30
        self.window.skin_picker.buttons['sage'].click()
        self.assertEqual(self.garden.sunlight, 30)
        self.assertFalse(self.window.apply_skin_button.isEnabled())
        with patch.object(self.store, 'save', side_effect=SaveError('disk full')):
            self.window.buy_skin_button.click()
        self.assertEqual((self.garden.sunlight, self.garden.owned_skins), (30, ['terracotta']))
        self.window.buy_skin_button.click()
        self.assertEqual(self.garden.sunlight, 12)
        self.assertEqual(self.garden.equipped_skin, 'terracotta')
        self.assertFalse(self.window.buy_skin_button.isEnabled())
        with patch.object(self.store, 'save', side_effect=SaveError('disk full')):
            self.window.apply_skin_button.click()
        self.assertEqual(self.garden.equipped_skin, 'terracotta')
        self.window.apply_skin_button.click()
        self.assertEqual((self.garden.equipped_skin, self.garden.sunlight), ('sage', 12))
        restored = self.store.load(self.garden.last_update)
        self.assertEqual((restored.equipped_skin, restored.owned_skins), ('sage', ['terracotta', 'sage']))
        self.window.skin_picker.buttons['rose'].click()
        self.assertFalse(self.window.buy_skin_button.isEnabled())
        self.assertFalse(self.window.apply_skin_button.isEnabled())
        self.assertEqual(self.garden.equipped_skin, 'sage')
        self.window.skin_picker.buttons['terracotta'].click()
        self.window.apply_skin_button.click()
        self.assertEqual((self.garden.equipped_skin, self.garden.sunlight), ('terracotta', 12))

    def test_skin_reaches_growing_collection_and_drag_renderers(self):
        self.garden.sunlight = 18
        self.garden.buy_skin('sage')
        self.garden.equip_skin('sage')
        self.window.plant_button.click()
        self.window.refresh()
        skins = []

        def draw_pot(*args, **kwargs):
            skins.append(kwargs['skin'])
            return paint_potted_flower(*args, **kwargs)

        def draw_collection(*args, **kwargs):
            skins.append(kwargs['skin'])
            return paint_collection_flower(*args, **kwargs)

        with patch('morning_bloom.app.paint_potted_flower', new=draw_pot):
            self.window.flower.grab()
            self.assertEqual(skins, ['sage'])
        self.show_garden()
        skins.clear()
        with patch('morning_bloom.garden_view.paint_collection_flower', new=draw_collection):
            self.meadow.grab()
            self.assertTrue(skins)
            self.assertEqual(set(skins), {'sage'})
            skins.clear()
            with patch('morning_bloom.garden_view.QDrag') as drag:
                drag.return_value.exec.return_value = Qt.IgnoreAction
                self.meadow.start_drag('flower-0')
            self.assertTrue(skins)
            self.assertEqual(set(skins), {'sage'})

    def test_cosmetic_icons_are_exclusive_and_fit_all_window_sizes(self):
        self.window.navigate(1)
        self.window.pages.finish_transition()
        self.assertEqual(self.window.findChildren(QComboBox), [])
        scroll = self.window.pages.widget(SHOP_PAGE).findChild(QScrollArea)
        for side in (320, 384, 520):
            self.window.setFixedSize(side, side)
            for picker in (self.window.theme_picker, self.window.skin_picker):
                self.app.processEvents()
                scroll.ensureWidgetVisible(picker, 0, 0)
                self.app.processEvents()
                for button in picker.buttons.values():
                    self.assertFalse(button.icon().isNull())
                    self.assertTrue(scroll.viewport().rect().contains(button.mapTo(scroll.viewport(), button.rect().topLeft())))
                    self.assertTrue(scroll.viewport().rect().contains(button.mapTo(scroll.viewport(), button.rect().bottomRight())))
                buttons = list(picker.buttons.values())
                buttons[-1].click()
                self.assertEqual(sum(button.isChecked() for button in buttons), 1)
                self.assertEqual(self.garden.equipped_theme, 'grass')
                self.assertEqual(self.garden.equipped_skin, 'terracotta')

    def test_drag_cancel_keeps_flower_and_coins(self):
        self.show_garden()
        with patch('morning_bloom.garden_view.QDrag') as drag:
            drag.return_value.exec.return_value = Qt.IgnoreAction
            self.meadow.start_drag('flower-0')
        self.assertIsNone(self.meadow.dragged_id)
        self.assertIsNone(self.zone.preview)
        self.assertEqual((self.garden.coins, len(self.garden.collection)), (120, 2))

    def test_drag_enter_previews_price_without_selling(self):
        self.meadow.dragged_id = 'flower-0'
        mime = self.mime()
        enter = LocalEnter(self.meadow, mime)
        self.zone.dragEnterEvent(enter)
        self.assertTrue(enter.isAccepted())
        self.assertTrue(self.zone.highlighted)
        self.assertEqual(self.zone.preview['bonus_g'], 5)
        self.assertEqual(self.garden.coins, 120)

    def test_drag_lifecycle_sells_after_drop_and_clears_preview(self):
        self.show_garden()
        with patch('morning_bloom.garden_view.QDrag') as drag:
            def drop_from_drag(actions):
                mime = drag.return_value.setMimeData.call_args.args[0]
                enter = LocalEnter(self.meadow, mime)
                self.zone.dragEnterEvent(enter)
                self.assertTrue(enter.isAccepted())
                drop = LocalDrop(self.meadow, mime)
                self.zone.dropEvent(drop)
                self.assertTrue(drop.isAccepted())
                return Qt.MoveAction
            drag.return_value.exec.side_effect = drop_from_drag
            self.meadow.start_drag('flower-0')
        self.assertEqual(self.garden.coins, 175)
        self.assertIsNone(self.meadow.dragged_id)
        self.assertIsNone(self.zone.preview)

    def test_drop_sells_one_flower_and_persists_snapshot_price(self):
        self.show_garden()
        self.meadow.dragged_id = 'flower-0'
        mime = self.mime()
        drop = LocalDrop(self.meadow, mime)
        self.zone.dropEvent(drop)
        self.assertTrue(drop.isAccepted())
        self.assertEqual(self.garden.coins, 175)
        self.assertEqual([i['id'] for i in self.meadow.items], ['flower-1'])
        restored = self.store.load(self.garden.last_update)
        self.assertEqual(restored.coins, 175)
        self.assertEqual([i['id'] for i in restored.collection], ['flower-1'])

    def test_duplicate_drop_cannot_sell_twice(self):
        self.meadow.dragged_id = 'flower-0'
        mime = self.mime()
        self.zone.dropEvent(LocalDrop(self.meadow, mime))
        repeated = LocalDrop(self.meadow, mime)
        self.zone.dropEvent(repeated)
        self.assertFalse(repeated.isAccepted())
        self.assertEqual(self.garden.coins, 175)

    def test_foreign_and_stale_drags_are_rejected(self):
        self.meadow.dragged_id = 'flower-0'
        for source, item_id in ((None, 'flower-0'), (self.window, 'flower-0'), (self.meadow, 'missing')):
            mime = self.mime(item_id)
            drop = LocalDrop(source, mime)
            self.zone.dropEvent(drop)
            self.assertFalse(drop.isAccepted())
        self.assertEqual(self.garden.coins, 120)

    def test_missing_or_invalid_mime_is_rejected(self):
        self.meadow.dragged_id = 'flower-0'
        mime = QMimeData()
        for payload in (None, b'\xff'):
            if payload:
                mime.setData(FLOWER_MIME, payload)
            drop = LocalDrop(self.meadow, mime)
            self.zone.dropEvent(drop)
            self.assertFalse(drop.isAccepted())
        self.assertEqual(len(self.garden.collection), 2)

    def test_failed_drop_save_restores_flower_coins_and_visible_error(self):
        self.show_garden()
        self.window.setFixedSize(320, 320)
        self.meadow.dragged_id = 'flower-0'
        mime = self.mime()
        drop = LocalDrop(self.meadow, mime)
        with patch.object(self.store, 'save', side_effect=SaveError('disk full')):
            self.zone.dropEvent(drop)
        self.assertFalse(drop.isAccepted())
        self.assertEqual((self.garden.coins, len(self.meadow.items)), (120, 2))
        self.assertIn('되돌렸습니다', self.window.message.text())
        self.assertTrue(self.window.message.isVisible())

    def test_vacation_allows_garden_sale(self):
        self.garden.set_vacation(True, self.garden.last_update)
        self.meadow.dragged_id = 'flower-0'
        mime = self.mime()
        drop = LocalDrop(self.meadow, mime)
        self.zone.dropEvent(drop)
        self.assertTrue(drop.isAccepted())
        self.assertTrue(self.garden.vacation)

    def test_many_flowers_scroll_to_the_last_one(self):
        self.garden.collection = [flower(i) for i in range(100)]
        self.window.refresh()
        self.show_garden()
        scroll = self.window.collection_garden.scroll
        self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        self.app.processEvents()
        self.assertEqual(self.meadow.item_at(self.meadow.item_rect(99).center())['id'], 'flower-99')
        self.assertTrue(self.meadow.visibleRegion().boundingRect().intersects(self.meadow.item_rect(99).toRect()))

    def test_empty_garden_is_valid_after_last_sale(self):
        self.garden.collection = [flower()]
        self.window.refresh()
        self.assertTrue(self.window.sell_flower('flower-0'))
        self.assertEqual(self.meadow.items, [])
        self.show_garden()
        self.assertFalse(self.meadow.grab().isNull())

    def test_square_layout_keeps_footer_and_sale_zone_inside(self):
        for side in (320, 384, 520):
            self.window.setFixedSize(side, side)
            self.window.pages.slide_to(GARDEN_PAGE)
            self.window.pages.finish_transition()
            self.app.processEvents()
            for widget in (self.window.settings_button, self.zone, self.window.next_page):
                bottom_right = widget.mapTo(self.window, widget.rect().bottomRight())
                self.assertTrue(self.window.rect().contains(bottom_right), (side, widget.objectName()))


if __name__ == '__main__':
    unittest.main()
