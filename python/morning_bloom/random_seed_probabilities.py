"""Read-only probability disclosure for the shop's mystery seed."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHeaderView, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from .gacha_probabilities import percent
from .plant_catalog import (PLANTS, MYSTERY_SEED_PROBABILITIES, MYSTERY_SEED_RARITIES,
                            MYSTERY_SEED_SUMMARY, RANDOM_SEED_PRICE)


class RandomSeedProbabilities(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle('랜덤 씨앗 확률')
        self.setWindowModality(Qt.WindowModal)
        self.resize(min(580, max(320, parent.width())), 520)
        self.setMinimumSize(300, 320)
        layout = QVBoxLayout(self)
        note = QLabel(
            f'1개 {RANDOM_SEED_PRICE}G · {MYSTERY_SEED_SUMMARY}\n'
            '구매마다 독립 추첨 · 천장 없음 · 개화 후 정체 공개\n'
            '같은 등급은 균등 확률(고대 꽃 제외)\n'
            '소수 확률은 반올림 표시 · 합계는 정확히 100%'
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        keys = [key for tier in ('R', 'SR', 'SSR')
                for key, rarity in MYSTERY_SEED_RARITIES.items() if rarity == tier]
        self.table = QTableWidget(len(keys), 3)
        self.table.setHorizontalHeaderLabels(['식물', '등급', '구매 1회 확률'])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.ElideNone)
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(35)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.sectionResized.connect(lambda *_: self.table.resizeRowsToContents())
        self.table.setStyleSheet('font-size:11px;')
        for row, key in enumerate(keys):
            chance = MYSTERY_SEED_PROBABILITIES[key]
            for column, value in enumerate((PLANTS[key].name, MYSTERY_SEED_RARITIES[key], percent(chance))):
                cell = QTableWidgetItem(value)
                cell.setToolTip(f'{PLANTS[key].name} · 정확한 비율 {chance.numerator}/{chance.denominator}')
                self.table.setItem(row, column, cell)
        self.table.resizeRowsToContents()
        layout.addWidget(self.table, 1)
        close = QPushButton('확인')
        close.clicked.connect(self.accept)
        layout.addWidget(close)
