"""Seed packets shared by the planting screen and the gold shop."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QPushButton

from .flower_art import paint_collection_flower
from .icon_picker import IconPicker
from .navigation import chevron_icon
from .plant_catalog import HOUR, PLANTS, REGULAR_PLANTS, RANDOM_SEED_PRICE, VACATION_PLANTS


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
        self.page = 0
        self.page_size = 3
        self.previous = QPushButton(self)
        self.next = QPushButton(self)
        for button, direction, label in ((self.previous, -1, '이전 씨앗'), (self.next, 1, '다음 씨앗')):
            button.setFixedWidth(24)
            button.setIcon(chevron_icon(direction))
            button.setStyleSheet('padding:0;')
            button.setAccessibleName(label)
            button.clicked.connect(lambda checked=False, step=direction: self.change_page(step))
        self.layout().insertWidget(0, self.previous)
        self.layout().addWidget(self.next)
        self.selectionChanged.connect(self.reveal_selected)
        self.show_page()
        self.update_counts({})

    def show_page(self):
        for index, button in enumerate(self.buttons.values()):
            button.setVisible(index // self.page_size == self.page)
        pages = (len(self.buttons) + self.page_size - 1) // self.page_size
        self.previous.setEnabled(self.page > 0)
        self.next.setEnabled(self.page < pages - 1)
        for button in (self.previous, self.next):
            button.setToolTip(f'씨앗 {self.page + 1} / {pages}쪽')

    def change_page(self, direction):
        page = self.page + direction
        if not 0 <= page <= (len(self.buttons) - 1) // self.page_size:
            return
        self.page = page
        list(self.buttons.values())[page * self.page_size].setChecked(True)
        self.show_page()
        self.selectionChanged.emit()

    def reveal_selected(self):
        self.page = list(self.buttons).index(self.selected) // self.page_size
        self.show_page()

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
                + (f'\n{definition.shop_tag}\n설정의 휴가 모드는 성장을 정지합니다.'
                   if key in VACATION_PLANTS else '')
            )
