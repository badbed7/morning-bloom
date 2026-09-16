"""Three deliberate sprays; cancellation never applies partial care."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from .flower_art import paint_potted_flower


def spray_cursor():
    pixmap = QPixmap(40, 40)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor('#365b63'), 2))
    painter.setBrush(QColor('#8ecbd6'))
    painter.drawRoundedRect(QRectF(10, 17, 20, 20), 5, 5)
    painter.setBrush(QColor('#536e69'))
    painter.drawRoundedRect(QRectF(11, 8, 20, 8), 2, 2)
    painter.drawLine(15, 16, 12, 23)
    painter.setPen(QPen(QColor('#86cce7'), 2))
    for y in (5, 10, 15):
        painter.drawLine(2, y, 7, 10)
    painter.end()
    return QCursor(pixmap, 3, 10)


class SprayCanvas(QWidget):
    completed = Signal()
    progress = Signal(int)

    def __init__(self, garden, parent):
        super().__init__(parent)
        self.definition, self.stage, self.skin = garden.definition, garden.stage, garden.equipped_skin
        self.hits = 0
        self.frame = 0
        self.spraying = False
        self.done = False
        self.setFixedHeight(205)
        self.setCursor(spray_cursor())
        self.setAccessibleName('분무기 · 식물을 세 번 클릭하세요')
        self.timer = QTimer(self)
        self.timer.setInterval(25)
        self.timer.timeout.connect(self.animate)

    def plant_rect(self):
        scale = min(self.width() / 380, self.height() / 180)
        return QRectF((self.width() - 380 * scale) / 2 + 135 * scale,
                      8 * scale, 110 * scale, 156 * scale)

    def mousePressEvent(self, event):
        if (event.button() == Qt.LeftButton and not self.done and not self.spraying
                and self.plant_rect().contains(event.position())):
            self.spraying = True
            self.frame = 0
            self.hits += 1
            self.progress.emit(self.hits)
            self.timer.start()
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def animate(self):
        self.frame += 1
        if self.frame >= 12:
            self.timer.stop()
            self.spraying = False
            if self.hits == 3 and not self.done:
                self.done = True
                self.unsetCursor()
                self.completed.emit()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        scale = min(self.width() / 380, self.height() / 180)
        painter.translate((self.width() - 380 * scale) / 2, 0)
        painter.scale(scale, scale)
        paint_potted_flower(painter, self.definition, self.stage, skin=self.skin)
        if self.spraying:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(93, 178, 215, max(0, 240 - self.frame * 15)))
            for index in range(24):
                angle = (index % 7 - 3) * .12
                distance = 12 + self.frame * 7 + (index // 7) * 9
                x = 96 + math.cos(angle) * distance
                y = 48 + math.sin(angle) * distance + self.frame * 1.5
                painter.drawEllipse(QPointF(x, y), 2, 3)
        painter.end()


class MistGame(QDialog):
    completed = Signal()

    def __init__(self, parent, garden):
        super().__init__(parent)
        self.finished_spraying = False
        self.setWindowTitle('분무 미니게임')
        self.setWindowModality(Qt.WindowModal)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(parent.windowFlags() & Qt.WindowStaysOnTopHint))
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowOpacity(parent.windowOpacity())
        self.setFixedWidth(320)
        layout = QVBoxLayout(self)
        self.status = QLabel('식물을 클릭해 분무하세요 · 0 / 3')
        layout.addWidget(self.status)
        self.canvas = SprayCanvas(garden, self)
        layout.addWidget(self.canvas)
        hint = QLabel('물방울이 사라지면 다시 클릭하세요.\n3회 완료할 때만 분무 효과가 적용됩니다.')
        layout.addWidget(hint)
        self.result = QLabel('')
        self.result.setWordWrap(True)
        layout.addWidget(self.result)
        self.close_button = QPushButton('취소 · Esc')
        self.close_button.clicked.connect(self.reject)
        layout.addWidget(self.close_button)
        self.canvas.progress.connect(lambda n: self.status.setText(f'분무 중 · {n} / 3'))
        self.canvas.completed.connect(self.finish_spraying)
        self.finished.connect(lambda _: self.canvas.timer.stop())

    def finish_spraying(self):
        if self.finished_spraying:
            return
        self.finished_spraying = True
        self.status.setText('분무 3회 완료')
        self.close_button.setText('돌아가기')
        self.completed.emit()
