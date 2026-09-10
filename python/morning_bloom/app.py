import argparse
import math
import sys
import time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, QStandardPaths, QLockFile
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QFontDatabase
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QSlider, QCheckBox, QMessageBox)
from .storage import Store, SaveError

class Flower(QWidget):
    def __init__(self, garden):
        super().__init__()
        self.garden = garden
        self.phase = 0
        self.drops = 0
        self.setMinimumHeight(230)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(50)

    def animate(self):
        self.phase += .08
        self.drops = max(0, self.drops - 1)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(self.width() / 380, self.height() / 240)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#e8efdf'))
        p.drawEllipse(QRectF(75, 190, 230, 30))
        p.setBrush(QColor('#bd7e5c'))
        p.drawRoundedRect(QRectF(144, 158, 92, 56), 14, 14)
        p.setBrush(QColor('#d99b75'))
        p.drawRoundedRect(QRectF(136, 150, 108, 19), 6, 6)
        p.setBrush(QColor('#654638'))
        p.drawEllipse(QRectF(143, 146, 94, 13))
        if self.garden.planted:
            stage = self.garden.stage
            top = 142 - stage * 24
            sway = math.sin(self.phase) * 3 if not self.garden.vacation else 0
            p.setPen(QPen(QColor('#64835b'), 5, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(190, 151), QPointF(190 + sway, top))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('#86a674'))
            if stage:
                p.drawEllipse(QRectF(166 + sway, top + 25, 26, 12))
                p.drawEllipse(QRectF(192 + sway, top + 12, 27, 13))
            if stage >= 3:
                p.save()
                p.translate(190 + sway, top)
                for i in range(8):
                    p.save()
                    p.rotate(i * 45)
                    p.setBrush(QColor('#fffdf3'))
                    p.drawEllipse(QRectF(-8, -31 if stage == 4 else -18, 16, 28 if stage == 4 else 17))
                    p.restore()
                p.setBrush(QColor('#e6b953'))
                p.drawEllipse(QRectF(-10, -10, 20, 20))
                p.restore()
            else:
                p.setBrush(QColor('#a0b581'))
                p.drawEllipse(QRectF(183 + sway, top - 6, 14, 10))
        if self.drops:
            p.setBrush(QColor('#81b8ce'))
            for i in range(7):
                p.drawEllipse(QRectF(140 + i * 16, 60 + ((30 - self.drops) * 4 + i * 13) % 85, 4, 9))
        p.end()

class Window(QWidget):
    def __init__(self, store, garden, demo=False):
        super().__init__()
        self.store, self.garden, self.demo = store, garden, demo
        self.offset = 0
        self.setWindowTitle('아침 한 송이')
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, garden.settings['topmost'])
        self.setFixedSize(420, 690 if demo else 650)
        self.setStyleSheet('''QWidget {background:#f8f7ef;color:#334e41;font-size:14px;}
            QPushButton {background:#e5ecde;border:0;border-radius:9px;padding:10px;}
            QPushButton:hover {background:#d5e1cb;} QPushButton:disabled {color:#a7afa3;}
            QLabel#title {font-size:22px;font-weight:600;} QLabel#small {color:#778575;font-size:12px;}
            QProgressBar {border:0;background:#e5e9df;border-radius:5px;height:10px;text-align:center;}
            QProgressBar::chunk {background:#8faa79;border-radius:5px;}''')
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        top = QHBoxLayout()
        self.title = QLabel('아침 한 송이' + (' · 데모' if demo else ''))
        self.title.setObjectName('title')
        self.title.mousePressEvent = self.drag
        top.addWidget(self.title)
        top.addStretch()
        close = QPushButton('×')
        close.setFixedWidth(38)
        close.clicked.connect(self.close)
        top.addWidget(close)
        root.addLayout(top)
        hint = QLabel('하루의 작은 정원  /  제목을 잡고 이동하세요')
        hint.setObjectName('small')
        root.addWidget(hint)
        self.flower = Flower(garden)
        root.addWidget(self.flower)
        self.status = QLabel()
        self.status.setAlignment(Qt.AlignCenter)
        root.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        root.addWidget(self.progress)
        self.remaining = QLabel()
        self.remaining.setAlignment(Qt.AlignCenter)
        self.remaining.setObjectName('small')
        root.addWidget(self.remaining)
        row = QHBoxLayout()
        self.plant_button = self.button(row, '씨앗 심기', lambda: garden.plant(self.now()))
        self.water_button = self.button(row, '물주기', lambda: self.care('water'))
        self.mist_button = self.button(row, '분무', lambda: self.care('mist'))
        root.addLayout(row)
        row = QHBoxLayout()
        self.harvest_button = self.button(row, '꽃 보관', lambda: garden.harvest(self.now()))
        self.sell_button = self.button(row, '보관 꽃 판매 · 50G', garden.sell)
        root.addLayout(row)
        self.inventory = QLabel()
        root.addWidget(self.inventory)
        self.vacation = QCheckBox('휴가 모드')
        self.vacation.setChecked(garden.vacation)
        self.vacation.toggled.connect(lambda checked: self.act(lambda: garden.set_vacation(checked, self.now())))
        self.topmost = QCheckBox('항상 위')
        self.topmost.setChecked(garden.settings['topmost'])
        self.topmost.toggled.connect(self.toggle_topmost)
        row = QHBoxLayout()
        row.addWidget(self.vacation)
        row.addWidget(self.topmost)
        root.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel('불투명도'))
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(10, 100)
        self.opacity.setValue(round(garden.settings['opacity'] * 100))
        self.opacity.valueChanged.connect(self.set_opacity)
        row.addWidget(self.opacity)
        reset = QPushButton('복구')
        reset.clicked.connect(lambda: self.opacity.setValue(100))
        row.addWidget(reset)
        root.addLayout(row)
        if demo:
            row = QHBoxLayout()
            self.button(row, '+6시간', self.fast_forward)
            root.addLayout(row)
        self.message = QLabel(store.notice or '첫 꽃은 60초, 다음 꽃은 24시간에 자라요.')
        self.message.setWordWrap(True)
        self.message.setObjectName('small')
        root.addWidget(self.message)
        self.setWindowOpacity(garden.settings['opacity'])
        pos = QPointF(garden.settings['x'], garden.settings['y']).toPoint()
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        rect = screen.availableGeometry()
        x = max(rect.left(), min(pos.x(), rect.right() - self.width() + 1))
        y = max(rect.top(), min(pos.y(), rect.bottom() - self.height() + 1))
        if pos.x() == -99999:
            x, y = rect.right() - self.width() - 16, rect.bottom() - self.height() - 16
        self.move(x, y)
        self.clock = QTimer(self)
        self.clock.timeout.connect(self.refresh)
        self.clock.start(1000)
        self.autosave = QTimer(self)
        self.autosave.timeout.connect(self.persist)
        self.autosave.start(30000)
        self.refresh()

    def now(self): return time.time() + self.offset

    def drag(self, event):
        if event.button() == Qt.LeftButton and self.windowHandle(): self.windowHandle().startSystemMove()

    def button(self, layout, text, callback):
        button = QPushButton(text)
        button.clicked.connect(lambda: self.act(callback))
        layout.addWidget(button)
        return button

    def act(self, callback):
        result = callback()
        if result is False: self.message.setText('지금은 할 수 없는 행동이에요.')
        self.refresh()
        self.persist()

    def care(self, kind):
        done = self.garden.care(kind, self.now())
        if done:
            self.flower.drops = 30
            self.message.setText('돌봤어요. 이른 돌봄은 효과만 보여주며 성장을 가속하지 않아요.')
        return done

    def fast_forward(self):
        self.offset += 6 * 3600

    def toggle_topmost(self, checked):
        self.garden.settings['topmost'] = checked
        self.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        self.show()
        self.persist()

    def set_opacity(self, value):
        self.garden.settings['opacity'] = value / 100
        self.setWindowOpacity(value / 100)

    def refresh(self):
        g = self.garden
        g.advance(self.now())
        self.status.setText(g.health)
        self.progress.setValue(int(g.ratio * 100))
        seconds = max(0, math.ceil(g.duration - g.growth))
        stage = ('씨앗', '새싹', '자라는 중', '봉오리', '개화')[g.stage]
        self.remaining.setText(f'{stage} · 남은 성장 {seconds // 3600}시간 {(seconds % 3600) // 60}분 {seconds % 60}초' if g.planted else '빈 화분 · 데이지 1종')
        self.inventory.setText(f'{g.coins}G   ·   씨앗 {g.seeds}개   ·   보관한 데이지 {len(g.collection)}송이')
        self.plant_button.setText('씨앗 심기' if g.seeds else '심기 · 20G')
        self.plant_button.setEnabled(not g.planted and not g.vacation and (g.seeds > 0 or g.coins >= 20))
        for button in (self.water_button, self.mist_button): button.setEnabled(g.planted and not g.bloomed and not g.vacation)
        self.harvest_button.setEnabled(g.bloomed)
        self.sell_button.setEnabled(bool(g.collection))
        self.flower.update()

    def persist(self):
        self.garden.advance(self.now())
        self.garden.settings.update(x=self.x(), y=self.y())
        try: self.store.save(self.garden)
        except (SaveError, ValueError) as exc:
            self.message.setText('저장 실패 · ' + str(exc))
            return False
        return True

    def closeEvent(self, event):
        if self.persist(): event.accept()
        else:
            result = QMessageBox.question(self, '저장 실패', '저장하지 않고 종료할까요?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            event.accept() if result == QMessageBox.Yes else event.ignore()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true', help='별도 저장과 +6시간 버튼')
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName('MorningBloomPython')
    font = Path(__file__).resolve().parents[2] / 'assets/fonts/NotoSansKR-Subset.otf'
    if font.exists():
        fid = QFontDatabase.addApplicationFont(str(font))
        families = QFontDatabase.applicationFontFamilies(fid)
        if families: app.setFont(QFont(families[0], 10))
    path = Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))
    path.mkdir(parents=True, exist_ok=True)
    name = 'demo-garden' if args.demo else 'garden'
    lock = QLockFile(str(path / (name + '.lock')))
    if not lock.tryLock(0):
        QMessageBox.warning(None, '이미 실행 중', '같은 정원이 이미 실행 중입니다.')
        return 1
    store = Store(path / (name + '.json'))
    try: garden = store.load(time.time())
    except SaveError as exc:
        QMessageBox.critical(None, '저장 파일 보호', str(exc) + '\n' + str(path))
        return 1
    window = Window(store, garden, args.demo)
    # Continue the demo timeline after a previous accelerated session.
    if args.demo: window.offset = max(0, garden.last_update - time.time())
    window.show()
    return app.exec()
