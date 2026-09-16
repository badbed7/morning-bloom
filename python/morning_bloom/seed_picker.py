"""Seed packets shared by the planting screen and the gold shop."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from .flower_art import paint_collection_flower
from .icon_picker import IconPicker
from .plant_catalog import HOUR, PLANTS


def seed_packet_icon(definition):
    pixmap = QPixmap(80, 88)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor('#ab9270'), 1))
    painter.setBrush(QColor('#ead9b8'))
    painter.drawRoundedRect(QRectF(4, 2, 32, 40), 3, 3)
    painter.drawLine(5, 8, 35, 8)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor('#faf5e9'))
    painter.drawRoundedRect(QRectF(8, 11, 24, 27), 2, 2)
    paint_collection_flower(painter, QRectF(10, 12, 20, 25), definition)
    painter.end()
    return QIcon(pixmap)


class SeedPicker(IconPicker):
    def __init__(self, shop=False):
        super().__init__((definition.key, definition.name, seed_packet_icon(definition))
                         for definition in PLANTS.values())
        self.shop = shop
        self.update_counts({})

    def update_counts(self, seeds):
        for key, button in self.buttons.items():
            definition = PLANTS[key]
            count = seeds.get(key, 0)
            detail = f'{definition.seed_price}G' if self.shop else f'{count}개'
            button.setText(f'{definition.name}\n{detail}')
            button.setAccessibleName(f'{definition.name} 씨앗 · {detail} · 보유 {count}개')
            button.setToolTip(
                f'{definition.name} 씨앗 · 보유 {count}개\n'
                f'성장 {definition.growth_seconds // HOUR}시간 · 가격 {definition.seed_price}G'
            )
