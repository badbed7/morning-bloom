"""Hold-and-release dandelion flight. Physics and rewards use active play only."""
import math
import random
import time
from uuid import uuid4

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QStyle, QVBoxLayout, QWidget


class WindState:
    player_x = .28

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.y = .5
        self.velocity = 0.0
        self.wind = 0.0
        self.elapsed = 0.0
        self.score = 0
        self.combo = 0
        self.hits = 0
        self.sparkle = 0.0
        self.ended = False
        self.spawn_wait = 2.5
        self.target_y = .5
        self.gates = [dict(x=.65, y=.5, checked=False)]

    @property
    def reward(self):
        return self.score // 5

    @property
    def radius(self):
        return max(.08, .14 - self.elapsed * .0004)

    def step(self, seconds, held):
        if self.ended or not math.isfinite(seconds) or seconds <= 0:
            return
        # A stalled UI never simulates unattended play or skips a collision.
        remaining = min(seconds, .1)
        while remaining > 1e-9 and not self.ended:
            dt = min(remaining, 1 / 120)
            remaining -= dt
            self.elapsed += dt
            self.sparkle = max(0.0, self.sparkle - dt)
            self.wind += (float(held) - self.wind) * (1 - math.exp(-dt / .18))
            gust = math.sin(self.elapsed * 1.7) * min(.14, self.elapsed * .0015)
            self.velocity += (.55 - 1.15 * self.wind + gust) * dt
            self.velocity *= math.exp(-.65 * dt)
            self.y += self.velocity * dt
            if not .055 < self.y < .945:
                self.ended = True
                break
            speed = min(.24, .13 + self.elapsed * .0008)
            for gate in self.gates:
                gate['x'] -= speed * dt
                if not gate['checked'] and gate['x'] <= self.player_x:
                    gate['checked'] = True
                    if abs(self.y - gate['y']) <= self.radius - .02:
                        self.hits += 1
                        self.combo += 1
                        self.score += min(3, 1 + self.combo // 5)
                        self.sparkle = .4
                    else:
                        self.combo = 0
            self.gates = [gate for gate in self.gates if gate['x'] > -.15]
            self.spawn_wait -= dt
            if self.spawn_wait <= 0:
                self.target_y = max(.22, min(.78, self.target_y + self.rng.uniform(-.22, .22)))
                self.gates.append(dict(x=1.1, y=self.target_y, checked=False))
                self.spawn_wait += 2.5


class WindCanvas(QWidget):
    heldChanged = Signal(bool)

    def __init__(self, game):
        super().__init__(game)
        self.game = game
        self.setFixedHeight(240)
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
            color = '#d6cfb8' if gate['checked'] else '#dbb34f'
            painter.setPen(QPen(QColor(color), 3))
            painter.setBrush(Qt.NoBrush)
            x, y = gate['x'] * width, gate['y'] * height
            painter.drawEllipse(QPointF(x, y), 12, state.radius * height)
            if not gate['checked']:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor('#f4d674'))
                painter.drawEllipse(QPointF(x, y), 4, 4)
        x, y = state.player_x * width, state.y * height
        if state.sparkle:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor('#e9bc46'))
            distance = 18 + (1 - state.sparkle / .4) * 24
            for index in range(8):
                angle = index * math.tau / 8
                painter.drawEllipse(QPointF(x + math.cos(angle) * distance, y + math.sin(angle) * distance),
                                    state.sparkle * 6, state.sparkle * 6)
        painter.setPen(QPen(QColor('#abc5bd'), 1.5))
        for index in range(5):
            breeze_y = height - ((state.elapsed * 70 * (.2 + state.wind) + index * 39) % height)
            breeze_x = x + math.sin(index + state.elapsed) * 20
            painter.drawLine(QPointF(breeze_x, breeze_y), QPointF(breeze_x + 2, breeze_y - 7 - state.wind * 14))
        painter.save()
        painter.translate(x, max(12, min(height - 12, y)))
        painter.rotate(state.velocity * 35 + math.sin(state.elapsed * 3) * 5)
        painter.setPen(QPen(QColor('#897254'), 1.4))
        painter.drawLine(QPointF(0, 0), QPointF(1, 14))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#b59567'))
        painter.drawEllipse(QRectF(-1, 11, 4, 7))
        for index in range(13):
            angle = math.pi + index * math.pi / 12
            point = QPointF(math.cos(angle) * 18, math.sin(angle) * 18)
            painter.setPen(QPen(QColor('#9eaa91'), 1))
            painter.drawLine(QPointF(0, 0), point)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor('#fffdf5'))
            painter.drawEllipse(point, 3, 2)
        painter.restore()
        if not self.game.running or self.game.paused:
            painter.setPen(QColor('#596c56'))
            text = '잠시 쉬는 중' if self.game.paused else '한 번 더 날아볼까요?' if state.ended else '누르면 바람이 불어요'
            painter.drawText(QRectF(0, height - 46, width, 30), Qt.AlignCenter, text)
        painter.end()


class WindGame(QDialog):
    completed = Signal(str, int)

    def __init__(self, parent):
        super().__init__(parent)
        self.state = WindState()
        self.game_id = str(uuid4())
        self.running = False
        self.paused = False
        self.finished_game = False
        self.reward_pending = False
        self.held_sources = set()
        self.setWindowTitle('홀씨 바람놀이')
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(parent.windowFlags() & Qt.WindowStaysOnTopHint))
        self.setWindowModality(Qt.WindowModal)
        self.setWindowOpacity(parent.windowOpacity())
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedWidth(max(300, min(384, parent.width())))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
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
        self.close_button.setToolTip('보상 없이 닫기 · Esc\n획득분을 받으려면 그만하고 받기를 누르세요.')
        self.close_button.clicked.connect(self.reject)
        header.addWidget(self.close_button)
        layout.addLayout(header)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.canvas = WindCanvas(self)
        self.canvas.heldChanged.connect(lambda held: self.set_held('canvas', held))
        layout.addWidget(self.canvas)
        self.hint = QLabel('누르면 상승 · 놓으면 하강 · 스페이스도 가능\n금빛 고리 통과! 천장·바닥에 닿으면 마무리해요.')
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet('font-size:11px;color:#778575;')
        layout.addWidget(self.hint)
        self.result = QLabel('꽃가루 5점마다 1G · 비용과 보상 대기 없음')
        self.result.setWordWrap(True)
        layout.addWidget(self.result)
        controls = QHBoxLayout()
        self.hold_button = QPushButton('꾹 눌러 바람 불기')
        self.hold_button.pressed.connect(lambda: self.set_held('button', True))
        self.hold_button.released.connect(lambda: self.set_held('button', False))
        controls.addWidget(self.hold_button)
        self.finish_button = QPushButton('그만하고 받기')
        self.finish_button.clicked.connect(self.finish_play)
        controls.addWidget(self.finish_button)
        layout.addLayout(controls)
        self.start_button = QPushButton('바람놀이 시작')
        self.start_button.clicked.connect(self.start)
        layout.addWidget(self.start_button)
        for button in (self.close_button, self.hold_button, self.finish_button, self.start_button):
            button.setAutoDefault(False)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        QApplication.instance().installEventFilter(self)
        self.finished.connect(self.cleanup)
        self.update_controls()

    def drag(self, event):
        if event.button() == Qt.LeftButton and self.windowHandle():
            self.pause()
            self.windowHandle().startSystemMove()

    def set_held(self, source, held):
        if held and self.running and not self.paused:
            self.held_sources.add(source)
        else:
            self.held_sources.discard(source)

    def start(self):
        if self.reward_pending:
            self.completed.emit(self.game_id, self.state.reward)
            return
        if self.running and not self.paused:
            return
        if not self.paused:
            self.state = WindState()
            self.game_id = str(uuid4())
            self.finished_game = False
            self.result.setText('5회 연속 통과부터 2배 · 10회부터 3배 점수')
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
        self.state.step(now - self.last_tick, bool(self.held_sources))
        self.last_tick = now
        if self.state.ended:
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
        if not self.running or self.finished_game:
            return
        self.running = False
        self.paused = False
        self.finished_game = True
        self.state.ended = True
        self.held_sources.clear()
        self.timer.stop()
        self.reward_pending = True
        self.update_controls()
        self.completed.emit(self.game_id, self.state.reward)

    def reward_result(self, success, text):
        self.reward_pending = not success
        self.result.setText(text)
        self.update_controls()

    def update_controls(self):
        self.status.setText(f'꽃가루 {self.state.score} · 연속 {self.state.combo}회 · 보상 {self.state.reward}G')
        self.hold_button.setEnabled(self.running and not self.paused)
        self.finish_button.setEnabled(self.running)
        self.start_button.setVisible(not self.running or self.paused)
        self.start_button.setText('보상 저장 다시 시도' if self.reward_pending else
                                 '계속 날리기' if self.paused else
                                 '바로 다시 시작' if self.finished_game else '바람놀이 시작')
        self.canvas.update()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.ApplicationDeactivate or (watched is self and event.type() == QEvent.WindowDeactivate):
            self.pause()
        if (event.type() in (QEvent.KeyPress, QEvent.KeyRelease)
                and isinstance(watched, QWidget) and (watched is self or self.isAncestorOf(watched))
                and event.key() == Qt.Key_Space and self.running and not self.paused):
            if not event.isAutoRepeat():
                self.set_held('keyboard', event.type() == QEvent.KeyPress)
            return True
        return super().eventFilter(watched, event)

    def cleanup(self, _result):
        self.running = False
        self.held_sources.clear()
        self.timer.stop()
        QApplication.instance().removeEventFilter(self)
