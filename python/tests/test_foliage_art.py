"""Guard shared card bounds and stage-specific details of foliage artwork."""
import math
import unittest

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from morning_bloom.flower_art import paint_collection_flower, paint_potted_flower
from morning_bloom.foliage_art import paint_foliage
from morning_bloom.plant_catalog import CATALOG_GACHA_PLANTS, PLANTS


class FoliageArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_every_stage_fits_card_at_both_sway_extremes(self):
        for key in CATALOG_GACHA_PLANTS:
            for stage in range(5):
                for width, height in ((64, 64), (96, 96), (120, 182)):
                    for phase in (-math.pi / 2, math.pi / 2):
                        with self.subTest(key=key, stage=stage, size=(width, height), phase=phase):
                            image = QImage(width + 40, height + 40, QImage.Format_ARGB32)
                            image.fill(Qt.transparent)
                            painter = QPainter(image)
                            painter.setRenderHint(QPainter.Antialiasing)
                            rect = QRectF(20, 20, width, height)
                            paint_collection_flower(painter, rect, PLANTS[key], stage=stage, phase=phase)
                            painter.end()
                            # Erase the allowed area; any remaining pixels are overflow.
                            painter = QPainter(image)
                            painter.setCompositionMode(QPainter.CompositionMode_Source)
                            painter.fillRect(rect, Qt.transparent)
                            painter.end()
                            self.assertFalse(any(bytes(image.constBits())))

    def test_foliage_restores_callers_painter_state(self):
        image = QImage(400, 240, QImage.Format_ARGB32)
        for key in CATALOG_GACHA_PLANTS:
            painter = QPainter(image)
            painter.translate(4, 7)
            painter.setPen(QColor('red'))
            painter.setBrush(QColor('blue'))
            before = (painter.transform(), painter.pen(), painter.brush())
            paint_foliage(painter, key, 4, 1)
            after = (painter.transform(), painter.pen(), painter.brush())
            painter.end()
            self.assertEqual(before, after, key)

    def test_main_scene_and_desktop_mask_do_not_clip_foliage(self):
        for key in CATALOG_GACHA_PLANTS:
            for phase in (-math.pi / 2, math.pi / 2):
                for desktop in (False, True):
                    with self.subTest(key=key, phase=phase, desktop=desktop):
                        image = QImage(420, 260, QImage.Format_ARGB32)
                        image.fill(Qt.transparent)
                        painter = QPainter(image)
                        painter.setRenderHint(QPainter.Antialiasing)
                        if desktop:
                            paint_collection_flower(painter, QRectF(68, 32, 120, 182), PLANTS[key], phase=phase)
                            allowed = QRectF(74, 36, 108, 173)
                        else:
                            painter.translate(20, 20)
                            paint_potted_flower(painter, PLANTS[key], phase=phase)
                            painter.resetTransform()
                            allowed = QRectF(20, 20, 380, 180)
                        painter.setCompositionMode(QPainter.CompositionMode_Source)
                        painter.fillRect(allowed, Qt.transparent)
                        painter.end()
                        self.assertFalse(any(bytes(image.constBits())))

    def test_hoya_flowers_and_monstera_variegation_appear_at_correct_stages(self):
        for key, color, first_stage in (
            ('catalog_plant_000', '#eee4b8', 4),
            ('catalog_plant_001', '#f7c8ba', 3),
            ('catalog_plant_006', '#f9e6ba', 4),
        ):
            for stage in range(1, 5):
                image = QImage(380, 200, QImage.Format_ARGB32)
                image.fill(Qt.transparent)
                painter = QPainter(image)
                paint_foliage(painter, key, stage, 0)
                painter.end()
                target = QColor(color).rgba()
                found = target in memoryview(image.constBits()).cast('I')
                self.assertEqual(found, stage >= first_stage, (key, stage))
