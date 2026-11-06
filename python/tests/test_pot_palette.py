"""Issue #29 palette, custom RGB, nested cancellation and save compatibility."""
from copy import deepcopy
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from morning_bloom.app import Window
from morning_bloom.cosmetics import POT_SKINS, colored_pot_skin
from morning_bloom.flower_art import paint_potted_flower
from morning_bloom.model import Garden
from morning_bloom.plant_catalog import PLANTS
from morning_bloom.pot_colors import (LEGACY_POT_COLORS, POT_COLORS, POT_COLOR_GROUPS,
                                     normalize_pot_color, pot_color_hex, valid_pot_color)
from morning_bloom.storage import SaveError, Store, migrate

NOW = 1_700_000_000
EXPECTED = (
    '#F0E8D8', '#E8D5B7', '#D4BFA3', '#B8B0A3', '#A9A69E', '#55534E', '#F5F1E8', '#A18C78',
    '#B96F50', '#A65342', '#B77C56', '#80634F', '#C58F83', '#B98787', '#85865A', '#A3AA91',
    '#E8D99B', '#A9C5B5', '#AFC5D3', '#B9A9CA', '#E3B9B7', '#E6B49A', '#C0C99B', '#D0E0E2',
    '#455B47', '#555B3D', '#46566A', '#793F46', '#B18A3F', '#594337', '#695064', '#637C88',
)


def render(color, planted=False, skin='terracotta'):
    image = QImage(380, 180, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    paint_potted_flower(painter, PLANTS['rose'], planted=planted, skin=skin, pot_color=color)
    painter.end()
    return image


class PaletteRules(unittest.TestCase):
    def test_exact_32_issue_colors_and_legacy_ids_are_distinct(self):
        self.assertEqual(list(POT_COLOR_GROUPS), ['뉴트럴', '어스톤', '파스텔', '딥'])
        self.assertTrue(all(len(keys) == 8 for keys in POT_COLOR_GROUPS.values()))
        keys = [key for group in POT_COLOR_GROUPS.values() for key in group]
        self.assertEqual(len(set(keys)), 32)
        self.assertFalse(set(keys) & set(LEGACY_POT_COLORS))
        self.assertEqual(tuple(pot_color_hex(key).upper() for key in keys), EXPECTED)
        self.assertEqual(len(POT_COLORS), 39)
        self.assertEqual(pot_color_hex('ivory'), '#f0e5ce')
        self.assertEqual(pot_color_hex('neutral_ivory'), '#f0e8d8')
        self.assertEqual(pot_color_hex('charcoal'), '#35313d')
        self.assertEqual(pot_color_hex('neutral_charcoal'), '#55534e')

    def test_strict_hex_and_normalization_with_no_model_mutation_on_invalid_input(self):
        garden = Garden(NOW)
        before = garden.to_dict()
        for invalid in ('', '#123', '#12345678', '#zz0011', 'red', 'AABBCC', None, True, [], {}, '#123456\n'):
            with self.subTest(color=invalid):
                self.assertFalse(valid_pot_color(invalid))
                self.assertFalse(garden.set_slot_pot(0, 'terracotta', invalid))
                self.assertEqual(garden.to_dict(), before)
        for color in ('#000000', '#FFFFFF', '#a1B2C3', 'forest_green', 'original'):
            self.assertTrue(garden.set_slot_pot(0, 'terracotta', color))
            self.assertEqual(garden.current_color, normalize_pot_color(color))
            Garden.from_dict(garden.to_dict())

    def test_v20_migration_preserves_every_legacy_color_and_raw_backup(self):
        for color in LEGACY_POT_COLORS:
            garden = Garden(NOW)
            garden.set_slot_pot(0, 'terracotta', color)
            old = garden.to_dict()
            old['schema'] = 20
            before = deepcopy(old)
            upgraded = migrate(old)
            self.assertEqual(old, before)
            self.assertEqual(upgraded, {**old, 'schema': Garden.CURRENT_SCHEMA})
            with tempfile.TemporaryDirectory() as tmp:
                store = Store(Path(tmp) / 'garden.json')
                raw = json.dumps(old)
                store.path.write_text(raw, encoding='utf-8')
                loaded = store.load(NOW)
                store.save(loaded)
                self.assertEqual(store.migration_backup.read_text(encoding='utf-8'), raw)
                self.assertEqual(store.replace_from_cloud(old, NOW).current_color, color)
                self.assertEqual(store.load(NOW).current_color, color)

    def test_old_unknown_colors_stay_invalid_and_new_saves_validate_custom_rgb(self):
        for color in ('forest_green', '#aabbcc', None, '#1234'):
            data = Garden(NOW).to_dict()
            data['schema'] = 20
            data['pot_colors'] = [color]
            with self.assertRaises(ValueError):
                migrate(data)
        for invalid in ('#12345', '#12345678', False, {'rgb': '#abcdef'}):
            data = Garden(NOW).to_dict()
            data['pot_colors'] = [invalid]
            with self.assertRaises(ValueError):
                Garden.from_dict(data)

    def test_custom_color_survives_growth_harvest_sale_and_cloud_restore(self):
        garden = Garden(NOW, tutorial_used=True, seeds={'rose': 2})
        garden.plant(NOW, 'rose')
        plant_id = garden.pot['plant_id']
        garden.set_plant_pot(plant_id, 'terracotta', '#A1B2C3')
        garden.care('water', NOW)
        garden.pot['growth'] = garden.pot['duration']
        garden.harvest(NOW)
        garden.plant(NOW, 'rose')
        second = garden.pot['plant_id']
        garden.set_plant_pot(second, 'terracotta', 'forest_green')
        self.assertEqual(garden.source_color(plant_id), '#a1b2c3')
        self.assertEqual(garden.source_color(second), 'forest_green')
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            clone = store.replace_from_cloud(garden.to_dict(), NOW)
            self.assertEqual(clone.to_dict(), garden.to_dict())
            clone.sell(plant_id, NOW)
            self.assertNotIn(plant_id, clone.flower_pots)
            self.assertEqual(clone.source_color(second), 'forest_green')

    def test_texture_is_deterministic_preserves_petals_and_does_not_use_game_rng(self):
        rng = random.getstate()
        first, second = render('clay_pink'), render('clay_pink')
        self.assertEqual(random.getstate(), rng)
        self.assertEqual(bytes(first.bits()), bytes(second.bits()))
        body = first.copy(160, 126, 60, 29)
        shades = {body.pixelColor(x, y).name() for x in range(body.width()) for y in range(body.height())}
        self.assertGreater(len(shades), 3)
        samples = [render(color) for color in ('#000000', '#ffffff', 'forest_green')]
        self.assertGreater(len({bytes(image.bits()) for image in samples}), 1)
        for color in ('#000000', '#ffffff', 'forest_green', 'ice_blue'):
            before, after = render('original', True), render(color, True)
            top_before, top_after = before.copy(0, 0, 380, 100), after.copy(0, 0, 380, 100)
            self.assertEqual(bytes(top_before.bits()), bytes(top_after.bits()))
        catalog = deepcopy(POT_SKINS)
        for key in POT_SKINS:
            self.assertEqual(colored_pot_skin(key, '#A1B2C3').body, '#a1b2c3')
        self.assertEqual(POT_SKINS, catalog)


class PaletteUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'garden.json')
        self.garden = Garden(NOW, tutorial_used=True, tutorial_reward_claimed=True)
        self.clock = patch('morning_bloom.app.time.time', return_value=NOW)
        self.clock.start()
        self.window = Window(self.store, self.garden)
        self.window.show()
        self.app.processEvents()
        self.window.persist()
        self.window.pot_style_button.click()
        self.pots = self.window._cosmetic_dialog

    def tearDown(self):
        self.window.close_collection_picker()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.clock.stop()
        self.temp.cleanup()

    def colors(self):
        self.pots.color_button.click()
        self.app.processEvents()
        return self.pots._color_dialog

    def test_all_presets_preview_without_saving_and_cancel_keeps_outer_choice(self):
        before = self.garden.to_dict()
        colors = self.colors()
        for group, keys in POT_COLOR_GROUPS.items():
            colors.category.setCurrentText(group)
            self.assertEqual(tuple(colors.swatches), keys)
            for key in keys:
                colors.swatches[key].click()
                self.assertEqual(colors.selected_color, key)
                self.assertEqual(colors.preview.choice[2], key)
                self.assertEqual(colors.hex_input.text(), pot_color_hex(key).upper())
                self.assertEqual(sum(button.isChecked() for button in colors.swatches.values()), 1)
        colors.reject()
        self.assertEqual(self.pots.selected_color, 'original')
        self.assertEqual(self.garden.to_dict(), before)
        colors = self.colors()
        colors.category.setCurrentText('어스톤')
        colors.swatches['sage_green'].click()
        colors.use_button.click()
        self.assertEqual(self.pots.selected_color, 'sage_green')
        self.assertEqual(self.garden.to_dict(), before)
        self.pots.reject()
        self.assertEqual(self.garden.to_dict(), before)

    def test_hex_invalid_blocks_accept_then_valid_applies_only_on_outer_save(self):
        colors = self.colors()
        for invalid in ('#12', '#GGGGGG', '#11223344', ''):
            colors.hex_input.setText(invalid)
            self.assertFalse(colors.use_button.isEnabled())
            colors.accept()
            self.assertIs(self.pots._color_dialog, colors)
        colors.hex_input.setText('A1B2C3')
        self.assertTrue(colors.use_button.isEnabled())
        self.assertEqual(colors.selected_color, '#a1b2c3')
        colors.use_button.click()
        self.assertEqual(self.garden.current_color, 'original')
        before = self.garden.to_dict()
        with patch.object(self.store, 'save', side_effect=SaveError('disk full')):
            self.pots.apply()
        self.assertEqual(self.garden.to_dict(), before)
        self.assertEqual(self.pots.selected_color, '#a1b2c3')
        self.pots.apply()
        self.assertEqual(self.store.load(NOW).current_color, '#a1b2c3')
        self.assertIn('#A1B2C3', self.window.pot_style_button.toolTip())

    def test_picker_cancel_keeps_choice_and_accept_stages_opaque_rgb(self):
        colors = self.colors()
        colors.picker_button.click()
        picker = colors._picker
        self.assertIsNotNone(picker)
        picker.setCurrentColor(QColor('#123456'))
        picker.reject()
        self.assertEqual(colors.selected_color, 'original')
        colors.picker_button.click()
        picker = colors._picker
        picker.setCurrentColor(QColor('#123456'))
        picker.accept()
        self.assertEqual(colors.selected_color, '#123456')
        self.assertEqual(self.garden.current_color, 'original')
        self.pots.reject()
        self.assertIsNone(self.pots._color_dialog)
        self.assertEqual(self.garden.current_color, 'original')

    def test_small_and_large_layouts_scroll_without_overlaps_and_footer_stays_visible(self):
        colors = self.colors()
        for side in (320, 520, 320):
            colors.resize(side, side)
            for group in colors.groups:
                colors.category.setCurrentText(group)
                self.app.processEvents()
                buttons = list(colors.swatches.values())
                self.assertLess(buttons[0].geometry().right(), buttons[1].geometry().left())
                self.assertLess(buttons[0].geometry().bottom(), buttons[4].geometry().top())
                self.assertTrue(colors.rect().contains(colors.use_button.geometry().bottomRight()))
                self.assertEqual(colors.scroll.horizontalScrollBar().maximum(), 0)
            if side == 320:
                self.assertGreater(colors.scroll.verticalScrollBar().maximum(), 0)
            colors.scroll.ensureWidgetVisible(colors.hex_input)
            self.app.processEvents()
            self.assertTrue(colors.scroll.viewport().rect().contains(colors.hex_input.mapTo(colors.scroll.viewport(), colors.hex_input.rect().center())))

    def test_keyboard_swatch_selection_and_original_restore_keep_model_unchanged(self):
        colors = self.colors()
        colors.category.setCurrentText('딥')
        button = colors.swatches['navy']
        button.setFocus()
        QTest.keyClick(button, Qt.Key_Space)
        self.assertEqual(colors.selected_color, 'navy')
        colors.category.setCurrentText('추천')
        colors.swatches['original'].click()
        self.assertEqual(colors.selected_color, 'original')
        self.assertTrue(colors.use_button.isEnabled())
        self.assertEqual(colors.hex_input.text(), '')
        colors.use_button.click()
        self.assertEqual(self.garden.current_color, 'original')


if __name__ == '__main__':
    unittest.main()
