"""Persistent press-and-hold journey from a dandelion seed to an empty pot."""
import math
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

from .model import WIND_BASE_SECONDS, WIND_REWARD_GOLD


def duration_text(seconds):
    seconds = max(0, math.ceil(seconds))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if hours:
        return f'{hours}시간 {minutes:02}분 {seconds:02}초'
    return f'{minutes}분 {seconds:02}초'


class WindState:
    """UI-independent journey progress measured in base-speed work seconds."""

    def __init__(self, progress=0.0, upgrade=0):
        self.progress = max(0.0, min(float(progress), float(WIND_BASE_SECONDS)))
        self.upgrade = max(0, int(upgrade))
        self.ended = self.progress >= WIND_BASE_SECONDS

    @property
    def speed(self):
        return 2 ** self.upgrade

    @property
    def ratio(self):
        return min(1.0, self.progress / WIND_BASE_SECONDS)

    @property
    def remaining_seconds(self):
        return max(0.0, WIND_BASE_SECONDS - self.progress) / self.speed

    @property
    def reward(self):
        return WIND_REWARD_GOLD if self.ended else 0

    def step(self, seconds, held):
        if self.ended or not held or not math.isfinite(seconds) or seconds <= 0:
            return False
        self.progress = min(float(WIND_BASE_SECONDS), self.progress + seconds * self.speed)
        self.ended = self.progress >= WIND_BASE_SECONDS
        return True


class WindCanvas(QWidget):
    heldChanged = Signal(bool)

    def __init__(self, game):
        super().__init__(game)
        self.game = game
        self.setFixedHeight(170)
        self.setMinimumWidth(0)
        self.setAccessibleName('민들레 씨앗이 오른쪽 빈 화분으로 이동하는 장면')

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

        start_x = 28.0
        pot_x = max(start_x + 100.0, width - 52.0)
        seed_x = start_x + (pot_x - start_x) * state.ratio
        seed_y = height * .48 + math.sin(state.ratio * math.tau * 3) * 7

        painter.setPen(QPen(QColor('#c9d7c1'), 2, Qt.DashLine))
        painter.drawLine(round(start_x), round(height * .62), round(pot_x), round(height * .62))

        # The requested empty flowerpot is fixed at the far right.
        pot_top = height * .55
        painter.setPen(QPen(QColor('#83593f'), 2))
        painter.setBrush(QColor('#c48763'))
        painter.drawRoundedRect(QRectF(pot_x - 27, pot_top + 9, 54, 39), 9, 9)
        painter.setBrush(QColor('#e2a17c'))
        painter.drawRoundedRect(QRectF(pot_x - 32, pot_top, 64, 15), 8, 8)
        painter.setBrush(QColor('#76503b'))
        painter.drawEllipse(QRectF(pot_x - 24, pot_top + 3, 48, 7))

        # Dandelion seed.
        painter.save()
        painter.translate(QPointF(seed_x, seed_y))
        painter.rotate(10 + math.sin(state.ratio * math.tau * 2) * 12)
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

        if not self.game.running or self.game.paused:
            painter.setPen(QColor('#596c56'))
            text = '잠시 쉬는 중' if self.game.paused else '버튼을 누르면 씨앗이 날아가요'
            painter.drawText(QRectF(0, height - 34, width, 24), Qt.AlignCenter, text)
        painter.end()


class WindGame(QDialog):
    progressed = Signal(float)
    completed = Signal(str, int)

    def __init__(self, parent, progress=0.0, upgrade=0):
        super().__init__(parent)
        self.state = WindState(progress, upgrade)
        self.game_id = str(uuid4())
        self.running = False
        self.paused = False
        self.finished_game = False
        self.reward_pending = False
        self.held_sources = set()
        self.last_tick = None
        self.setWindowTitle('민들레 화분 여행')
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
        self.title = QLabel('민들레 화분 여행')
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
        self.bar.setAccessibleName('민들레 씨앗의 화분 도착 진행도')
        layout.addWidget(self.bar)
        self.canvas = WindCanvas(self)
        self.canvas.heldChanged.connect(lambda held: self.set_held('canvas', held))
        layout.addWidget(self.canvas)
        self.hint = QLabel('버튼·비행장·스페이스를 누르는 동안 오른쪽 화분으로 이동해요.\n강화 0단계 기준 누적 2시간에 도착합니다.')
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet('font-size:11px;color:#778575;')
        layout.addWidget(self.hint)
        self.result = QLabel(f'도착 즉시 2시간 가치의 골드 {WIND_REWARD_GOLD}G · 진행도 자동 저장')
        self.result.setWordWrap(True)
        layout.addWidget(self.result)

        self.hold_button = QPushButton('누르고 씨앗 날리기')
        self.hold_button.pressed.connect(lambda: self.set_held('button', True))
        self.hold_button.released.connect(lambda: self.set_held('button', False))
        layout.addWidget(self.hold_button)
        self.start_button = QPushButton('여행 시작')
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
        if held and self.running and not self.paused:
            self.held_sources.add(source)
        else:
            self.held_sources.discard(source)

    def start(self):
        if self.reward_pending:
            self.completed.emit(self.game_id, WIND_REWARD_GOLD)
            return
        if self.running and not self.paused:
            return
        if self.finished_game:
            self.state = WindState(0.0, self.state.upgrade)
            self.game_id = str(uuid4())
            self.finished_game = False
            self.result.setText(f'도착 즉시 {WIND_REWARD_GOLD}G · 진행도 자동 저장')
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
        changed = self.state.step(now - self.last_tick, bool(self.held_sources))
        self.last_tick = now
        if changed:
            self.progressed.emit(self.state.progress)
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
        self.completed.emit(self.game_id, WIND_REWARD_GOLD)

    def reward_result(self, success, text):
        self.reward_pending = not success
        self.result.setText(text)
        self.update_controls()

    def update_controls(self):
        ratio = self.state.ratio
        self.bar.setValue(round(ratio * self.bar.maximum()))
        self.bar.setFormat(f'{ratio * 100:.2f}%')
        self.status.setText(
            f'강화 {self.state.upgrade}단계 · 진행 {ratio * 100:.2f}% · '
            f'남은 누르기 {duration_text(self.state.remaining_seconds)}'
        )
        self.hold_button.setEnabled(self.running and not self.paused)
        self.start_button.setVisible(not self.running or self.paused)
        self.start_button.setText('보상 저장 다시 시도' if self.reward_pending else
                                 '계속 날리기' if self.paused else
                                 '바로 다시 시작' if self.finished_game else '여행 시작')
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
        self.pause()
        self.running = False
        self.held_sources.clear()
        self.timer.stop()
        QApplication.instance().removeEventFilter(self)
