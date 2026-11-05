"""Read-only, exact next-roll rates shared with the actual draw rules."""
from fractions import Fraction

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHeaderView, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import gacha_board as board
from .cosmetics import POT_SKINS, THEMES
from .plant_catalog import PLANTS, ROSE_VARIETIES


def percent(value):
    return f'{float(value * 100):.4f}'.rstrip('0').rstrip('.') + '%'


class GachaProbabilities(QDialog):
    def __init__(self, parent, category, state):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle('뽑기 확률 상세')
        self.setWindowModality(Qt.WindowModal)
        self.resize(min(640, max(320, parent.width())), 520)
        self.setMinimumSize(300, 320)
        layout = QVBoxLayout(self)
        note = QLabel('일반 칸: 보장 없는 칸 기준\n'
                      '다음 1회: 주사위·보드·보장 반영\n'
                      '10회 뽑기는 매회 확률이 달라요.')
        note.setWordWrap(True)
        note.setStyleSheet('font-size:11px;')
        layout.addWidget(note)
        if category == 'rose':
            origin = QLabel('자연 발생률 실측값이 아닌 게임 확률\n'
                            '빨강은 상점 · 그 외는 매회 씨앗 1개')
            origin.setStyleSheet('font-size:11px;')
            origin.setToolTip('실제 색상·육종 특성을 참고한 게임 설계값입니다. 색상별 공통 자연 발생률은 확인되지 않았습니다. '
                              '파랑은 특수 육종, 검정은 흑적색 품종을 모티브로 했습니다.')
            origin.setWordWrap(True)
            layout.addWidget(origin)
        self.probabilities = board.item_probabilities(category, state)
        ordinary = board.ordinary_item_probabilities(category)
        keys = list(ROSE_VARIETIES) if category == 'rose' else [key for tier in ('R', 'SR', 'SSR') for key in board.REWARDS[category][tier]]
        catalog = PLANTS if category in ('plant', 'rose') else POT_SKINS if category == 'pot' else THEMES
        self.table = QTableWidget(len(keys), 4)
        self.table.setHorizontalHeaderLabels(['항목', '등급', '일반 칸', '다음 1회'])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setWordWrap(True)
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(35)
        header.setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet('font-size:11px;')
        for row, key in enumerate(keys):
            tier = board.item_rarity(category, key)
            baseline = ordinary.get(key, Fraction(0))
            chance = self.probabilities.get(key, Fraction(0))
            values = [catalog[key].name, tier, '상점' if category == 'rose' and key == 'rose' else percent(baseline), percent(chance)]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(f'{catalog[key].name} · 일반 칸 {percent(baseline)} · 현재 다음 1회 {percent(chance)}\n'
                                f'정확한 다음 1회 비율: {chance.numerator}/{chance.denominator}')
                self.table.setItem(row, column, cell)
        self.table.resizeRowsToContents()
        layout.addWidget(self.table, 1)
        close = QPushButton('확인')
        close.clicked.connect(self.accept)
        layout.addWidget(close)
