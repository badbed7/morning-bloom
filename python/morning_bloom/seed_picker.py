"""Seed packets shared by the planting screen and the gold shop."""
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QSizePolicy, QToolButton, QWidget

from .flower_art import paint_collection_flower
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


class SeedPicker(QWidget):
    selectionChanged = Signal()

    def __init__(self, shop=False):
        super().__init__()
        self.shop = shop
        self.buttons = {}
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.setFixedHeight(76)
        self.setMinimumWidth(0)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for definition in PLANTS.values():
            button = QToolButton()
            button.setObjectName('seedPacket')
            button.setProperty('species', definition.key)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setIcon(seed_packet_icon(definition))
            button.setIconSize(QSize(36, 40))
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            button.setMinimumWidth(0)
            self.group.addButton(button)
            self.buttons[definition.key] = button
            layout.addWidget(button, 1)
        next(iter(self.buttons.values())).setChecked(True)
        self.group.buttonClicked.connect(lambda _: self.selectionChanged.emit())
        self.update_counts({})

    @property
    def selected(self):
        return self.group.checkedButton().property('species')

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
