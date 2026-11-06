"""Shared plant/pot preview with a short repotting movement."""
from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget
from .flower_art import paint_collection_flower, paint_potted_flower
from .plant_catalog import plant_definition


class PotPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(110, 76)
        self.choice = None
        self.progress = 1.0
        self.effect = QVariantAnimation(self)
        self.effect.setDuration(240)
        self.effect.setEasingCurve(QEasingCurve.OutCubic)
        self.effect.valueChanged.connect(self.animate)

    def animate(self, value):
        self.progress = float(value)
        self.update()

    def show_choice(self, species, skin, color, planted, animate=False, stage=4):
        self.choice = species, skin, color, planted, stage
        if animate:
            self.effect.stop()
            self.effect.setStartValue(0.0)
            self.effect.setEndValue(1.0)
            self.effect.start()
        else:
            self.update()

    def paintEvent(self, event):
        if self.choice is None:
            return
        species, skin, color, planted, stage = self.choice
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(0, -(1-self.progress)*7)
        if planted:
            paint_collection_flower(painter, QRectF(0, 0, self.width(), self.height()), plant_definition(species),
                                    skin=skin, pot_color=color, stage=stage)
        else:
            scale = .75
            painter.translate(self.width()/2 - 190*scale, -62)
            painter.scale(scale, scale)
            paint_potted_flower(painter, plant_definition(species), planted=False, skin=skin, pot_color=color)
        painter.end()

