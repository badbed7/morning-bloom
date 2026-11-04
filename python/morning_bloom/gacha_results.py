"""Presentation of an already committed draw batch; never grants rewards."""
from copy import deepcopy
import math

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QFrame, QGridLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from .locked_catalog import COLLECTIONS, CATEGORY_IDS, preview_image

COLORS = {'R': '#658465', 'SR': '#9268ba', 'SSR': '#b88319'}
NAMES = {value: key for key, value in CATEGORY_IDS.items()}


def reward_item(result):
    return next(item for item in COLLECTIONS[NAMES[result['category']]] if item.key == result['item'])


class RewardReveal(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(100)
        self.result = None
        self.progress = 0.0
        self.effect = QVariantAnimation(self)
        self.effect.setEasingCurve(QEasingCurve.OutCubic)
        self.effect.valueChanged.connect(self.animate)
        self.hide()

    def reveal(self, result):
        self.result = result
        self.item = reward_item(result)
        self.image = preview_image(self.item)
        duration = {'R': 220, 'SR': 650, 'SSR': 1000}[result['rarity']]
        self.setAccessibleName(f"{result['rarity']} {self.item.name} 획득")
        self.effect.stop()
        self.effect.setDuration(duration)
        self.effect.setStartValue(0.0)
        self.effect.setEndValue(1.0)
        self.show()
        self.effect.start()
        return duration

    def animate(self, value):
        self.progress = float(value)
        self.update()

    def paintEvent(self, event):
        if self.result is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        tier = self.result['rarity']
        painter.fillRect(self.rect(), QColor('#fff3cf' if tier == 'SSR' else '#f0e8fa' if tier == 'SR' else '#edf3e8'))
        color = QColor(COLORS[tier])
        painter.setPen(QPen(color, 2 if tier == 'SSR' else 1))
        if tier in ('SR', 'SSR'):
            center = self.rect().center()
            for i in range(12 if tier == 'SSR' else 6):
                angle = i * math.pi / (6 if tier == 'SSR' else 3)
                radius = 25 + self.progress * 35
                x, y = center.x() + math.cos(angle)*radius, center.y() + math.sin(angle)*radius
                painter.drawEllipse(QRectF(x-2, y-2, 4, 4))
        size = round(48 + self.progress * (20 if tier == 'SSR' else 8))
        image = self.image.scaled(QSize(size, size), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        painter.drawImage((self.width()-image.width())//2, 2, image)
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(QRectF(0, 74, self.width(), 24), Qt.AlignCenter,
                         f"{tier} · {self.item.name} · {'중복' if self.result['duplicate'] else '신규!'}")


class GachaResults(QDialog):
    def __init__(self, board, results):
        super().__init__(board)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.results = deepcopy(results)
        self.setWindowTitle('꽃길 뽑기 결과')
        self.setWindowModality(Qt.WindowModal)
        self.resize(max(320, min(520, board.owner.width())), max(320, board.owner.height()))
        self.setMinimumSize(300, 300)
        layout = QVBoxLayout(self)
        self.new_count = sum(not item['duplicate'] for item in self.results)
        self.leaves = sum(item['leaves'] for item in self.results)
        self.summary = QLabel(f'{len(self.results)}회 뽑기 결과 · 신규 {self.new_count} · 중복 {len(self.results)-self.new_count}\n교환잎 +{self.leaves}')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.grid = QGridLayout(self.content)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll, 1)
        self.cards = []
        for index, result in enumerate(self.results):
            item = reward_item(result)
            card = QFrame()
            card.setStyleSheet(f"QFrame {{border:1px solid {COLORS[result['rarity']]};border-radius:6px;background:#fffaf1;}} QLabel {{border:0;}}")
            contents = QVBoxLayout(card)
            picture = QLabel()
            picture.setAlignment(Qt.AlignCenter)
            picture.setPixmap(QPixmap.fromImage(preview_image(item).scaled(QSize(80, 60), Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            contents.addWidget(picture)
            text = QLabel(f"{index+1}. {result['rarity']} · {NAMES[result['category']]}\n{item.name}\n" +
                          (f"중복 · 교환잎 +{result['leaves']}" if result['duplicate'] else '신규 획득'))
            text.setAlignment(Qt.AlignCenter)
            text.setWordWrap(True)
            contents.addWidget(text)
            card.setAccessibleName(text.text().replace('\n', ' · '))
            self.cards.append(card)
        close = QPushButton('결과 확인 · 보드로 돌아가기')
        close.clicked.connect(self.accept)
        layout.addWidget(close)
        self.arrange()

    def arrange(self):
        columns = 2 if self.width() < 440 else 3
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // columns, index % columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'cards'):
            self.arrange()
