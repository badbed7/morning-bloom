"""Visible sixty-space board for the first, existing-cosmetics-only release."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QListWidget,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from . import gacha_board as board
from .cosmetics import POT_SKINS, THEMES


def coordinates(number):
    index = number - 1
    if index < 20:
        return 11, index
    if index < 30:
        return 11 - (index - 19), 19
    if index < 50:
        return 0, 19 - (index - 30)
    return index - 49, 0


class GachaBoardWindow(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle('꽃길 뽑기 · 60칸')
        self.setWindowModality(Qt.WindowModal)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, owner.garden.settings['topmost'])
        self.setWindowOpacity(owner.windowOpacity())
        self.resize(930, 690)
        self.animation = []
        self.animating = False
        self.display_position = None
        self.display_side = None
        self.timer = QTimer(self)
        self.timer.setInterval(230)
        self.timer.timeout.connect(self.animation_step)

        outer = QVBoxLayout(self)
        title = QLabel('직사각형 꽃길 · 60칸')
        title.setStyleSheet('font-size:20px;font-weight:700;color:#466347')
        outer.addWidget(title)
        explanation = QLabel('뽑기마다 한 칸 이동 · 11/26/41번 SR 이상 · 56번 SSR 확정')
        explanation.setWordWrap(True)
        outer.addWidget(explanation)
        self.balance = QLabel()
        outer.addWidget(self.balance)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(465)
        board_widget = QWidget()
        grid = QGridLayout(board_widget)
        grid.setSpacing(3)
        self.cells = {}
        for number in range(1, 61):
            row, column = coordinates(number)
            cell = QLabel()
            cell.setAlignment(Qt.AlignCenter)
            cell.setMinimumSize(35, 34)
            cell.setAccessibleName(f'{number}번 {"SSR" if number == board.GOLD else "SR 이상" if number in board.SILVER else "일반"} 칸')
            grid.addWidget(cell, row, column)
            self.cells[number] = cell
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setAlignment(Qt.AlignCenter)
        self.position_label = QLabel()
        self.position_label.setAlignment(Qt.AlignCenter)
        self.position_label.setStyleSheet('font-size:22px;font-weight:700;color:#426845')
        self.next_label = QLabel()
        self.next_label.setAlignment(Qt.AlignCenter)
        self.gate_label = QLabel()
        self.gate_label.setAlignment(Qt.AlignCenter)
        self.gate_label.setWordWrap(True)
        for label in (self.position_label, self.next_label, self.gate_label):
            center_layout.addWidget(label)
        grid.addWidget(center, 2, 2, 8, 16)
        scroll.setWidget(board_widget)
        outer.addWidget(scroll, 1)

        side = QHBoxLayout()
        self.side_cells = {}
        for number in sorted(board.SPECIALS):
            gate = QLabel()
            gate.setAlignment(Qt.AlignCenter)
            gate.setMinimumWidth(75)
            side.addWidget(gate)
            self.side_cells[number] = gate
        for step in range(1, 5):
            waypoint = QLabel()
            waypoint.setAlignment(Qt.AlignCenter)
            side.addWidget(waypoint)
            self.side_cells[step] = waypoint
        outer.addLayout(side)

        controls = QHBoxLayout()
        self.category = QComboBox()
        self.category.addItem('화분', 'pot')
        self.category.addItem('정원', 'garden')
        self.one = QPushButton('1회 · 햇빛 10')
        self.ten = QPushButton('10회 · 햇빛 100')
        controls.addWidget(self.category)
        controls.addWidget(self.one)
        controls.addWidget(self.ten)
        outer.addLayout(controls)
        self.result = QLabel('기존 정원·화분 꾸미기를 획득합니다. 중복은 교환잎으로 바뀝니다.')
        self.result.setWordWrap(True)
        outer.addWidget(self.result)
        self.history = QListWidget()
        self.history.setMaximumHeight(90)
        outer.addWidget(self.history)
        self.one.clicked.connect(lambda: self.draw(1))
        self.ten.clicked.connect(lambda: self.draw(10))
        self.sync()

    def sync(self):
        garden = self.owner.garden
        account = garden.gacha
        state = account['board']
        position = state['position'] if self.display_position is None else self.display_position
        self.balance.setText(f"햇빛 {garden.sunlight} · 무료권 {account['tickets']} · 교환잎 {account['leaves']}")
        self.position_label.setText(f'현재 {position} / 60')
        upcoming = next((number for number in sorted(board.SPECIALS) if number > position), 71)
        self.next_label.setText(f'다음 특수 칸까지 {upcoming - position}회')
        side_gate, side_step = self.display_side if self.display_side is not None else (state['side_gate'], state['side_step'])
        self.gate_label.setText('곁길 출입구 닫힘' if side_gate is None else f'{side_gate}번 출입구 열림 · 곁길 {side_step}/4')
        for number in sorted(board.SPECIALS):
            cell = self.side_cells[number]
            cell.setText(f'{number}번 입구')
            cell.setStyleSheet('background:#f1d98d;border:2px solid #467955;border-radius:5px;' if number == side_gate else 'background:#eee;border:1px solid #ccc;border-radius:5px;')
        for step in range(1, 5):
            cell = self.side_cells[step]
            cell.setText(f'곁길 {step}')
            cell.setStyleSheet('background:#cde5cc;border:2px solid #467955;border-radius:5px;' if side_gate is not None and step == side_step else 'background:#f6faef;border:1px solid #c5d2bb;border-radius:5px;')
        for number, cell in self.cells.items():
            tier = 'SSR' if number == board.GOLD else 'SR+' if number in board.SILVER else ''
            cell.setText(f'{number}\n{tier}')
            color = '#f1d98d' if number == board.GOLD else '#e1e4f0' if tier else '#f6faef'
            border = '3px solid #467955' if number == position else '1px solid #c5d2bb'
            cell.setStyleSheet(f'background:{color};border:{border};border-radius:5px;color:#3d5e44;font-size:10px;font-weight:600;')
        busy = self.animating
        self.one.setEnabled(not busy and (account['tickets'] >= 1 or garden.sunlight >= 10))
        self.ten.setEnabled(not busy and (account['tickets'] >= 10 or garden.sunlight >= 100))
        self.category.setEnabled(not busy)
        self.history.clear()
        for item in reversed(account['history'][-10:]):
            catalog = POT_SKINS if item['category'] == 'pot' else THEMES
            self.history.addItem(f"{item['position']}번 · {item['rarity']} {catalog[item['item']].name} · {'중복' if item['duplicate'] else '신규'}")

    def draw(self, count):
        if self.animating:
            return
        results = []
        category = self.category.currentData()

        def action():
            outcome = self.owner.garden.draw_gacha(category, count)
            if outcome is False:
                return False
            results.extend(outcome)
            return True

        if not self.owner.act(action):
            self.sync()
            return
        self.animation = results
        self.animating = True
        self.display_position = None
        self.display_side = None
        self.result.setText(f'{count}회 결과를 저장했습니다. 한 칸씩 이동합니다.')
        self.sync()
        self.animation_step()
        if self.animation:
            self.timer.start()

    def animation_step(self):
        if not self.animation:
            self.timer.stop()
            self.animating = False
            self.display_position = None
            self.display_side = None
            self.sync()
            return
        item = self.animation.pop(0)
        self.display_position = item['position']
        self.display_side = (item['side_gate'], item['side_step'])
        catalog = POT_SKINS if item['category'] == 'pot' else THEMES
        self.result.setText(f"{item['position']}번 도착 · {item['rarity']} {catalog[item['item']].name} · {'중복' if item['duplicate'] else '신규'}")
        self.sync()
        if not self.animation:
            self.timer.stop()
            QTimer.singleShot(230, self.finish_animation)

    def finish_animation(self):
        self.animating = False
        self.display_position = None
        self.display_side = None
        self.sync()

    def closeEvent(self, event):
        self.timer.stop()
        self.animating = False
        super().closeEvent(event)
