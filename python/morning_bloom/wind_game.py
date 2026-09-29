"""Persistent dandelion flight with held-input progress and ring rewards."""
import math
import random
import time
from uuid import uuid4

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from .model import WIND_BASE_SECONDS, WIND_RINGS_PER_GOLD
from .plant_catalog import PLANTS
from .flower_art import paint_collection_flower


def duration_text(seconds):
    seconds = max(0, math.ceil(seconds))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if hours:
        return f'{hours}시간 {minutes:02}분 {seconds:02}초'
    return f'{minutes}분 {seconds:02}초'


class WindState:
    """UI-independent flight. Only held input advances reward progress."""

    player_x = .28

    def __init__(self, progress=0.0, upgrade=0, hits=0, rng=None):
        self.progress = max(0.0, min(float(progress), float(WIND_BASE_SECONDS)))
        self.upgrade = max(0, int(upgrade))
        self.hits = max(0, int(hits))
        self.rng = rng or random.Random()
        self.y = .5
        self.velocity = 0.0
        self.grounded = False
        self.wind = 0.0
        self.elapsed = 0.0
        self.sparkle = 0.0
        self.spawn_wait = 4.0
        self.target_y = .5
        self.gates = []
        self.ended = self.progress >= WIND_BASE_SECONDS

    @property
    def ratio(self):
        return min(1.0, self.progress / WIND_BASE_SECONDS)

    @property
    def remaining_seconds(self):
        return max(0.0, WIND_BASE_SECONDS - self.progress)

    def press(self):
        self.velocity = max(-.7, min(self.velocity, -.18))

    def step(self, seconds, held):
        if self.ended or not math.isfinite(seconds) or seconds <= 0:
            return 0
        remaining = min(seconds, .1)
        new_hits = 0
        while remaining > 1e-9:
            dt = min(remaining, 1 / 120)
            remaining -= dt
            if held:
                self.progress = min(float(WIND_BASE_SECONDS), self.progress + dt)
            self.elapsed += dt
            self.sparkle = max(0.0, self.sparkle - dt)
            self.wind += (float(held) - self.wind) * (1 - math.exp(-dt / .18))
            gust = math.sin(self.elapsed * 1.7) * min(.14, self.elapsed * .0015)
            if not self.grounded or held or self.velocity < 0:
                self.velocity += (.55 - 1.15 * self.wind + gust) * dt
                self.velocity *= math.exp(-.65 * dt)
                self.y += self.velocity * dt
            if self.y <= .055:
                self.y = .055
                self.velocity = max(.06, abs(self.velocity) * .25)
                self.grounded = False
            elif self.y >= .945:
                self.y = .945
                self.velocity = 0.0
                self.grounded = True
            else:
                self.grounded = False
            for gate in self.gates:
                if not self.grounded:
                    gate['x'] -= .13 * dt
                if not gate['collected'] and abs(gate['x'] - self.player_x) <= .052 and abs(gate['y'] - self.y) <= .105:
                    gate['collected'] = True
                    self.hits += 1
                    new_hits += 1
                    self.sparkle = .4
            self.gates = [gate for gate in self.gates if gate['x'] > -.15]
            if not self.grounded:
                self.spawn_wait -= dt
            if self.spawn_wait <= 0 and not self.grounded:
                self.target_y = max(.22, min(.78, self.target_y + self.rng.uniform(-.22, .22)))
                self.gates.append(dict(x=1.05, y=self.target_y, collected=False))
                self.spawn_wait += 10.0
        if held and WIND_BASE_SECONDS - self.progress < 1e-7:
            self.progress = float(WIND_BASE_SECONDS)
        self.ended = self.progress >= WIND_BASE_SECONDS
        return new_hits


class WindCanvas(QWidget):
    heldChanged = Signal(bool)

    def __init__(self, game):
        super().__init__(game)
        self.game = game
        self.setFixedHeight(200)
        self.setMinimumWidth(0)
        self.setAccessibleName('홀씨 비행장 · 누르면 상승, 놓으면 하강')

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.heldChanged.emit(True)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.heldChanged.emit(False)
            event.accept()

    def paintEvent(self, event):
        state = self.game.state
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width, height = self.width(), self.height()
        sky = QLinearGradient(0, 0, 0, height)
        sky.setColorAt(0, QColor('#eaf2ed'))
        sky.setColorAt(1, QColor('#fbf3df'))
        painter.setPen(Qt.NoPen)
        painter.setBrush(sky)
        painter.drawRoundedRect(QRectF(0, 0, width, height), 12, 12)

        painter.setBrush(QColor('#d6dfc8'))
        painter.drawRoundedRect(QRectF(0, height - 10, width, 22), 8, 8)
        painter.setPen(QPen(QColor('#d9bba2'), 1, Qt.DashLine))
        painter.drawLine(8, 10, width - 8, 10)
        for gate in state.gates:
            x, y = gate['x'] * width, gate['y'] * height
            painter.setPen(QPen(QColor('#d6cfb8' if gate['collected'] else '#dbb34f'), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(x, y), 12, 17)
        seed_x, seed_y = state.player_x * width, state.y * height
        if state.sparkle:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor('#e9bc46'))
            for index in range(8):
                angle = index * math.tau / 8
                radius = 18 + (1 - state.sparkle / .4) * 24
                painter.drawEllipse(QPointF(seed_x + math.cos(angle) * radius, seed_y + math.sin(angle) * radius),
                                    state.sparkle * 6, state.sparkle * 6)
        painter.setPen(QPen(QColor('#abc5bd'), 1.5))
        for index in range(5):
            breeze_y = height - ((state.elapsed * 70 * (.2 + state.wind) + index * 39) % height)
            breeze_x = seed_x + math.sin(index + state.elapsed) * 20
            painter.drawLine(QPointF(breeze_x, breeze_y), QPointF(breeze_x + 2, breeze_y - 7 - state.wind * 14))
        painter.save()
        painter.translate(QPointF(seed_x, seed_y))
        painter.rotate(state.velocity * 35 + math.sin(state.elapsed * 3) * 5)
        painter.setPen(QPen(QColor('#897254'), 1.5))
        painter.drawLine(QPointF(0, 0), QPointF(2, 17))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#b59567'))
        painter.drawEllipse(QRectF(0, 14, 5, 8))
        for index in range(13):
            angle = math.pi + index * math.pi / 12
            point = QPointF(math.cos(angle) * 19, math.sin(angle) * 19)
            painter.setPen(QPen(QColor('#9eaa91'), 1))
            painter.drawLine(QPointF(0, 0), point)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor('#fffdf5'))
            painter.drawEllipse(point, 3, 2)
        painter.restore()

        if self.game.finished_game:
            paint_collection_flower(painter, QRectF(width - 104, height - 145, 100, 138), PLANTS['dandelion'])

        if not self.game.running or self.game.paused:
            painter.setPen(QColor('#596c56'))
            text = '잠시 쉬는 중' if self.game.paused else '누르면 바람이 불어요'
            painter.drawText(QRectF(0, height - 34, width, 24), Qt.AlignCenter, text)
        painter.end()


class GoalPot(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(24, 28)
        self.setAccessibleName('민들레 꽃 목표')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#e2a17c'))
        painter.drawRoundedRect(QRectF(2, 18, 20, 8), 3, 3)
        painter.setBrush(QColor('#b98566'))
        painter.drawRoundedRect(QRectF(4, 22, 16, 5), 2, 2)
        painter.setBrush(QColor('#f5cf4d'))
        for index in range(8):
            angle = index * math.tau / 8
            painter.drawEllipse(QPointF(12 + math.cos(angle) * 6, 10 + math.sin(angle) * 6), 3, 3)
        painter.setBrush(QColor('#dfa943'))
        painter.drawEllipse(QPointF(12, 10), 3, 3)
        painter.end()


class WindGame(QDialog):
    progressed = Signal(float)
    ring_collected = Signal(str, int)
    completed = Signal(str)

    def __init__(self, parent, progress=0.0, upgrade=0, hits=0):
        super().__init__(parent)
        self.state = WindState(progress, upgrade, hits)
        self.game_id = str(uuid4())
        self.running = False
        self.paused = False
        self.finished_game = False
        self.reward_pending = False
        self.ring_pending = False
        self.held_sources = set()
        self.last_tick = None
        self.setWindowTitle('홀씨 바람놀이')
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(parent.windowFlags() & Qt.WindowStaysOnTopHint))
        self.setWindowModality(Qt.WindowModal)
        self.setWindowOpacity(parent.windowOpacity())
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedWidth(max(300, min(384, parent.width())))
        self.setStyleSheet('''
            QProgressBar {height:18px;border:1px solid #b8c5ad;border-radius:8px;background:#e5e9df;text-align:center;}
            QProgressBar::chunk {background:#8faa79;border-radius:7px;}
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        header = QHBoxLayout()
        self.title = QLabel('홀씨 바람놀이')
        self.title.setStyleSheet('font-size:18px;font-weight:600;')
        self.title.mousePressEvent = self.drag
        header.addWidget(self.title, 1)
        self.close_button = QPushButton()
        self.close_button.setIcon(self.style().standardIcon(QStyle.SP_DialogCloseButton))
        self.close_button.setStyleSheet('padding:0;')
        self.close_button.setFixedSize(28, 28)
        self.close_button.setAccessibleName('미니게임 닫기')
        self.close_button.setToolTip('진행도를 저장하고 닫기 · Esc')
        self.close_button.clicked.connect(self.reject)
        header.addWidget(self.close_button)
        layout.addLayout(header)

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        # The progress gauge stays above the flight scene.
        self.bar = QProgressBar()
        self.bar.setRange(0, 10000)
        self.bar.setAccessibleName('민들레까지 누적 플레이 진행도')
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.bar, 1)
        progress_row.addWidget(GoalPot(self))
        layout.addLayout(progress_row)
        self.canvas = WindCanvas(self)
        self.canvas.heldChanged.connect(lambda held: self.set_held('canvas', held))
        layout.addWidget(self.canvas)
        self.hint = QLabel('누를 때만 게이지 증가 · 놓으면 하강\n바닥에서 전진 정지 · 버튼·비행장·스페이스 조작')
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet('font-size:11px;color:#778575;')
        layout.addWidget(self.hint)
        self.result = QLabel('누적 1시간 완료 시 민들레 1송이 · 햇빛 1개')
        self.result.setWordWrap(True)
        layout.addWidget(self.result)

        self.hold_button = QPushButton('꾹 눌러 바람 불기')
        self.hold_button.pressed.connect(lambda: self.set_held('button', True))
        self.hold_button.released.connect(lambda: self.set_held('button', False))
        layout.addWidget(self.hold_button)
        self.start_button = QPushButton('바람놀이 시작')
        self.start_button.clicked.connect(self.start)
        layout.addWidget(self.start_button)
        for button in (self.close_button, self.hold_button, self.start_button):
            button.setAutoDefault(False)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        QApplication.instance().installEventFilter(self)
        self.finished.connect(self.cleanup)
        self.update_controls()
        if self.state.ended:
            QTimer.singleShot(0, self.finish_play)

    def drag(self, event):
        if event.button() == Qt.LeftButton and self.windowHandle():
            self.pause()
            self.windowHandle().startSystemMove()

    def set_held(self, source, held):
        if held and not self.running and not self.paused and not self.finished_game and not self.reward_pending:
            self.start()
        elif self.running and not self.paused and not self.ring_pending:
            # Account for the old input state up to this press/release event.
            self.tick()
        if held and self.running and not self.paused:
            if not self.held_sources:
                self.state.press()
            self.held_sources.add(source)
        else:
            self.held_sources.discard(source)

    def start(self):
        if self.reward_pending:
            self.completed.emit(self.game_id)
            return
        if self.ring_pending:
            self.ring_collected.emit(self.game_id, self.state.hits)
            if not self.ring_pending:
                if self.state.ended:
                    self.finish_play()
                else:
                    self.start()
            return
        if self.running and not self.paused:
            return
        if self.finished_game:
            self.state = WindState(0.0, self.state.upgrade, self.state.hits)
            self.game_id = str(uuid4())
            self.finished_game = False
            self.result.setText('누적 1시간 완료 시 민들레 1송이 · 햇빛 1개')
        self.held_sources.clear()
        self.running = True
        self.paused = False
        self.last_tick = time.monotonic()
        self.timer.start()
        self.hold_button.setFocus()
        self.update_controls()

    def tick(self):
        if not self.running or self.paused:
            return
        now = time.monotonic()
        hits = self.state.step(now - self.last_tick, bool(self.held_sources))
        self.last_tick = now
        self.progressed.emit(self.state.progress)
        for total_hits in range(self.state.hits - hits + 1, self.state.hits + 1):
            self.ring_pending = True
            self.ring_collected.emit(self.game_id, total_hits)
            if self.ring_pending:
                self.pause()
                break
        if self.state.ended and not self.ring_pending:
            self.finish_play()
        self.update_controls()

    def pause(self):
        self.held_sources.clear()
        self.hold_button.setDown(False)
        if self.running:
            self.paused = True
            self.timer.stop()
            self.update_controls()

    def finish_play(self):
        if self.finished_game:
            return
        self.running = False
        self.paused = False
        self.finished_game = True
        self.state.ended = True
        self.state.progress = float(WIND_BASE_SECONDS)
        self.held_sources.clear()
        self.timer.stop()
        self.progressed.emit(self.state.progress)
        self.reward_pending = True
        self.update_controls()
        self.completed.emit(self.game_id)

    def ring_result(self, success, text):
        self.ring_pending = not success
        self.result.setText(text)
        self.update_controls()

    def reward_result(self, success, text):
        self.reward_pending = not success
        self.result.setText(text)
        self.update_controls()

    def update_controls(self):
        ratio = self.state.ratio
        self.bar.setValue(round(ratio * self.bar.maximum()))
        self.bar.setFormat(f'{ratio * 100:.2f}%')
        self.status.setText(
            f'민들레까지 {ratio * 100:.2f}% · 남은 누르기 {duration_text(self.state.remaining_seconds)}\n'
            f'고리 {self.state.hits % WIND_RINGS_PER_GOLD}/{WIND_RINGS_PER_GOLD} · 10개마다 1G'
        )
        self.hold_button.setEnabled(not self.paused and not self.finished_game and not self.reward_pending and not self.ring_pending)
        self.start_button.setVisible(not self.running or self.paused)
        self.start_button.setText('저장 다시 시도' if self.reward_pending or self.ring_pending else
                                 '계속 날리기' if self.paused else
                                 '바로 다시 시작' if self.finished_game else '바람놀이 시작')
        self.canvas.update()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.ApplicationDeactivate or (watched is self and event.type() == QEvent.WindowDeactivate):
            self.pause()
        if (event.type() in (QEvent.KeyPress, QEvent.KeyRelease)
                and isinstance(watched, QWidget) and (watched is self or self.isAncestorOf(watched))
                and event.key() == Qt.Key_Space and not self.paused and not self.finished_game
                and not self.reward_pending and not self.ring_pending):
            if not event.isAutoRepeat():
                self.set_held('keyboard', event.type() == QEvent.KeyPress)
            return True
        return super().eventFilter(watched, event)

    def cleanup(self, _result):
        self.pause()
        self.running = False
        self.held_sources.clear()
        self.timer.stop()
        QApplication.instance().removeEventFilter(self)
