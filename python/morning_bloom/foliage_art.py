"""Species-specific foliage silhouettes, shared by every game preview.

Artwork follows the supplied eight-plant reference, including its cream
philodendron patches. Pots, names, rarity and growth rules remain independent.
All markings use path intersections so SVG exports retain the same geometry.
"""

import math
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPainterPathStroker, QPen, QTransform


def _path(start, curves):
    result = QPainterPath(QPointF(*start))
    for curve in curves:
        result.cubicTo(*curve)
    result.closeSubpath()
    return result


def _fill(painter, path, color):
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawPath(path)


def _stroke(painter, path, color, width):
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawPath(path)


def _stem(painter, start, control, end, color='#79965c', width=3):
    path = QPainterPath(QPointF(*start))
    path.quadTo(QPointF(*control), QPointF(*end))
    _stroke(painter, path, color, width)


def _boolean(first, second, subtract=False):
    # Qt flattens curves for boolean operations. Unit-sized paths otherwise
    # lose their round edges before the leaf is enlarged to screen size.
    up, down = QTransform().scale(100, 100), QTransform().scale(.01, .01)
    a, b = up.map(first), up.map(second)
    return down.map(a.subtracted(b) if subtract else a.intersected(b))


@lru_cache(maxsize=None)
def _blade(kind):
    if kind == 'oval':
        return _path((0, 0), [(-.5, -.25, -.48, -.83, 0, -1),
                              (.48, -.83, .5, -.25, 0, 0)])
    if kind == 'heart':
        # Petiole attaches at the notch; the tip hangs below the lobes.
        return _path((0, -.56), [(-.22, -.98, -.67, -.76, -.53, -.28),
                                (-.46, .03, -.15, .12, 0, .4),
                                (.15, .12, .46, .03, .53, -.28),
                                (.67, -.76, .22, -.98, 0, -.56)])
    if kind == 'monstera':
        path = _path((0, 0), [(-.18, -.12, -.63, .08, -.57, -.48),
                              (-.55, -.88, -.18, -1.02, 0, -.97),
                              (.31, -1.05, .62, -.72, .59, -.42),
                              (.58, -.02, .19, -.11, 0, 0)])
        # Open edge splits plus internal fenestrations, rather than a spear.
        for sign in (-1, 1):
            for y, depth in ((-.31, .3), (-.53, .24)):
                split = _path((sign * .68, y - .13), [
                    (sign * .43, y - .12, sign * depth, y - .05, sign * depth, y),
                    (sign * depth, y + .06, sign * .47, y + .04, sign * .68, y + .1)])
                path = _boolean(path, split, subtract=True)
        for x, y, w, h in ((-.28, -.76, .14, .08), (.13, -.81, .11, .16),
                            (-.16, -.59, .09, .14)):
            hole = QPainterPath()
            hole.addEllipse(QRectF(x, y, w, h))
            path = _boolean(path, hole, subtract=True)
        return path
    raise ValueError(kind)


def _oval(painter, x, y, angle, size, color):
    painter.save()
    painter.translate(x, y)
    painter.rotate(angle)
    painter.scale(size, size)
    _fill(painter, _blade('oval'), color)
    painter.restore()


def _heart(painter, x, y, angle, size, color, patch=None, veins=None):
    painter.save()
    painter.translate(x, y)
    painter.rotate(angle)
    painter.scale(size, size)
    shape = _blade('heart')
    _fill(painter, shape, color)
    if patch:
        if veins == 'pink':
            # Broad creamy interior with a green margin, not a half-leaf tint.
            painter.save()
            painter.scale(.81, .81)
            _fill(painter, shape, patch)
            painter.restore()
        else:
            sector = _path((.02, -.85), [(.6, -.66, .4, -.24, .06, -.24),
                                         (-.21, -.23, .22, -.03, .12, .5),
                                         (.9, .45, .9, -1, .02, -.85)])
            _fill(painter, _boolean(shape, sector), patch)
    if veins:
        vein = QPainterPath(QPointF(0, -.57))
        vein.cubicTo(-.04, -.3, .03, .05, 0, .29)
        for x1, y1, x2, y2 in ((0, -.31, -.35, -.55), (0, -.31, .35, -.55),
                               (0, -.16, -.4, -.23), (0, -.16, .4, -.23),
                               (0, .02, -.2, -.02), (0, .02, .2, -.02)):
            vein.moveTo(x1, y1)
            vein.lineTo(x2, y2)
        stroker = QPainterPathStroker()
        stroker.setWidth(.045 if veins == 'pink' else .034)
        stroker.setCapStyle(Qt.RoundCap)
        _fill(painter, _boolean(shape, stroker.createStroke(vein)),
              '#ecaaa2' if veins == 'pink' else '#b9cdb4')
    painter.restore()


def _blossom(painter, x, y, radius, pink=False):
    painter.setPen(Qt.NoPen)
    for n in range(5 if pink else 7):
        angle = math.tau * n / (5 if pink else 7) - math.pi / 2
        painter.setBrush(QColor('#f7c8ba' if pink else '#f9e6ba'))
        painter.drawEllipse(QPointF(x + math.cos(angle) * radius * .62,
                                   y + math.sin(angle) * radius * .62),
                            radius * .5, radius * .5)
    if pink:
        star = QPainterPath()
        for n in range(10):
            a = n * math.pi / 5 - math.pi / 2
            r = radius * (.43 if n % 2 == 0 else .22)
            point = QPointF(x + math.cos(a) * r, y + math.sin(a) * r)
            star.moveTo(point) if n == 0 else star.lineTo(point)
        star.closeSubpath()
        _fill(painter, star, '#d98e87')
    else:
        painter.setBrush(QColor('#efbf61'))
        painter.drawEllipse(QPointF(x, y), radius * .43, radius * .32)


def _monstera(painter, stage):
    if stage == 1:
        _oval(painter, 0, 0, -48, 43, '#83a370')
        _oval(painter, 0, 0, 48, 43, '#729763')
        return
    leaves = ((-19, -23, -42, 59, '#80a177'),
              (12, -36, 37, 60, '#70966e'),
              (-4, -50, -17, 55, '#8aaa79'))[:2 if stage == 2 else 3]
    for x, y, angle, size, color in leaves:
        _stem(painter, (0, 2), (x, -19), (x, y), width=4)
    for x, y, angle, size, color in reversed(leaves):
        painter.save()
        painter.translate(x, y)
        painter.rotate(angle)
        painter.scale(size, size)
        shape = _blade('monstera')
        _fill(painter, shape, color)
        if stage == 4 and angle == 37:
            patch = _path((.12, -.98), [(.4, -.79, .25, -.62, .02, -.58),
                                       (-.2, -.49, .16, -.34, .18, -.06),
                                       (.75, -.1, .73, -.98, .12, -.98)])
            _fill(painter, _boolean(shape, patch), '#eee4b8')
        painter.restore()
    if stage == 4:
        _oval(painter, 8, -1, 70, 30, '#7e9f69')


def _hoya(painter, stage):
    if stage == 1:
        for angle, size in ((-65, 42), (5, 37), (60, 44)):
            _oval(painter, 0, 0, angle, size, '#80a06c')
        return
    _stem(painter, (-3, 1), (-27, -105), (23, -83), width=4)
    vine = QPainterPath(QPointF(20, -81))
    vine.cubicTo(60, -66, 39, -20, 47, 4)
    vine.cubicTo(57, 28, 41, 49, 26, 48)
    _stroke(painter, vine, '#789655', 3.5)
    leaves = ((-8, -37, -63, 44), (0, -62, -28, 42), (17, -65, 33, 41),
              (24, -32, 40, 44), (-27, -27, -31, 40), (-20, -6, -56, 35),
              (-10, -15, 8, 42), (37, -14, 52, 32), (48, 9, 103, 26),
              (48, 26, -45, 25), (34, 42, 65, 24), (29, 53, -28, 22))
    for n, (x, y, angle, size) in enumerate(leaves):
        _oval(painter, x, y, angle, size, ('#708d59', '#8ea862', '#78975f')[n % 3])
    if stage == 4:
        vine = QPainterPath(QPointF(-24, -35))
        vine.cubicTo(-56, -20, -48, 22, -32, 39)
        _stroke(painter, vine, '#789655', 3)
        for x, y, a in ((-43, -3, -40), (-46, 16, 45), (-32, 40, -20)):
            _oval(painter, x, y, a, 22, '#78975f')
    if stage >= 3:
        flowers = ((-12, -65, 10), (-5, -79, 9), (7, -62, 10),
                   (16, -50, 10), (27, -78, 8), (47, 26, 7))
        for x, y, r in flowers[:3 if stage == 3 else 6]:
            _blossom(painter, x, y, r, pink=True)


def _snake(painter, stage):
    blades = ((4, 116, 8, 17), (-13, 100, -24, 15), (16, 84, 29, 14),
              (-20, 49, -24, 11), (23, 39, 22, 10))
    for x, height, lean, width in blades[:(0, 1, 2, 3, 5)[stage]]:
        blade = _path((x - 7, 1), [
            (x - width, -height * .35, x + lean - width * .65, -height * .8, x + lean, -height),
            (x + lean + width * .2, -height * .82, x + width, -height * .3, x + 7, 1)])
        _fill(painter, blade, '#65835b')
        for n in range(1, int(height / 10)) if stage > 1 else ():
            y = -n * 10
            stripe = _path((x - 45, y), [(x - 15, y - 7, x + 3, y + 7, x + 48, y - 2),
                                         (x + 48, y + 7, x - 12, y + 6, x - 45, y + 5)])
            _fill(painter, blade.intersected(stripe), '#7f9865')
        _stroke(painter, blade, '#e9dca5', 2.2)


def _philodendron(painter, stage):
    leaves = ((5, -69, -24, 47), (-30, -39, 28, 44),
              (29, -38, -31, 46), (-7, -13, 21, 47), (42, 5, -24, 40))
    for x, y, angle, size in leaves[:(0, 1, 2, 3, 5)[stage]]:
        _stem(painter, (0, 0), (x * .6, y - 25), (x, y - size * .4), width=3)
        _heart(painter, x, y, angle, size, '#7d9e6c', patch='#f0e3b7' if stage >= 3 else None)


def _caladium(painter, stage):
    for x, y, angle, size in ((-21, -53, 32, 68), (26, -36, -35, 62))[:1 if stage == 1 else 2]:
        _stem(painter, (0, 2), (x * .4, -26), (x, y - 15), width=4)
        _heart(painter, x, y, angle, size, '#87a16b', patch='#f5e6bf', veins='pink')
    if stage >= 3:
        _oval(painter, 2, 1, 62, 24, '#88a86c')


def _alocasia(painter, stage):
    leaves = [(-24, -49, 39, 68), (24, -59, -29, 67)][:1 if stage == 1 else 2]
    if stage == 4:
        leaves.insert(0, (0, -76, -5, 40))
    for x, y, angle, size in leaves:
        _stem(painter, (0, 2), (x * .6, -25), (x, y - 12), width=4)
        _heart(painter, x, y, angle, size, '#4f7160', veins='pale')
    if stage >= 3:
        _oval(painter, -1, 1, -22, 24, '#8ba667')
        _oval(painter, 5, 1, 35, 24, '#76935a')


def _lithops(painter, stage):
    for x, y, radius in ((0, -31, 25), (-27, -14, 25), (23, -12, 29))[:min(stage, 3)]:
        body = QPainterPath()
        body.addEllipse(QRectF(x - radius, y - radius * .64, radius * 2, radius * 1.32))
        _fill(painter, body, '#b6a49a')
        top = QPainterPath()
        top.addEllipse(QRectF(x - radius, y - radius * .78, radius * 2, radius * 1.05))
        _fill(painter, top, '#c8b4a4')
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#b49e8e'))
        for n in range(25):
            a = n * 2.39996
            distance = radius * .82 * math.sqrt((n + .5) / 25)
            painter.drawEllipse(QPointF(x + math.cos(a) * distance,
                                       y - radius * .24 + math.sin(a) * distance * .5),
                                1.6 + n % 3 * .3, 1.1 + n % 2 * .4)
        seam = QPainterPath(QPointF(x + 2, y - radius * .65))
        seam.cubicTo(x - 8, y - 4, x - 3, y + 8, x + 1, y + radius * .55)
        _stroke(painter, seam, '#a38c80', 2)
        if stage == 4:
            _blossom(painter, x, y - radius * .85 - 4, 10 if x else 13)


def _fern(painter, stage):
    # Curved fronds with blunt overlapping pinnae, including hanging outer tips.
    fronds = ((6, -104, -10, -72), (-34, -85, -17, -69), (49, -78, 10, -68),
              (-64, -23, -48, -75), (64, -20, 43, -80), (-62, 30, -75, -77),
              (65, 28, 78, -64), (-34, 21, -44, -48), (39, 28, 53, -49))
    for n, (end_x, end_y, bend_x, bend_y) in enumerate(fronds[:(0, 2, 4, 6, 9)[stage]]):
        path = QPainterPath(QPointF(0, 2))
        path.quadTo(bend_x, bend_y, end_x, end_y)
        color = ('#aa7786', '#986878', '#b68191')[n % 3]
        _stroke(painter, path, color, 3)
        for step in range(3, 17):
            t = step / 17
            point = path.pointAtPercent(t)
            tangent = path.pointAtPercent(min(.999, t + .01)) - point
            angle = math.degrees(math.atan2(tangent.y(), tangent.x())) + 90
            size = 10.5 * (1 - .65 * t)
            for side in (-1, 1):
                painter.save()
                painter.translate(point)
                painter.rotate(angle + side * 60)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(color))
                painter.drawEllipse(QRectF(-size * .42, -size, size * .84, size * 1.23))
                painter.restore()


_PAINTERS = (_monstera, _hoya, _snake, _philodendron,
             _caladium, _alocasia, _lithops, _fern)


def paint_foliage(painter, key, stage, phase):
    """Draw foliage above the independently selected pot in a 380×180 scene."""
    painter.save()
    painter.translate(190 + math.sin(phase) * 1.5, 105)
    if stage == 0:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#7f644b'))
        painter.drawEllipse(QRectF(-3, -2, 6, 3))
    else:
        # The main pot and mist game use the raw 180px scene without the
        # collection card's top padding. Leave room for the tallest leaf.
        scale = .88 * (0, .42, .63, .83, 1)[stage]
        painter.scale(scale, scale)
        _PAINTERS[int(key[-3:])](painter, stage)
    painter.restore()
