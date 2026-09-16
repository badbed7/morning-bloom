"""Seed packets shared by the planting screen and the gold shop."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from .flower_art import paint_collection_flower
from .icon_picker import IconPicker
from .plant_catalog import HOUR, PLANTS, REGULAR_PLANTS, RANDOM_SEED_PRICE


def seed_packet_icon(definition=None):
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
    if definition:
        paint_collection_flower(painter, QRectF(10, 12, 20, 25), definition)
    else:
        painter.setPen(QColor('#806498'))
        font = painter.font()
        font.setPixelSize(20)
        painter.setFont(font)
        painter.drawText(QRectF(8, 10, 24, 28), Qt.AlignCenter, '?')
    painter.end()
    return QIcon(pixmap)


class SeedPicker(IconPicker):
    def __init__(self, shop=False):
        super().__init__([(key, PLANTS[key].name, seed_packet_icon(PLANTS[key]))
                          for key in REGULAR_PLANTS] + [('random', '랜덤', seed_packet_icon())])
        self.shop = shop
        self.update_counts({})

    def update_counts(self, seeds):
        for key, button in self.buttons.items():
            if key == 'random':
                count = seeds.get(key, 0)
                detail = f'{RANDOM_SEED_PRICE}G' if self.shop else f'{count}개'
                button.setText(f'랜덤\n{detail}')
                button.setAccessibleName(f'랜덤 씨앗 · {detail} · 보유 {count}개')
                button.setToolTip('개화 전에는 외관으로만 추측해 보세요.\n고대 씨앗 0.1% · 고대 꽃 기본 판매 500G')
                continue
            definition = PLANTS[key]
            count = seeds.get(key, 0)
            detail = f'{definition.seed_price}G' if self.shop else f'{count}개'
            button.setText(f'{definition.name}\n{detail}')
            button.setAccessibleName(f'{definition.name} 씨앗 · {detail} · 보유 {count}개')
            button.setToolTip(
                f'{definition.name} 씨앗 · 보유 {count}개\n'
                f'성장 {definition.growth_seconds // HOUR}시간 · 가격 {definition.seed_price}G'
            )
