"""Shared vector flowers for the growing pot, collection and drag preview."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen

from .cosmetics import pot_skin


def paint_potted_flower(painter, definition, stage=4, phase=0, planted=True, drops=0, skin='terracotta'):
    """Draw in a 380 x 180 scene; the actual pot is centered on x=190."""
    painter.save()
    painter.setPen(Qt.NoPen)
    style = pot_skin(skin)
    painter.setBrush(QColor(style.edge))
    painter.drawRoundedRect(QRectF(144, 112, 92, 49), 14, 14)
    painter.setBrush(QColor(style.body or definition.pot_color))
    painter.drawRoundedRect(QRectF(148, 119, 84, 43), 12, 12)
    painter.setBrush(QColor(style.rim))
    if style.pattern == 'stripes':
        for x in range(158, 225, 13):
            painter.drawRoundedRect(QRectF(x, 127, 3, 23), 1.5, 1.5)
    elif style.pattern == 'dots':
        for y in (131, 145):
            for x in (164, 181, 198, 215):
                painter.drawEllipse(QRectF(x, y, 5, 5))
    elif style.pattern == 'band':
        painter.drawRect(QRectF(149, 132, 82, 9))
    painter.drawRoundedRect(QRectF(136, 104, 108, 18), 6, 6)
    painter.setBrush(QColor('#654638'))
    painter.drawEllipse(QRectF(143, 101, 94, 12))
    if planted:
        top = 98 - stage * 18
        sway = math.sin(phase) * 3
        painter.setPen(QPen(QColor('#64835b'), 5, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(190, 106), QPointF(190 + sway, top))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(definition.leaf_color))
        if stage:
            painter.drawEllipse(QRectF(164 + sway, top + 18, 28, 12))
            painter.drawEllipse(QRectF(192 + sway, top + 8, 29, 13))
        if stage >= 3:
            painter.save()
            painter.translate(190 + sway, top)
            if definition.key == 'ancient':
                painter.setPen(QPen(QColor('#d8bc6b'), 1.5))
                painter.drawEllipse(QRectF(-33, -33, 66, 66))
                painter.setPen(Qt.NoPen)
                _starflower(painter, definition, stage == 4)
                painter.rotate(36)
                painter.scale(.65, .65)
                _starflower(painter, definition, stage == 4)
            elif definition.key == 'tulip':
                _tulip(painter, definition, stage == 4)
            elif definition.key == 'starflower':
                _starflower(painter, definition, stage == 4)
            else:
                _daisy(painter, definition, stage == 4)
            painter.restore()
        else:
            painter.drawEllipse(QRectF(183 + sway, top - 6, 14, 10))
    if drops:
        painter.setBrush(QColor('#81b8ce'))
        for index in range(7):
            y = 24 + ((30 - drops) * 4 + index * 13) % 76
            painter.drawEllipse(QRectF(140 + index * 16, y, 4, 9))
    painter.restore()


def paint_collection_flower(painter, rect, definition, phase=0, skin='terracotta'):
    """Fit the flower itself, without the empty sides of the growing scene."""
    scale = min(rect.width() / 138, rect.height() / 190)
    painter.save()
    painter.translate(rect.center().x() - 190 * scale, rect.top() + 16 * scale)
    painter.scale(scale, scale)
    paint_potted_flower(painter, definition, phase=phase, skin=skin)
    painter.restore()


def _daisy(painter, definition, opened):
    for index in range(8):
        painter.save()
        painter.rotate(index * 45)
        painter.setBrush(QColor(definition.petal_color))
        painter.drawEllipse(QRectF(-8, -30 if opened else -18, 16, 27 if opened else 17))
        painter.restore()
    painter.setBrush(QColor(definition.center_color))
    painter.drawEllipse(QRectF(-10, -10, 20, 20))


def _tulip(painter, definition, opened):
    width, top = (25, -34) if opened else (18, -25)
    flower = QPainterPath()
    flower.moveTo(-width, -3)
    flower.lineTo(-width + 3, top)
    flower.lineTo(0, top + (12 if opened else 6))
    flower.lineTo(width - 3, top)
    flower.lineTo(width, -3)
    flower.quadTo(0, 13, -width, -3)
    painter.setBrush(QColor(definition.petal_color))
    painter.drawPath(flower)
    painter.setBrush(QColor(definition.center_color))
    painter.drawEllipse(QRectF(-5, -8, 10, 8))


def _starflower(painter, definition, opened):
    length = 24 if opened else 15
    for index in range(5):
        painter.save()
        painter.rotate(index * 72)
        petal = QPainterPath()
        petal.moveTo(0, -3)
        petal.lineTo(-7, -length)
        petal.lineTo(0, -length - 7)
        petal.lineTo(7, -length)
        petal.closeSubpath()
        painter.setBrush(QColor(definition.petal_color))
        painter.drawPath(petal)
        painter.restore()
    painter.setBrush(QColor(definition.center_color))
    painter.drawEllipse(QRectF(-7, -7, 14, 14))
