"""Three short timing rounds. Only a completed round set can emit a reward."""
import random
import time
from uuid import uuid4

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QShortcut
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QStyle, QVBoxLayout, QWidget


class TimingBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.position = 0.0
        self.target = .35
        self.setFixedHeight(68)
        self.setAccessibleName('초록색 목표 구간 안에서 표시를 멈추세요')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width = self.width() - 12
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#e5e9df'))
        painter.drawRoundedRect(QRectF(6, 20, width, 28), 8, 8)
        painter.setBrush(QColor('#8faa79'))
        painter.setPen(QPen(QColor('#334e41'), 2))
        painter.drawRoundedRect(QRectF(6 + self.target * width, 20, .3 * width, 28), 6, 6)
        x = 6 + self.position * width
        painter.setPen(QPen(QColor('#334e41'), 3))
        painter.drawLine(round(x), 14, round(x), 54)
        painter.setBrush(QColor('#334e41'))
        painter.drawEllipse(QRectF(x - 3, 7, 6, 6))
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
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(parent.windowFlags() & Qt.WindowStaysOnTopHint))
        self.setWindowModality(Qt.WindowModal)
        self.setWindowOpacity(parent.windowOpacity())
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedWidth(max(300, min(384, parent.width())))
        self.setStyleSheet('''
            QLabel {background:transparent;}
            QLabel#gameTitle {font-size:18px;font-weight:600;}
            QLabel#gameMode {background:#e5ecde;border-radius:8px;padding:5px 8px;}
            QLabel#gameHint {color:#778575;font-size:11px;}
            QPushButton#gameAction {background:#496b50;color:#ffffff;font-weight:600;}
            QPushButton#gameAction:hover {background:#3d5d44;}
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        header = QHBoxLayout()
        self.title = QLabel('비료 섞기')
        self.title.setObjectName('gameTitle')
        self.title.mousePressEvent = self.drag
        header.addWidget(self.title, 1)
        self.close_button = QPushButton()
        self.close_button.setIcon(self.style().standardIcon(QStyle.SP_DialogCloseButton))
        self.close_button.setFixedSize(28, 28)
        self.close_button.setStyleSheet('padding:0;')
        self.close_button.setAccessibleName('미니게임 닫기')
        self.close_button.setToolTip('닫기 · Esc')
        self.close_button.clicked.connect(self.reject)
        header.addWidget(self.close_button)
        layout.addLayout(header)
        self.mode = QLabel('실전 · 성공 보상 비료 1개' if rewarded else '연습 · 보상 없음')
        self.mode.setObjectName('gameMode')
        layout.addWidget(self.mode)
        description = QLabel('초록 구간에서 멈추세요.\n3번 중 2번 성공하면 완성!')
        description.setWordWrap(True)
        layout.addWidget(description)
        rounds = QHBoxLayout()
        self.round_markers = []
        for index in range(3):
            marker = QLabel(f'{index + 1} 대기')
            marker.setAlignment(Qt.AlignCenter)
            marker.setFixedHeight(26)
            rounds.addWidget(marker)
            self.round_markers.append(marker)
        layout.addLayout(rounds)
        self.status = QLabel('준비되면 시작하세요 · 한 라운드 4초')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.bar = TimingBar(self)
        layout.addWidget(self.bar)
        self.result = QLabel('')
        self.result.setWordWrap(True)
        self.result.setVisible(False)
        layout.addWidget(self.result)
        row = QHBoxLayout()
        self.start_button = QPushButton('섞기 시작')
        # Keep one physical button: replacing the focused button during the
        # initiating click can lose the next input on Windows.
        self.stop_button = self.start_button
        self.start_button.clicked.connect(lambda: self.stop_round() if self.running else self.start())
        self.return_button = QPushButton('정원으로 돌아가기')
        self.return_button.clicked.connect(self.accept)
        self.return_button.setVisible(False)
        for button in (self.start_button, self.return_button):
            button.setObjectName('gameAction')
            button.setFixedHeight(36)
            button.setAutoDefault(False)
            row.addWidget(button)
        self.close_button.setAutoDefault(False)
        layout.addLayout(row)
        self.hint = QLabel(hint)
        self.hint.setObjectName('gameHint')
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.space = QShortcut(Qt.Key_Space, self)
        self.space.setAutoRepeat(False)
        self.space.setEnabled(False)
        self.space.activated.connect(self.stop_round)
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.tick)
        QApplication.instance().installEventFilter(self)
        self.finished.connect(self.cleanup)

    def drag(self, event):
        if event.button() == Qt.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()

    def start(self):
        if self.running or self.finished_game:
            return
        self.running = True
        self.stop_button.setText('멈추기 · 스페이스')
        self.stop_button.setFocus()
        self.space.setEnabled(True)
        self.next_round()
        self.timer.start()

    def next_round(self, started_at=None):
        self.round += 1
        self.round_start = time.monotonic() if started_at is None else started_at
        self.bar.target = random.uniform(.2, .5)
        self.bar.position = 0.0
        self.round_markers[self.round - 1].setText(f'{self.round} 진행')
        self.status.setText(f'{self.round}/3 라운드 · 초록 구간에서 멈추기')
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
        marker = self.round_markers[self.round - 1]
        marker.setText(f'{self.round} ' + ('성공' if hit else '놓침'))
        marker.setStyleSheet('background:#e5ecde;border-radius:8px;' if hit else
                            'background:#eee4dc;border-radius:8px;')
        if self.round < 3:
            self.next_round(next_start)
            return
        self.running = False
        self.finished_game = True
        self.timer.stop()
        self.space.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.stop_button.hide()
        self.return_button.show()
        self.return_button.setFocus()
        success = self.hits >= 2
        self.result.show()
        self.result.setText('성공!' if success else '다시 도전해 보세요. 비용과 벌점은 없어요.')
        self.status.setText(f'3/3 완료 · 성공 {self.hits}회')
        self.completed.emit(self.game_id, success, self.rewarded)

    def eventFilter(self, watched, event):
        if watched is self.stop_button and event.type() == QEvent.MouseButtonDblClick:
            # Ignore the second press of an OS double-click, not every valid
            # keyboard/mouse input inside a global half-second dead period.
            self.stop_button.setDown(False)
            return True
        if event.type() == QEvent.ApplicationDeactivate and self.running:
            self.reject()
        return super().eventFilter(watched, event)

    def cleanup(self, result):
        self.running = False
        self.timer.stop()
        QApplication.instance().removeEventFilter(self)
