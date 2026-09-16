"""Small previews drawn from the same theme and pot skin definitions as the game."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPen, QPixmap

from .flower_art import paint_potted_flower
from .plant_catalog import PLANTS


def theme_icon(theme):
    pixmap = QPixmap(88, 72)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    gradient = QLinearGradient(0, 3, 0, 33)
    gradient.setColorAt(0, QColor(theme.top))
    gradient.setColorAt(1, QColor(theme.bottom))
    painter.setBrush(gradient)
    painter.setPen(QPen(QColor(theme.tuft), 1))
    painter.drawRoundedRect(QRectF(2, 3, 40, 30), 4, 4)
    for x, y in ((10, 15), (22, 24), (34, 15)):
        painter.drawLine(x, y, x - 2, y - 3)
        painter.drawLine(x, y, x + 2, y - 4)
    painter.end()
    return QIcon(pixmap)


def skin_icon(skin):
    pixmap = QPixmap(88, 72)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.translate(22 - 190 * .38, 5 - 100 * .38)
    painter.scale(.38, .38)
    paint_potted_flower(painter, PLANTS['daisy'], planted=False, skin=skin.key)
    painter.end()
    return QIcon(pixmap)
