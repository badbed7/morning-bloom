"""Catalog images must represent their parent category even when IDs overlap."""

import hashlib
from dataclasses import replace
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from morning_bloom import flower_art, cosmetic_icons
from morning_bloom.locked_catalog import COLLECTIONS, preview_image
from morning_bloom.cosmetics import THEMES, POT_SKINS
from morning_bloom.plant_catalog import PLANTS


class CatalogCategoryImages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        preview_image.cache_clear()

    def test_gardens_never_draw_a_potted_plant(self):
        with patch.object(
            flower_art,
            "paint_collection_flower",
            wraps=flower_art.paint_collection_flower,
        ) as plant, patch.object(
            cosmetic_icons, "theme_icon", wraps=cosmetic_icons.theme_icon
        ) as theme:
            for item in COLLECTIONS["정원"]:
                with self.subTest(item=item.key):
                    before = theme.call_count
                    self.assertFalse(preview_image(item).isNull())
                    self.assertEqual(theme.call_count, before + 1)
                    self.assertIs(theme.call_args.args[0], THEMES[item.key])
            plant.assert_not_called()

    def test_pots_never_draw_a_blooming_plant(self):
        with patch.object(
            flower_art,
            "paint_collection_flower",
            wraps=flower_art.paint_collection_flower,
        ) as plant, patch.object(
            flower_art, "paint_potted_flower", wraps=flower_art.paint_potted_flower
        ) as pot:
            for item in COLLECTIONS["화분"]:
                with self.subTest(item=item.key):
                    self.assertFalse(preview_image(item).isNull())
                    self.assertEqual(pot.call_args.kwargs.get("skin"), item.key)
                    self.assertIs(pot.call_args.kwargs.get("planted"), False)
            plant.assert_not_called()

    def test_plants_use_their_own_species_definition(self):
        with patch.object(
            flower_art,
            "paint_collection_flower",
            wraps=flower_art.paint_collection_flower,
        ) as plant:
            for item in COLLECTIONS["식물"]:
                with self.subTest(item=item.key):
                    self.assertFalse(preview_image(item).isNull())
                    self.assertIs(plant.call_args.args[2], PLANTS[item.key])

    def test_shared_ids_have_distinct_category_images_in_both_cache_orders(self):
        for first_category, second_category, key in (
            ("식물", "정원", "lavender"),
            ("식물", "화분", "rose"),
        ):
            for order in (
                (first_category, second_category),
                (second_category, first_category),
            ):
                preview_image.cache_clear()
                items = [
                    next(item for item in COLLECTIONS[c] if item.key == key)
                    for c in order
                ]
                images = [preview_image(item) for item in items]
                self.assertNotEqual(
                    hashlib.sha256(images[0].bits()).hexdigest(),
                    hashlib.sha256(images[1].bits()).hexdigest(),
                )
                self.assertEqual(
                    bytes(preview_image(items[0]).bits()), bytes(images[0].bits())
                )

    def test_all_157_items_have_explicit_category_and_matching_metadata(self):
        identities = set()
        for title, category, source in (
            ("식물", "plant", PLANTS),
            ("정원", "garden", THEMES),
            ("화분", "pot", POT_SKINS),
        ):
            for item in COLLECTIONS[title]:
                self.assertEqual(item.category, category)
                self.assertEqual(item.name, source[item.key].name)
                self.assertNotIn((item.category, item.key), identities)
                identities.add((item.category, item.key))
        self.assertEqual(len(identities), 157)

    def test_invalid_category_or_mismatched_name_is_rejected(self):
        item = next(i for i in COLLECTIONS["정원"] if i.key == "lavender")
        for changes in (
            {"category": "plant"},
            {"category": "unknown"},
            {"key": "daisy"},
            {"name": "다른 식물"},
        ):
            with self.assertRaises(ValueError):
                replace(item, **changes)
