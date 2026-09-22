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
        if not (stage >= 3 and definition.key in ('lily_of_the_valley', 'freesia')):
            painter.drawLine(QPointF(190, 106), QPointF(190 + sway, top))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(definition.leaf_color))
        if stage and not (stage >= 3 and definition.key in ('lily_of_the_valley', 'clover', 'lavender', 'cosmos', 'freesia')):
            _leaf(painter, 190 + sway, 106, -45, 24 + stage * 6, 15)
            _leaf(painter, 190 + sway, 106, 45, 26 + stage * 6, 15)
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
            elif definition.key in REFERENCE_FLOWERS:
                if stage == 3:
                    painter.scale(.72, .72)
                REFERENCE_FLOWERS[definition.key](painter, definition)
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


def paint_collection_flower(painter, rect, definition, phase=0, skin='terracotta', stage=4):
    """Fit the flower itself, without the empty sides of the growing scene."""
    scale = min(rect.width() / 138, rect.height() / 190)
    painter.save()
    painter.translate(rect.center().x() - 190 * scale, rect.top() + 16 * scale)
    painter.scale(scale, scale)
    paint_potted_flower(painter, definition, stage=stage, phase=phase, skin=skin)
    painter.restore()


def _daisy(painter, definition, opened):
    for index in range(6):
        painter.save()
        painter.rotate(index * 60)
        painter.setBrush(QColor(definition.petal_color))
        painter.drawEllipse(QRectF(-11, -33 if opened else -19, 22, 29 if opened else 18))
        painter.restore()
    painter.setBrush(QColor(definition.center_color))
    painter.drawEllipse(QRectF(-10, -10, 20, 20))


def _tulip(painter, definition, opened):
    width, top = (26, -33) if opened else (18, -25)
    flower = QPainterPath()
    flower.moveTo(0, 9)
    flower.cubicTo(-width - 8, 9, -width - 7, top - 8, -14, top + 4)
    flower.quadTo(-5, top - 8, 2, top + 2)
    flower.quadTo(18, top - 13, width, top + 5)
    flower.cubicTo(width + 8, -6, 19, 10, 0, 9)
    painter.setBrush(QColor(definition.petal_color))
    painter.drawPath(flower)
    painter.setPen(QPen(QColor('#df6f83'), 2.5, Qt.SolidLine, Qt.RoundCap))
    fold = QPainterPath(QPointF(-13, top + 5))
    fold.quadTo(0, top + 12, 2, -4)
    painter.drawPath(fold)
    painter.setPen(Qt.NoPen)


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


def _rose(painter, definition):
    painter.setBrush(QColor(definition.petal_color))
    for index in range(6):
        angle = index * math.tau / 6
        painter.drawEllipse(QPointF(math.cos(angle) * 13, math.sin(angle) * 13), 20, 19)
    spiral = QPainterPath(QPointF(2, 0))
    for index in range(1, 101):
        angle, radius = index * .14, 2 + index * .22
        spiral.lineTo(math.cos(angle) * radius, math.sin(angle) * radius)
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor(definition.center_color), 3.5, Qt.SolidLine, Qt.RoundCap))
    painter.drawPath(spiral)
    painter.setPen(Qt.NoPen)


def _leaf(painter, x, y, angle, length=40, width=13):
    painter.save()
    painter.translate(x, y)
    painter.rotate(angle)
    leaf = QPainterPath(QPointF(0, 0))
    leaf.cubicTo(-width, -length / 3, -width, -length * .8, 0, -length)
    leaf.cubicTo(width, -length * .8, width, -length / 3, 0, 0)
    painter.drawPath(leaf)
    painter.restore()


def _lily(painter, definition):
    painter.setBrush(QColor(definition.leaf_color))
    _leaf(painter, 0, 76, -25, 62, 15)
    _leaf(painter, 6, 77, 35, 68, 17)
    stem = QPainterPath(QPointF(4, 78))
    stem.cubicTo(5, 13, -12, -40, -32, -15)
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor(definition.leaf_color), 4, Qt.SolidLine, Qt.RoundCap))
    painter.drawPath(stem)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(definition.petal_color))
    for x, y in ((-32, -8), (-16, 7), (-4, 25), (7, 44)):
        painter.drawEllipse(QRectF(x - 9, y - 9, 18, 18))
        for dx in (-7, 0, 7):
            painter.drawEllipse(QPointF(x + dx, y + 4), 5, 5)


def _clover(painter, definition):
    painter.setBrush(QColor(definition.leaf_color))
    for x, y in ((-27, 59), (27, 54)):
        for angle in (-90, 30, 150):
            radians = math.radians(angle)
            painter.drawEllipse(QPointF(x + math.cos(radians) * 9, y + math.sin(radians) * 9), 10, 11)
    painter.setBrush(QColor(definition.center_color))
    painter.drawEllipse(QPointF(0, 0), 25, 25)
    for ring, count in ((19, 11), (10, 7), (0, 1)):
        for index in range(count):
            angle = index * math.tau / count
            painter.setBrush(QColor(definition.petal_color))
            painter.drawEllipse(QRectF(math.cos(angle) * ring - 4, math.sin(angle) * ring - 8, 8, 15))


def _sunflower(painter, definition):
    painter.setBrush(QColor(definition.petal_color))
    for index in range(12):
        painter.save()
        painter.rotate(index * 30)
        painter.drawEllipse(QRectF(-8, -35, 16, 28))
        painter.restore()
    painter.setBrush(QColor(definition.center_color))
    painter.drawEllipse(QPointF(0, 0), 17, 17)
    painter.setBrush(QColor('#805532'))
    for index in range(8):
        angle = index * 2.4
        radius = 3 + index * 1.2
        painter.drawEllipse(QPointF(math.cos(angle) * radius, math.sin(angle) * radius), 2.3, 2.3)


def _lavender(painter, definition):
    painter.setBrush(QColor(definition.leaf_color))
    for x, angle in ((-3, -42), (3, 42)):
        _leaf(painter, x, 76, angle, 45, 9)
    for x, y, scale in ((-17, 20, .8), (17, 16, .8), (0, -15, 1)):
        painter.setPen(QPen(QColor(definition.leaf_color), 3, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(x, y), QPointF(0, 76))
        painter.setPen(Qt.NoPen)
        for index in range(5):
            radius = (4 + index) * scale
            painter.setBrush(QColor(definition.petal_color if index % 2 else '#a47ac1'))
            for side in (-1, 1):
                painter.drawEllipse(QPointF(x + side * radius * .55, y + index * 11 * scale), radius, radius * .8)


def _forget_me_not(painter, definition):
    for x, y in ((-24, 15), (11, -10), (29, 37)):
        painter.setPen(QPen(QColor(definition.leaf_color), 3))
        painter.drawLine(QPointF(x, y), QPointF(0, 76))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(definition.petal_color))
        for index in range(5):
            angle = index * math.tau / 5 - math.pi / 2
            painter.drawEllipse(QPointF(x + math.cos(angle) * 10, y + math.sin(angle) * 10), 9, 9)
        painter.setBrush(QColor(definition.center_color))
        painter.drawEllipse(QPointF(x, y), 4.5, 4.5)


def _pansy(painter, definition):
    painter.setBrush(QColor(definition.petal_color))
    painter.drawEllipse(QRectF(-32, -30, 36, 37))
    painter.setBrush(QColor('#9572b3'))
    painter.drawEllipse(QRectF(-5, -36, 39, 43))
    painter.setBrush(QColor(definition.center_color))
    for x, y, width, height in ((-32, -8, 35, 33), (0, -9, 35, 33), (-20, 6, 42, 31)):
        painter.drawEllipse(QRectF(x, y, width, height))
    painter.setBrush(QColor('#765398'))
    for angle in (-62, 62, 145, 215):
        painter.save()
        painter.translate(1, 7)
        painter.rotate(angle)
        painter.drawEllipse(QRectF(-4, -15, 8, 13))
        painter.restore()
    painter.setBrush(QColor('#eab947'))
    painter.drawEllipse(QPointF(1, 7), 3.5, 3.5)


def _cosmos(painter, definition):
    painter.setPen(QPen(QColor(definition.leaf_color), 2.5, Qt.SolidLine, Qt.RoundCap))
    for side in (-1, 1):
        painter.drawLine(QPointF(0, 76), QPointF(side * 27, 45))
        painter.setBrush(QColor(definition.leaf_color))
        for index in range(3):
            x, y = side * (8 + index * 7), 68 - index * 8
            for angle in (side * 28, side * 85):
                _leaf(painter, x, y, angle, 19, 3)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(definition.petal_color))
    for index in range(8):
        painter.save()
        painter.rotate(index * 45)
        petal = QPainterPath(QPointF(0, 0))
        petal.cubicTo(-7, -5, -18, -28, -7, -31)
        petal.quadTo(-2, -33, 0, -29)
        petal.quadTo(6, -34, 10, -28)
        petal.cubicTo(15, -19, 7, -3, 0, 0)
        painter.drawPath(petal)
        painter.restore()
    painter.setBrush(QColor(definition.center_color))
    painter.drawEllipse(QPointF(0, 0), 9, 8)


def _freesia(painter, definition):
    painter.setBrush(QColor(definition.leaf_color))
    _leaf(painter, 0, 77, -32, 65, 11)
    _leaf(painter, 3, 78, 21, 83, 10)
    _leaf(painter, 4, 78, 48, 51, 9)
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor(definition.leaf_color), 3.5, Qt.SolidLine, Qt.RoundCap))
    stem = QPainterPath(QPointF(0, 78))
    stem.quadTo(-3, 10, 35, -5)
    painter.drawPath(stem)
    blooms = ((-23, 9, 1), (-3, -9, .85), (19, -13, .65))
    for x, y, scale in blooms:
        painter.drawLine(QPointF(2, 45), QPointF(x, y))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(definition.leaf_color))
    _leaf(painter, 30, 2, 40, 20, 6)
    for x, y, scale in reversed(blooms):
        painter.save()
        painter.translate(x, y)
        painter.scale(scale, scale)
        painter.setBrush(QColor(definition.petal_color))
        for index in range(6):
            angle = index * math.tau / 6
            painter.drawEllipse(QPointF(math.cos(angle) * 12, math.sin(angle) * 12), 11, 14)
        painter.setBrush(QColor(definition.center_color))
        painter.drawEllipse(QPointF(0, 1), 10, 9)
        painter.setBrush(QColor('#fbe386'))
        painter.drawEllipse(QPointF(-2, 3), 5, 4)
        painter.restore()


REFERENCE_FLOWERS = {
    'rose': _rose, 'lily_of_the_valley': _lily, 'clover': _clover,
    'sunflower': _sunflower, 'lavender': _lavender, 'forget_me_not': _forget_me_not,
    'pansy': _pansy, 'cosmos': _cosmos, 'freesia': _freesia,
}
