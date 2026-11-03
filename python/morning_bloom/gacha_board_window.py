"""Main and high-grade side boards with saved, two-dice movement."""

import math

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QListWidget,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from . import gacha_board as board
from .plant_catalog import PLANTS
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


class DiceFace(QWidget):
    """Crisp vector dice; the settled face always comes from the saved draw."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 1
        self.tilt = 0
        self.setFixedSize(64, 64)
        self.set_face(1)

    def set_face(self, value, tilt=0):
        self.value, self.tilt = value, tilt
        self.setAccessibleName(f'주사위 {value}')
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(32, 32)
        painter.rotate(self.tilt)
        painter.setPen(QPen(QColor('#9d977b'), 1.5))
        painter.setBrush(QColor('#fffaf0'))
        painter.drawRoundedRect(QRectF(-24, -24, 48, 48), 9, 9)
        pips = {
            1: ((0, 0),),
            2: ((-13, -13), (13, 13)),
            3: ((-13, -13), (0, 0), (13, 13)),
            4: ((-13, -13), (13, -13), (-13, 13), (13, 13)),
            5: ((-13, -13), (13, -13), (0, 0), (-13, 13), (13, 13)),
            6: ((-13, -13), (13, -13), (-13, 0), (13, 0), (-13, 13), (13, 13)),
        }
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#4d6445'))
        for x, y in pips[self.value]:
            painter.drawEllipse(QPointF(x, y), 3.6, 3.6)


class DandelionToken(QWidget):
    """A light seed with a white parachute, floating over the board cells."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(40, 42)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAccessibleName('보드 위를 이동하는 민들레 씨')
        self.sway = 0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(20, 20)
        painter.rotate(self.sway)
        painter.setPen(QPen(QColor('#665539'), 1.6))
        painter.drawLine(QPointF(0, -5), QPointF(2, 13))
        for i in range(9):
            angle = math.pi * (1.08 + .84 * i / 8)
            end = QPointF(math.cos(angle) * 17, math.sin(angle) * 17 - 1)
            painter.setPen(QPen(QColor('#71836a'), 2.8))
            painter.drawLine(QPointF(0, -5), end)
            painter.setPen(QPen(QColor('#fffef4'), 1.4))
            painter.drawLine(QPointF(0, -5), end)
            painter.drawEllipse(end, 1.5, 1.5)
        painter.setPen(QPen(QColor('#6b452d'), 1))
        painter.setBrush(QColor('#b18047'))
        painter.drawEllipse(QRectF(-.5, 9, 5, 10))


class GachaBoardWindow(QDialog):
    ROLL_FRAMES = 8
    ROLL_TICK_MS = 55
    SETTLE_MS = 160
    STEP_MS = 105
    PAUSE_MS = 220

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle('꽃길 뽑기')
        self.setWindowModality(Qt.WindowModal)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, owner.garden.settings['topmost'])
        self.setWindowOpacity(owner.windowOpacity())
        self.resize(930, 690)
        self.animation = []
        self.animating = False
        self.display_position = None
        self.display_side = None
        self.display_gate = None
        self.phase = 'idle'
        self.current_result = None
        self._visible_history = None
        self._roll_frame = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.movement = QVariantAnimation(self)
        self.movement.valueChanged.connect(self._move_seed)
        self.movement.finished.connect(self._reveal_reward)

        outer = QVBoxLayout(self)
        title = QLabel('꽃길 뽑기')
        title.setStyleSheet('font-size:20px;font-weight:700;color:#466347')
        outer.addWidget(title)
        explanation = QLabel(f'주사위 2개로 이동 · 특수 칸 도착 시 전용 곁길 진입 · 곁길 {board.SIDE_DRAWS}회 후 복귀 · 매회 햇빛 10 · 곁길은 SR 이상, 황금 곁길은 SSR 전용')
        explanation.setWordWrap(True)
        outer.addWidget(explanation)
        self.balance = QLabel()
        outer.addWidget(self.balance)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(465)
        board_widget = self.board_widget = QWidget()
        board_widget.installEventFilter(self)
        grid = self.board_grid = QGridLayout(board_widget)
        self._layout_gate = False
        grid.setSpacing(3)
        grid.setContentsMargins(24, 24, 24, 24)
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
        dice_row = QHBoxLayout()
        dice_row.setAlignment(Qt.AlignCenter)
        self.dice = [DiceFace(center), DiceFace(center)]
        dice_row.addWidget(self.dice[0])
        dice_row.addWidget(QLabel('+'))
        dice_row.addWidget(self.dice[1])
        center_layout.addLayout(dice_row)
        self.dice_total = QLabel('주사위 2개 · 2~12칸 이동')
        self.dice_total.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.dice_total)
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
        self.seed = DandelionToken(board_widget)
        self.seed.raise_()
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
        for step in range(1, board.SIDE_DRAWS + 1):
            waypoint = QLabel()
            waypoint.setAlignment(Qt.AlignCenter)
            side.addWidget(waypoint)
            self.side_cells[step] = waypoint
        outer.addLayout(side)

        controls = QHBoxLayout()
        self.category = QComboBox()
        self.category.addItem('화분', 'pot')
        self.category.addItem('정원', 'garden')
        self.category.addItem('식물', 'plant')
        self.one = QPushButton('주사위 굴리기 · 햇빛 10')
        self.ten = QPushButton('10회 굴리기 · 햇빛 100')
        controls.addWidget(self.category)
        controls.addWidget(self.one)
        controls.addWidget(self.ten)
        self.skip = QPushButton('연출 건너뛰기')
        self.skip.clicked.connect(self.finish_animation)
        self.skip.setVisible(False)
        controls.addWidget(self.skip)
        outer.addLayout(controls)
        self.result = QLabel('식물 재배 해금·정원·화분을 획득합니다. 중복은 교환잎으로 바뀝니다.')
        self.result.setWordWrap(True)
        outer.addWidget(self.result)
        self.history = QListWidget()
        self.history.setMaximumHeight(90)
        outer.addWidget(self.history)
        self.probability = QLabel()
        self.probability.setWordWrap(True)
        self.probability.setStyleSheet('font-size:11px;')
        outer.addWidget(self.probability)
        self.category.currentIndexChanged.connect(self.sync)
        self.one.clicked.connect(lambda: self.draw(1))
        self.ten.clicked.connect(lambda: self.draw(10))
        self.sync()

    def sync(self):
        garden = self.owner.garden
        account = garden.gacha
        state = account['board']
        gate = self.display_gate if self.animating else state['side_gate']
        self._layout_board(gate)
        pool = board.REWARDS[self.category.currentData()]
        tiers = ('SSR',) if gate == board.GOLD else ('SR', 'SSR') if gate is not None else ('R', 'SR', 'SSR')
        rates = ' / '.join(f'{tier}: {len(pool[tier])}종 · 등급 내 개별 {100 / len(pool[tier]):.2f}%' for tier in tiers)
        self.probability.setText('일반 R 70% / SR 25% / SSR 5% · 은색 칸·10회 보장 SR 95%/SSR 5%\n'
            + '곁길 일반 칸 SR 95%/SSR 5% · 금색 칸·60회 보장 SSR 100%\n' + rates)
        position = (state['side_position'] if gate is not None else state['position']) if self.display_position is None else self.display_position
        length = board.SIDE_LENGTH if gate is not None else board.LENGTH
        self.balance.setText(f"햇빛 {garden.sunlight} · 무료권 {account['tickets']} · 교환잎 {account['leaves']}")
        self.position_label.setText(f'{board.board_name(gate)} · 현재 {position or length}번')
        side_gate, side_step = self.display_side if self.display_side is not None else (state['side_gate'], state['side_step'])
        if gate is None:
            upcoming = next((number for number in sorted(board.SPECIALS) if number > position), 71)
            self.next_label.setText(f'다음 특수 칸까지 {upcoming - position}칸 · 통과 보상 없음')
        else:
            ssr = ', '.join(map(str, sorted(board.SIDE_BOARDS[gate]['ssr_cells'])))
            self.next_label.setText(f'SR 이상 전용 · SSR 확정 칸: {ssr}')
        if side_gate is None:
            message = '곁길 종료 · 다음 회차 일반 꽃길 복귀' if gate is not None else '특수 칸 도착 시 곁길 진입'
        else:
            message = f'{board.board_name(side_gate)} · {side_step}/{board.SIDE_DRAWS}회 · 일반 {side_gate}번으로 복귀'
        self.gate_label.setText(message)
        for number in sorted(board.SPECIALS):
            cell = self.side_cells[number]
            cell.setText(f'{number}번 · {board.board_name(number)}')
            cell.setStyleSheet('background:#f1d98d;border:2px solid #467955;border-radius:5px;' if number == side_gate else 'background:#eee;border:1px solid #ccc;border-radius:5px;')
        for step in range(1, board.SIDE_DRAWS + 1):
            cell = self.side_cells[step]
            cell.setText(f'{step}회')
            cell.setStyleSheet('background:#cde5cc;border:2px solid #467955;border-radius:5px;' if side_gate is not None and step == side_step else 'background:#f6faef;border:1px solid #c5d2bb;border-radius:5px;')
        for number, cell in self.cells.items():
            if number > length:
                continue
            tier = ('SSR' if number in board.SIDE_BOARDS[gate]['ssr_cells'] else 'SR+') if gate is not None else ('SSR' if number == board.GOLD else 'SR+' if number in board.SILVER else '')
            cell.setText(f'{number}\n{tier}')
            cell.setAccessibleName(f'{board.board_name(gate)} {number}번 {tier or "일반"} 칸')
            color = '#f1d98d' if tier == 'SSR' else '#e1e4f0' if tier else '#f6faef'
            border = '3px solid #467955' if number == (position or length) else '1px solid #c5d2bb'
            cell.setStyleSheet(f'background:{color};border:{border};border-radius:5px;color:#3d5e44;font-size:10px;font-weight:600;')
        self.one.setText('주사위 굴리기 · 테스트' if self.owner.test_sunlight else '주사위 굴리기 · 햇빛 10')
        self.ten.setText('10회 굴리기 · 테스트' if self.owner.test_sunlight else '10회 굴리기 · 햇빛 100')
        if self.owner.test_sunlight:
            self.balance.setText('햇빛 ∞ · 테스트 · 햇빛/무료권 미차감')
        busy = self.animating
        self.one.setEnabled(not busy and (self.owner.test_sunlight or account['tickets'] >= 1 or garden.sunlight >= 10))
        self.ten.setEnabled(not busy and (self.owner.test_sunlight or account['tickets'] >= 10 or garden.sunlight >= 100))
        self.category.setEnabled(not busy)
        self.skip.setVisible(busy)
        self.history.clear()
        history = self._visible_history if busy and self._visible_history is not None else account['history']
        for item in reversed(history[-10:]):
            catalog = PLANTS if item['category'] == 'plant' else POT_SKINS if item['category'] == 'pot' else THEMES
            self.history.addItem(f"{board.board_name(item.get('board_gate'))} {item['position']}번 · {item['rarity']} {catalog[item['item']].name} · {'중복' if item['duplicate'] else '신규'}")
        if not self.animating or self.phase != 'moving':
            self._align_seed()

    def draw(self, count):
        if self.animating:
            return
        results = []
        category = self.category.currentData()
        state = self.owner.garden.gacha['board']
        start_position = state['side_position'] if state['side_gate'] is not None else state['position']
        start_gate = state['side_gate']
        start_side = (state['side_gate'], state['side_step'])
        history = list(self.owner.garden.gacha['history'])

        def action():
            outcome = self.owner.garden.draw_gacha(category, count, test_free=self.owner.test_sunlight)
            if outcome is False:
                return False
            results.extend(outcome)
            return True

        if not self.owner.act(action):
            self.sync()
            return
        self.animation = results
        self.animating = True
        self.display_gate = start_gate
        self.display_position = start_position
        self.display_side = start_side
        self._visible_history = history
        self.result.setText(f'{count}회 결과를 저장했습니다. 주사위를 굴립니다.')
        self.sync()
        self.animation_step()

    def animation_step(self):
        if not self.animating:
            return
        if not self.animation:
            self.finish_animation()
            return
        self.current_result = self.animation.pop(0)
        self.phase = 'rolling'
        self.display_gate = self.current_result['board_gate']
        self.display_position = self.current_result['start']
        self.sync()
        self._roll_frame = 0
        self.dice_total.setText('주사위를 굴리는 중…')
        self.result.setText('민들레 씨가 바람을 기다리고 있어요.')
        self.timer.setSingleShot(False)
        self.timer.start(self.ROLL_TICK_MS)

    def _tick(self):
        if not self.animating:
            return
        if self.phase == 'settling':
            self._start_movement()
        elif self.phase == 'pause':
            self.animation_step()
        elif self.phase == 'rolling':
            self._roll_frame += 1
            for index, die in enumerate(self.dice):
                die.set_face((self._roll_frame * (index + 2) + index) % 6 + 1,
                             9 if (self._roll_frame + index) % 2 else -9)
            if self._roll_frame >= self.ROLL_FRAMES:
                self.timer.stop()
                item = self.current_result
                for die, face in zip(self.dice, item['dice']):
                    die.set_face(face)
                a, b = item['dice']
                self.dice_total.setText(f'{a} + {b} = {item["distance"]}칸')
                self.phase = 'settling'
                self.timer.setSingleShot(True)
                self.timer.start(self.SETTLE_MS)

    def _start_movement(self):
        self.timer.stop()
        self.phase = 'moving'
        item = self.current_result
        self.result.setText(f'민들레 씨 이동 · {item["distance"]}칸')
        self.movement.setStartValue(0.0)
        self.movement.setEndValue(float(item['distance']))
        self.movement.setDuration(item['distance'] * self.STEP_MS)
        self.movement.start()

    def _layout_board(self, gate):
        if self._layout_gate == gate:
            return
        self._layout_gate = gate
        side_coordinates = ((11, 0), (11, 6), (11, 12), (11, 19), (7, 19), (3, 19),
                            (0, 19), (0, 12), (0, 6), (0, 0), (3, 0), (7, 0))
        for cell in self.cells.values():
            self.board_grid.removeWidget(cell)
            cell.hide()
        length = board.SIDE_LENGTH if gate is not None else board.LENGTH
        for number in range(1, length + 1):
            row, column = side_coordinates[number - 1] if gate is not None else coordinates(number)
            self.board_grid.addWidget(self.cells[number], row, column)
            self.cells[number].show()
        self.board_grid.activate()

    def _cell_center(self, number):
        gate = self.display_gate if self.animating else self.owner.garden.gacha['board']['side_gate']
        length = board.SIDE_LENGTH if gate is not None else board.LENGTH
        cell = self.cells[number or length]
        return QPointF(cell.mapTo(self.board_widget, cell.rect().center()))

    def _align_seed(self):
        if not hasattr(self, 'seed'):
            return
        state = self.owner.garden.gacha['board']
        position = (state['side_position'] if state['side_gate'] is not None else state['position']) if self.display_position is None else self.display_position
        center = self._cell_center(position)
        self.seed.move(round(center.x() - self.seed.width() / 2),
                       round(center.y() - self.seed.height() / 2))
        self.seed.raise_()

    def _move_seed(self, value):
        if not self.animating or not self.current_result:
            return
        item = self.current_result
        route = [item['start']] + item['path']
        progress = max(0.0, min(float(value), item['distance']))
        step = min(int(progress), item['distance'] - 1)
        fraction = progress - step
        start, end = self._cell_center(route[step]), self._cell_center(route[step + 1])
        center = start + (end - start) * fraction
        center.setY(center.y() - math.sin(fraction * math.pi) * 5)
        self.seed.move(round(center.x() - self.seed.width() / 2),
                       round(center.y() - self.seed.height() / 2))
        self.seed.sway = math.sin(progress * math.pi) * 13
        self.seed.update()
        self.seed.raise_()
        reached = route[min(int(progress), item['distance'])]
        if self.display_position != reached:
            self.display_position = reached
            self.sync()

    def _reveal_reward(self):
        if not self.animating or self.phase != 'moving':
            return
        item = self.current_result
        self.display_position = item['position']
        self.display_side = (item['side_gate'], item['side_step'])
        self._visible_history.append(item)
        catalog = PLANTS if item['category'] == 'plant' else POT_SKINS if item['category'] == 'pot' else THEMES
        self.result.setText(f"{board.board_name(item['board_gate'])} {item['position']}번 도착 · {item['rarity']} {catalog[item['item']].name} · {'중복' if item['duplicate'] else '신규'}")
        self.seed.sway = 0
        self.seed.update()
        self.sync()
        self.phase = 'pause'
        self.timer.setSingleShot(True)
        self.timer.start(self.PAUSE_MS)

    def finish_animation(self):
        self.timer.stop()
        self.movement.stop()
        last = self.animation[-1] if self.animation else self.current_result
        if last:
            for die, face in zip(self.dice, last['dice']):
                die.set_face(face)
            self.dice_total.setText(f'{last["dice"][0]} + {last["dice"][1]} = {last["distance"]}칸')
            catalog = PLANTS if last['category'] == 'plant' else POT_SKINS if last['category'] == 'pot' else THEMES
            self.result.setText(f"{board.board_name(last['board_gate'])} {last['position']}번 도착 · {last['rarity']} {catalog[last['item']].name} · 결과 저장 완료")
        self.animation.clear()
        self.current_result = None
        self.animating = False
        self.phase = 'idle'
        self._visible_history = None
        self.display_position = None
        self.display_side = None
        self.display_gate = None
        self.seed.sway = 0
        self.seed.update()
        self.sync()

    def eventFilter(self, watched, event):
        if watched is getattr(self, 'board_widget', None) and event.type() in (QEvent.Resize, QEvent.LayoutRequest):
            if self.animating and self.phase == 'moving' and self.current_result:
                self._move_seed(self.movement.currentValue())
            else:
                self._align_seed()
        return super().eventFilter(watched, event)

    def showEvent(self, event):
        super().showEvent(event)
        self.board_widget.layout().activate()
        self._align_seed()

    def done(self, result):
        self.finish_animation()
        super().done(result)

    def closeEvent(self, event):
        self.finish_animation()
        super().closeEvent(event)
