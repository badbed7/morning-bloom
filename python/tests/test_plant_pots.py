"""Issue #26 and its plant-instance/repotting comment: model, migration and real UI."""
from legacy_fixture import v19_shape
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from morning_bloom.app import GARDEN_PAGE, POT_PAGE, Window
from morning_bloom.cosmetics import POT_COLORS, POT_SKINS
from morning_bloom.flower_art import paint_potted_flower, paint_collection_flower
from morning_bloom.model import Garden
from morning_bloom.plant_catalog import PLANTS, SEED_PLANTS
from morning_bloom.storage import SaveError, Store, migrate

NOW = 1_700_000_000


def flower(item_id, species='rose'):
    return dict(id=item_id, species=species, harvested_at=NOW,
                base_sale_g=50, misted=False, bonus_g=0)


class PlantPots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'garden.json')
        self.garden = Garden(NOW, coins=500, seeds={'daisy': 3},
                             tutorial_used=True, tutorial_reward_claimed=True,
                             owned_skins=['terracotta', 'ivory', 'sage'],
                             collection=[flower('rose-1'), flower('rose-2'), flower('daisy', 'daisy')])
        self.clock = patch('morning_bloom.app.time.time', return_value=NOW)
        self.clock.start()
        self.window = Window(self.store, self.garden)
        self.window.show()
        self.app.processEvents()
        self.window.persist()

    def tearDown(self):
        if self.window._cosmetic_dialog:
            self.window._cosmetic_dialog.reject()
        self.window.close_collection_picker()
        self.window.cloud = None
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.clock.stop()
        self.temp.cleanup()

    def open_pot(self, item_id='rose-1'):
        self.window.customize_plant_pot(item_id)
        self.app.processEvents()
        return self.window._cosmetic_dialog

    def test_same_species_instances_keep_independent_shape_color_after_restart_and_cloud(self):
        before = self.garden.to_dict()
        self.assertTrue(self.garden.set_plant_pot('rose-1', 'ivory', 'charcoal'))
        self.assertTrue(self.garden.set_plant_pot('rose-2', 'ivory', 'beige'))
        self.assertEqual(self.garden.source_pot('rose-1'), dict(skin='ivory', color='charcoal'))
        self.assertEqual(self.garden.source_pot('rose-2'), dict(skin='ivory', color='beige'))
        self.assertEqual(self.garden.source_pot('daisy'), dict(skin='terracotta', color='original'))
        self.assertEqual(self.garden.collection, before['collection'])
        self.assertEqual((self.garden.coins, self.garden.seeds), (before['coins'], before['seeds']))
        self.store.save(self.garden)
        loaded = self.store.load(NOW)
        self.assertEqual(loaded.flower_pots, self.garden.flower_pots)
        self.assertEqual(self.store.replace_from_cloud(loaded.to_dict(), NOW).flower_pots, loaded.flower_pots)
        loaded.sell('rose-1', NOW)
        self.assertNotIn('rose-1', loaded.flower_pots)
        self.assertEqual(loaded.source_color('rose-2'), 'beige')
        Garden.from_dict(loaded.to_dict())

    def test_growing_change_preserves_growth_then_harvest_keeps_id_and_pot(self):
        self.garden.plant(NOW, 'daisy')
        item_id = self.garden.pot['plant_id']
        self.garden.care('water', NOW)
        self.garden.pot['growth'] = 123
        before = self.garden.to_dict()
        dialog = self.open_pot(item_id)
        self.assertEqual(dialog.preview.choice[-1], 0)
        dialog.select('sage')
        dialog.color_picker.setCurrentIndex(dialog.color_picker.findData('burgundy'))
        self.assertEqual(self.garden.to_dict(), before)
        dialog.apply()
        self.assertEqual(self.garden.pot, before['pots'][0])
        self.assertEqual(self.garden.seeds, before['seeds'])
        self.assertEqual(self.garden.coins, before['coins'])
        self.garden.pot['growth'] = self.garden.pot['duration']
        self.garden.harvest(NOW)
        self.assertIn(item_id, [item['id'] for item in self.garden.collection])
        self.assertEqual(self.garden.source_pot(item_id), dict(skin='sage', color='burgundy'))
        self.assertEqual(self.store.replace_from_cloud(self.garden.to_dict(), NOW).source_color(item_id), 'burgundy')

    def test_garden_click_opens_correct_instance_owned_first_preview_and_cancel(self):
        self.window.pages.setCurrentIndex(GARDEN_PAGE)
        self.app.processEvents()
        meadow = self.window.collection_garden.meadow
        rect = meadow.item_rect(1)
        QTest.mouseClick(meadow, Qt.LeftButton, pos=rect.center().toPoint())
        dialog = self.window._cosmetic_dialog
        self.assertEqual(dialog.item_id, 'rose-2')
        self.assertIn('장미 2', dialog.hint.text())
        self.assertEqual(dialog.ordered_keys[:3], ['terracotta', 'ivory', 'sage'])
        before = self.garden.to_dict()
        dialog.select('ivory')
        dialog.color_picker.setCurrentIndex(dialog.color_picker.findData('beige'))
        self.assertEqual(dialog.preview.choice[1:3], ('ivory', 'beige'))
        self.assertEqual(self.garden.to_dict(), before)
        dialog.reject()
        self.assertEqual(self.garden.to_dict(), before)

    def test_apply_saves_only_target_and_save_failure_rolls_back(self):
        dialog = self.open_pot()
        before = self.garden.to_dict()
        dialog.select('ivory')
        dialog.color_picker.setCurrentIndex(dialog.color_picker.findData('charcoal'))
        with patch.object(self.store, 'save', side_effect=SaveError('disk full')):
            dialog.apply()
        self.assertEqual(self.garden.to_dict(), before)
        self.assertIs(self.window._cosmetic_dialog, dialog)
        dialog.apply()
        self.assertEqual(self.store.load(NOW).source_color('rose-1'), 'charcoal')
        self.assertEqual(self.garden.source_color('rose-2'), 'original')
        self.assertIsNone(self.window._cosmetic_dialog)

    def test_locked_gray_and_stale_or_invalid_choices_never_mutate(self):
        dialog = self.open_pot()
        before = self.garden.to_dict()
        dialog.select('rose')
        self.assertFalse(dialog.apply_button.isEnabled())
        self.assertTrue(dialog.buttons['rose'].icon().pixmap(88, 62).toImage().isGrayscale())
        dialog.apply()
        for args in [('rose-1', 'rose', 'beige'), ('missing', 'ivory', 'beige'),
                     ('rose-1', 'ivory', 'invalid'), ([], 'ivory', 'beige')]:
            self.assertFalse(self.garden.set_plant_pot(*args))
        self.assertEqual(self.garden.to_dict(), before)
        dialog.select('ivory')
        self.garden.sell('rose-1', NOW)
        sold = self.garden.to_dict()
        dialog.apply()
        self.assertEqual(self.garden.to_dict(), sold)
        self.assertIsNone(self.window._cosmetic_dialog)

    def test_sun_click_and_drag_do_not_open_pot_dialog(self):
        self.window.pages.setCurrentIndex(GARDEN_PAGE)
        self.garden.sun_tokens.append(dict(id='sun-test', source_flower_id='rose-1', created_at=NOW))
        self.window.refresh()
        meadow = self.window.collection_garden.meadow
        self.app.processEvents()
        point = meadow.sun_rect(0).center()
        QTest.mouseClick(meadow, Qt.LeftButton, pos=point.toPoint())
        self.assertIsNone(self.window._cosmetic_dialog)
        point = meadow.item_rect(1).center().toPoint()
        with patch.object(meadow, 'start_drag') as drag:
            QTest.mousePress(meadow, Qt.LeftButton, pos=point)
            QTest.mouseMove(meadow, point + QPoint(30, 0))
            QTest.mouseRelease(meadow, Qt.LeftButton, pos=point + QPoint(30, 0))
        drag.assert_called_once_with('rose-2')
        self.assertIsNone(self.window._cosmetic_dialog)

    def test_appearance_is_shared_by_garden_picker_drag_and_desktop(self):
        self.garden.set_plant_pot('rose-2', 'sage', 'charcoal')
        self.window.pages.setCurrentIndex(GARDEN_PAGE)
        self.app.processEvents()
        meadow = self.window.collection_garden.meadow
        styles = []

        def draw(*args, **kwargs):
            # A Mock's call history would retain QPainter past QWidget.grab(),
            # keeping the temporary paint device active on Windows.
            skin = args[4] if len(args) > 4 else kwargs['skin']
            styles.append((skin, kwargs['pot_color']))
            return paint_collection_flower(*args, **kwargs)

        with patch('morning_bloom.garden_view.paint_collection_flower', new=draw):
            meadow.grab()
        self.assertEqual(styles[1], ('sage', 'charcoal'))
        styles.clear()
        with patch('morning_bloom.garden_view.QDrag'), \
                patch('morning_bloom.garden_view.paint_collection_flower', new=draw):
            meadow.start_drag('rose-2')
        self.assertEqual(styles, [('sage', 'charcoal')])
        styles.clear()
        self.window.pages.setCurrentIndex(POT_PAGE)
        self.window.open_collection_picker()
        picker = self.window._collection_picker
        with patch('morning_bloom.collection_picker.paint_collection_flower', new=draw):
            picker._icon(self.garden.collection[1])
        self.assertEqual(styles, [('sage', 'charcoal')])
        styles.clear()
        from morning_bloom.desktop_flowers import DesktopFlower
        widget = DesktopFlower(self.window, 'rose-2', unittest.mock.Mock())
        widget.show()
        with patch('morning_bloom.desktop_flowers.paint_collection_flower', new=draw):
            widget.grab()
        self.assertEqual(styles, [('sage', 'charcoal')])
        widget.close()
        widget.deleteLater()

    def test_v18_migration_keeps_ledger_ids_and_raw_backup(self):
        self.garden.buy_pot()
        self.garden.set_slot_pot(1, 'ivory', 'original')
        old = self.garden.to_dict()
        old.pop('pot_colors')
        old.pop('flower_pots')
        old['schema'] = 18
        old = v19_shape(old)
        original = deepcopy(old)
        raw = json.dumps(old, ensure_ascii=False)
        upgraded = migrate(old)
        self.assertEqual(old, original)
        self.assertEqual({k: v for k, v in upgraded.items() if k not in ('schema', 'seeds', 'pot_colors', 'flower_pots')},
                         {k: v for k, v in old.items() if k not in ('schema', 'seeds')})
        self.assertEqual(upgraded['pot_colors'], ['original', 'original'])
        self.assertEqual(upgraded['seeds'], {**dict.fromkeys(SEED_PLANTS, 0), **old['seeds']})
        self.assertEqual(set(upgraded['flower_pots']), {'rose-1', 'rose-2', 'daisy'})
        self.store.path.write_text(raw, encoding='utf-8')
        loaded = self.store.load(NOW)
        self.store.save(loaded)
        self.assertEqual(self.store.migration_backup.read_text(encoding='utf-8'), raw)
        self.assertEqual(self.store.replace_from_cloud(old, NOW).to_dict(), upgraded)

    def test_invalid_new_save_fields_are_rejected(self):
        for field, value in [('pot_colors', []), ('pot_colors', ['missing']), ('pot_colors', [True]),
                             ('flower_pots', {'missing': dict(skin='ivory', color='beige')}),
                             ('flower_pots', {'rose-1': dict(skin='rose', color='beige')}),
                             ('flower_pots', {'rose-1': dict(skin='ivory', color=[])}),
                             ('flower_pots', {'rose-1': dict(skin='ivory', color='beige', extra=1)})]:
            data = self.garden.to_dict()
            data[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                Garden.from_dict(data)

    def test_species_default_pot_override_is_retracted_and_custom_colors_preserve_petals(self):
        def render(species, color='original', skin='terracotta'):
            image = QImage(380, 180, QImage.Format_ARGB32)
            image.fill(Qt.transparent)
            painter = QPainter(image)
            paint_potted_flower(painter, PLANTS[species], skin=skin, pot_color=color)
            painter.end()
            return image
        self.assertEqual(render('rose').pixelColor(180, 150).name(), '#c98c67')
        self.assertEqual(render('daisy').pixelColor(180, 150).name(), '#bd7e5c')
        for species in ('rose', 'daisy'):
            before = render(species)
            after = render(species, 'charcoal')
            before_top, after_top = before.copy(0, 0, 380, 100), after.copy(0, 0, 380, 100)
            self.assertEqual(bytes(before_top.bits()), bytes(after_top.bits()))
        # Every owned shape remains renderable with every offered color.
        for skin in POT_SKINS:
            images = [render('rose', color, skin) for color in POT_COLORS]
            self.assertEqual(len({bytes(image.bits()) for image in images}), len(POT_COLORS), skin)

    def test_small_and_large_dialogs_scroll_and_keep_apply_visible(self):
        dialog = self.open_pot()
        for side, columns in ((320, 2), (520, 3), (320, 2)):
            dialog.resize(side, side)
            self.app.processEvents()
            self.assertGreater(dialog.scroll.verticalScrollBar().maximum(), 0)
            self.assertLess(dialog.buttons[dialog.ordered_keys[0]].geometry().bottom(),
                            dialog.buttons[dialog.ordered_keys[columns]].geometry().top())
            self.assertTrue(dialog.rect().contains(dialog.apply_button.geometry().bottomRight()))
            self.assertEqual(dialog.preview.choice[:3], ('rose', 'terracotta', 'original'))


if __name__ == '__main__':
    unittest.main()
