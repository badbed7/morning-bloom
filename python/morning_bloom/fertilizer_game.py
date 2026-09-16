"""Three short timing rounds. Only a completed round set can emit a reward."""
import random
import time
from uuid import uuid4

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QShortcut
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class TimingBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.position = 0.0
        self.target = .35
        self.setFixedHeight(52)
        self.setAccessibleName('초록색 목표 구간 안에서 표시를 멈추세요')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width = self.width() - 12
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#e5e9df'))
        painter.drawRoundedRect(QRectF(6, 12, width, 28), 6, 6)
        painter.setBrush(QColor('#8faa79'))
        painter.setPen(QPen(QColor('#334e41'), 2))
        painter.drawRect(QRectF(6 + self.target * width, 12, .3 * width, 28))
        painter.drawLine(round(6 + self.position * width), 6, round(6 + self.position * width), 46)
        painter.end()


class FertilizerGame(QDialog):
    completed = Signal(str, bool, bool)

    def __init__(self, parent, rewarded, hint):
        super().__init__(parent)
        self.game_id = str(uuid4())
        self.rewarded = rewarded
        self.running = False
        self.finished_game = False
        self.round = 0
        self.hits = 0
        self.last_input = float('-inf')
        self.setWindowTitle('비료 섞기')
        self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedWidth(max(300, min(384, parent.width())))
        layout = QVBoxLayout(self)
        self.mode = QLabel('실전 · 성공하면 비료 1개' if rewarded else '연습 · 보상 없음')
        layout.addWidget(self.mode)
        description = QLabel(hint + '\n3번 중 2번 목표 구간에서 멈추세요. 라운드당 최대 4초.')
        description.setWordWrap(True)
        layout.addWidget(description)
        self.status = QLabel('시작을 누른 뒤, 멈추기 버튼 또는 스페이스 키를 사용하세요.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.bar = TimingBar(self)
        layout.addWidget(self.bar)
        self.result = QLabel('')
        self.result.setWordWrap(True)
        layout.addWidget(self.result)
        row = QHBoxLayout()
        self.start_button = QPushButton('시작')
        self.start_button.clicked.connect(self.start)
        self.stop_button = QPushButton('멈추기 · Space')
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_round)
        self.close_button = QPushButton('닫기')
        self.close_button.clicked.connect(self.reject)
        for button in (self.start_button, self.stop_button, self.close_button):
            button.setAutoDefault(False)
            row.addWidget(button)
        layout.addLayout(row)
        self.space = QShortcut(Qt.Key_Space, self)
        self.space.setAutoRepeat(False)
        self.space.activated.connect(self.stop_round)
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.tick)
        QApplication.instance().installEventFilter(self)
        self.finished.connect(self.cleanup)

    def start(self):
        if self.running or self.finished_game:
            return
        self.running = True
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.next_round()
        self.timer.start()

    def next_round(self, started_at=None):
        self.round += 1
        self.round_start = time.monotonic() if started_at is None else started_at
        self.bar.target = random.uniform(.2, .5)
        self.bar.position = 0.0
        self.status.setText(f'{self.round}/3 라운드 · 성공 {self.hits}회 · 목표 구간에서 멈추기')
        self.bar.update()

    def tick(self):
        if not self.running:
            return
        now = time.monotonic()
        while self.running and now - self.round_start >= 4:
            self.end_round(False, self.round_start + 4)
        if not self.running:
            return
        elapsed = max(0.0, now - self.round_start)
        cycle = elapsed % 2
        self.bar.position = cycle if cycle <= 1 else 2 - cycle
        self.bar.update()

    def stop_round(self):
        if not self.running:
            return
        now = time.monotonic()
        # ponytail: inputs within the OS double-click interval are ignored; use release tracking for faster rounds.
        if now - self.last_input <= QApplication.doubleClickInterval() / 1000:
            return
        self.last_input = now
        elapsed = max(0.0, now - self.round_start)
        if elapsed >= 4:
            self.tick()
            return
        cycle = elapsed % 2
        position = cycle if cycle <= 1 else 2 - cycle
        self.end_round(elapsed < 4 and self.bar.target <= position <= self.bar.target + .3)

    def end_round(self, hit, next_start=None):
        if not self.running:
            return
        self.hits += int(hit)
        if self.round < 3:
            self.next_round(next_start)
            return
        self.running = False
        self.finished_game = True
        self.timer.stop()
        self.stop_button.setEnabled(False)
        success = self.hits >= 2
        self.result.setText('성공!' if success else '다시 도전해 보세요. 비용과 벌점은 없어요.')
        self.status.setText(f'3/3 완료 · 성공 {self.hits}회')
        self.completed.emit(self.game_id, success, self.rewarded)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.ApplicationDeactivate and self.running:
            self.reject()
        return super().eventFilter(watched, event)

    def cleanup(self, result):
        self.running = False
        self.timer.stop()
        QApplication.instance().removeEventFilter(self)
