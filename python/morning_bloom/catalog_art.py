"""Resolution-independent artwork for the new catalog; no text-bearing sprites."""

import math
import random
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen


def paint_catalog_pot(painter, style):
    name = style.name
    index = int(style.key[-3:])
    rng = random.Random(index)
    wide = name in ("와이드", "샬로우", "미니")
    round_body = name in ("라운드", "우드", "핑크 스톤", "테라조")
    left, right = (140, 240) if wide else (148, 232)
    bottom = 149 if wide else 164
    if name == "미니":
        left, right, bottom = 153, 227, 153
    if "핸들" in name or name == "양손잡이":
        painter.setPen(QPen(QColor(style.body), 5))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(left - 12, 119, 19, 23))
        painter.drawEllipse(QRectF(right - 7, 119, 19, 23))
    body = QPainterPath()
    body.moveTo(left - 2, 117)
    body.cubicTo(left - 1, bottom, left + 5, bottom + 3, 190, bottom + 3)
    body.cubicTo(right - 5, bottom + 3, right + 1, bottom, right + 2, 117)
    body.closeSubpath()
    painter.setPen(QPen(QColor(style.edge), 1))
    painter.setBrush(QColor(style.body))
    painter.drawPath(body)
    painter.save()
    painter.setClipPath(body)
    if name in (
        "스톤",
        "핑크 스톤",
        "크림 스톤",
        "테라조",
        "시멘트",
        "핸들 스톤",
        "샌드",
    ):
        for n in range(48):
            painter.setPen(Qt.NoPen)
            painter.setBrush(
                QColor(128 + n % 3 * 17, 101 + n % 4 * 12, 75 + n % 5 * 10, 130)
            )
            r = 1 + (n % 3) * 0.6
            painter.drawEllipse(
                QRectF(rng.uniform(left, right), rng.uniform(119, bottom), r, r * 1.3)
            )
    elif "체크" in name:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#f6edda"))
        for y in range(117, bottom, 10):
            for x in range(left, right, 10):
                if ((x - left) // 10 + (y - 117) // 10) % 2 == 0:
                    painter.drawRect(QRectF(x, y, 10, 10))
    elif any(
        x in name
        for x in ("리브드", "플루트", "블루 라인", "주름", "스트라이프", "라벤더")
    ):
        painter.setPen(
            QPen(QColor("#eee6d2") if "스트라이프" in name else QColor(style.edge), 2.5)
        )
        if name == "스트라이프":
            for y in range(126, bottom, 12):
                painter.drawLine(left, y, right, y)
        else:
            for x in range(left + 7, right, 11):
                painter.drawLine(x, 121, x + (-3 if x < 190 else 3), bottom - 3)
    elif any(x in name for x in ("패턴", "데이지", "플라워", "도트")):
        for x, y in ((166, 131), (192, 145), (216, 131)):
            if "리프" in name:
                painter.setPen(QPen(QColor("#6d8857"), 1))
                painter.drawLine(x, y + 8, x, y - 7)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#7e975f"))
                painter.drawEllipse(QRectF(x - 7, y - 6, 7, 4))
                painter.drawEllipse(QRectF(x, y, 7, 4))
            elif "하트" in name:
                painter.setBrush(QColor("#fff0df"))
                painter.setPen(Qt.NoPen)
                path = QPainterPath(QPointF(x, y + 5))
                path.cubicTo(x - 13, y - 3, x - 3, y - 10, x, y - 4)
                path.cubicTo(x + 3, y - 10, x + 13, y - 3, x, y + 5)
                painter.drawPath(path)
            elif name == "도트":
                painter.setBrush(QColor("#4c4a43"))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QRectF(x - 3, y - 3, 6, 6))
            else:
                flower(
                    painter,
                    x,
                    y,
                    4,
                    (
                        QColor("#f3adab")
                        if "핑크" in name or "튤립" in name
                        else QColor("#fff5dc")
                    ),
                )
    elif name == "투톤":
        painter.fillRect(QRectF(left, 121, right - left, 18), QColor("#f4ead4"))
    painter.restore()
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(style.rim))
    painter.drawRoundedRect(QRectF(left - 7, 105, right - left + 14, 15), 5, 5)
    if name in ("플라워", "핑크 플라워", "웨이브", "스카이 플라워"):
        for x in range(left - 6, right + 6, 11):
            painter.drawEllipse(QRectF(x, 103, 12, 12))
    painter.setBrush(QColor("#73543d"))
    painter.drawEllipse(QRectF(left - 2, 105, right - left + 4, 10))


def flower(painter, x, y, r, color):
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    for n in range(5):
        angle = n * math.tau / 5
        painter.drawEllipse(
            QPointF(x + math.cos(angle) * r, y + math.sin(angle) * r),
            r * 0.65,
            r * 0.65,
        )
    painter.setBrush(QColor("#e5bb66"))
    painter.drawEllipse(QPointF(x, y), r * 0.45, r * 0.45)


def leaf(
    painter, x, y, angle, size, color, variegated=None, arrow=False, fenestrated=False
):
    painter.save()
    painter.translate(x, y)
    painter.rotate(angle)
    path = QPainterPath(QPointF(0, 0))
    if arrow:
        path.lineTo(-size * 0.42, -size * 0.25)
        path.cubicTo(-size * 0.48, -size * 0.65, -size * 0.12, -size * 0.96, 0, -size)
        path.cubicTo(
            size * 0.12,
            -size * 0.96,
            size * 0.48,
            -size * 0.65,
            size * 0.42,
            -size * 0.25,
        )
        path.closeSubpath()
    else:
        path.cubicTo(-size * 0.65, -size * 0.75, -size * 0.1, -size * 1.05, 0, -size)
        path.cubicTo(size * 0.1, -size * 1.05, size * 0.65, -size * 0.75, 0, 0)
    if fenestrated:
        for sign in (-1, 1):
            for fraction in (0.37, 0.56, 0.73):
                hole = QPainterPath()
                hole.addEllipse(
                    QRectF(
                        sign * size * 0.16 - size * 0.035,
                        -size * fraction,
                        size * 0.07,
                        size * 0.14,
                    )
                )
                path = path.subtracted(hole)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawPath(path)
    if variegated:
        painter.save()
        painter.setClipPath(path)
        painter.setBrush(QColor(variegated))
        painter.drawPolygon(
            [QPointF(0, 0), QPointF(0, -size), QPointF(size, -size), QPointF(size, 0)]
        )
        painter.restore()
    painter.setClipPath(path, Qt.IntersectClip)
    painter.setPen(QPen(QColor("#c5d3b0"), max(0.7, size * 0.018)))
    painter.drawLine(QPointF(0, -size * 0.08), QPointF(0, -size * 0.92))
    for sign in (-1, 1):
        for fraction in (0.35, 0.55, 0.72):
            painter.drawLine(
                QPointF(0, -size * fraction),
                QPointF(sign * size * 0.24, -size * (fraction + 0.12)),
            )
    painter.restore()


def paint_foliage(painter, key, stage, phase):
    from .foliage_art import paint_foliage as paint_reference_foliage
    paint_reference_foliage(painter, key, stage, phase)


def paint_garden_pattern(painter, bounds, key):
    """Repeat crisp vector motifs; scene motifs retain readable foregrounds."""
    if not key.startswith("catalog_garden_"):
        return
    from .content_names import GARDEN_NAMES

    name = GARDEN_NAMES[int(key[-3:])]
    index = int(key[-3:])
    rng = random.Random(index)
    painter.save()
    painter.setClipRect(bounds)
    for row in range(bounds.top() // 80, bounds.bottom() // 80 + 1):
        for column in range(bounds.left() // 100, bounds.right() // 100 + 1):
            x = column * 100 + 20 + rng.randrange(35)
            y = row * 80 + 25 + rng.randrange(25)
            if any(s in name for s in ("돌", "자갈", "징검")):
                painter.setPen(QPen(QColor("#a6a68d"), 1))
                painter.setBrush(QColor("#d9d4b5"))
                painter.drawRoundedRect(QRectF(x - 22, y - 10, 45, 20), 9, 9)
            elif any(s in name for s in ("벽돌", "판자", "테라스")):
                painter.setPen(QPen(QColor("#ae9476"), 1))
                painter.setBrush(QColor("#c8b08d"))
                painter.drawRoundedRect(
                    QRectF(column * 100, row * 80 + 25, 96, 22), 3, 3
                )
            elif any(s in name for s in ("물가", "연못", "시냇물", "호수", "분수")):
                painter.setPen(QPen(QColor("#7db5ba"), 3))
                painter.setBrush(QColor("#a3ccd0"))
                painter.drawEllipse(QRectF(x - 34, y - 14, 68, 28))
                painter.setPen(QPen(QColor("#e2ece0"), 1))
                painter.drawArc(QRectF(x - 22, y - 8, 44, 15), 0, 160 * 16)
            elif any(s in name for s in ("울타리", "테두리")):
                painter.setPen(QPen(QColor("#b5aa83"), 2))
                painter.setBrush(QColor("#ede3bd"))
                painter.drawRoundedRect(QRectF(x - 10, y - 24, 13, 49), 3, 3)
                painter.drawLine(x - 22, y, x + 30, y)
            elif any(s in name for s in ("나무", "온실", "그늘")):
                painter.setPen(QPen(QColor("#a18e68"), 4))
                painter.drawLine(x, y + 20, x, y - 20)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(100, 136, 81, 100))
                painter.drawEllipse(QRectF(x - 30, y - 45, 60, 45))
            elif "밤하늘" in name:
                painter.setPen(QPen(QColor("#e8dfad"), 1))
                painter.drawLine(x - 3, y, x + 3, y)
                painter.drawLine(x, y - 4, x, y + 4)
            elif any(s in name for s in ("눈", "서리")):
                painter.setPen(QPen(QColor("#f6f5e9"), 2))
                painter.drawLine(x - 5, y, x + 5, y)
                painter.drawLine(x, y - 5, x, y + 5)
            elif (
                any(s in name for s in ("클로버", "토끼풀", "허브", "잎", "새싹", "풀"))
                and "꽃잎" not in name
            ):
                leaf(painter, x, y, -45, 13, "#82a16b")
                leaf(painter, x, y, 40, 14, "#90ac75")
            else:
                color = (
                    QColor("#df9da9")
                    if any(s in name for s in ("핑크", "벚꽃", "장미", "코스모스"))
                    else (
                        QColor("#b5a2cb")
                        if any(s in name for s in ("보라", "라벤더", "수국"))
                        else (
                            QColor("#f3cf75")
                            if any(s in name for s in ("노란", "민들레", "가을"))
                            else QColor("#f3f0d5")
                        )
                    )
                )
                flower(painter, x, y, 4 + index % 3, color)
    painter.restore()
