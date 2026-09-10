import argparse
import math
import sys
import time
from pathlib import Path

from PySide6.QtCore import QLockFile, QPointF, QRectF, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .plant_catalog import PLANTS, plant_definition
from .storage import SaveError, Store


class Flower(QWidget):
    def __init__(self, garden):
        super().__init__()
        self.garden = garden
        self.phase = 0
        self.drops = 0
        self.setMinimumHeight(118)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(50)

    def animate(self):
        self.phase += .08
        self.drops = max(0, self.drops - 1)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(self.width() / 380, self.height() / 180)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#e8efdf'))
        painter.drawEllipse(QRectF(75, 144, 230, 24))
        definition = self.garden.definition
        painter.setBrush(QColor(definition.pot_color))
        painter.drawRoundedRect(QRectF(144, 112, 92, 49), 14, 14)
        painter.setBrush(QColor('#d99b75'))
        painter.drawRoundedRect(QRectF(136, 104, 108, 18), 6, 6)
        painter.setBrush(QColor('#654638'))
        painter.drawEllipse(QRectF(143, 101, 94, 12))
        if self.garden.planted:
            self._draw_plant(painter, definition)
        if self.drops:
            painter.setBrush(QColor('#81b8ce'))
            for index in range(7):
                y = 24 + ((30 - self.drops) * 4 + index * 13) % 76
                painter.drawEllipse(QRectF(140 + index * 16, y, 4, 9))
        painter.end()

    def _draw_plant(self, painter, definition):
        stage = self.garden.stage
        top = 98 - stage * 18
        sway = math.sin(self.phase) * 3 if not self.garden.vacation else 0
        painter.setPen(QPen(QColor('#64835b'), 5, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(190, 106), QPointF(190 + sway, top))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(definition.leaf_color))
        if stage:
            painter.drawEllipse(QRectF(164 + sway, top + 18, 28, 12))
            painter.drawEllipse(QRectF(192 + sway, top + 8, 29, 13))
        if stage >= 3:
            painter.save()
            painter.translate(190 + sway, top)
            if definition.key == 'tulip':
                self._draw_tulip(painter, definition, stage == 4)
            else:
                self._draw_daisy(painter, definition, stage == 4)
            painter.restore()
        else:
            painter.setBrush(QColor(definition.leaf_color))
            painter.drawEllipse(QRectF(183 + sway, top - 6, 14, 10))

    @staticmethod
    def _draw_daisy(painter, definition, open_flower):
        for index in range(8):
            painter.save()
            painter.rotate(index * 45)
            painter.setBrush(QColor(definition.petal_color))
            length = 27 if open_flower else 17
            painter.drawEllipse(QRectF(-8, -30 if open_flower else -18, 16, length))
            painter.restore()
        painter.setBrush(QColor(definition.center_color))
        painter.drawEllipse(QRectF(-10, -10, 20, 20))

    @staticmethod
    def _draw_tulip(painter, definition, open_flower):
        width = 25 if open_flower else 18
        top = -34 if open_flower else -25
        flower = QPainterPath()
        flower.moveTo(-width, -3)
        flower.lineTo(-width + 3, top)
        flower.lineTo(0, top + (12 if open_flower else 6))
        flower.lineTo(width - 3, top)
        flower.lineTo(width, -3)
        flower.quadTo(0, 13, -width, -3)
        painter.setBrush(QColor(definition.petal_color))
        painter.drawPath(flower)
        painter.setBrush(QColor(definition.center_color))
        painter.drawEllipse(QRectF(-5, -8, 10, 8))


class Window(QWidget):
    def __init__(self, store, garden, demo=False):
        super().__init__()
        self.store, self.garden, self.demo = store, garden, demo
        self.offset = 0
        self.setWindowTitle('아침 한 송이')
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, garden.settings['topmost'])
        self._set_responsive_square()
        self._set_style()
        self._build_ui()
        self._place_window()
        self.setWindowOpacity(garden.settings['opacity'])

        self.clock = QTimer(self)
        self.clock.timeout.connect(self.refresh)
        self.clock.start(1000)
        self.autosave = QTimer(self)
        self.autosave.timeout.connect(self.persist)
        self.autosave.start(30000)
        self.refresh()

    def _set_responsive_square(self):
        saved_position = QPointF(
            self.garden.settings['x'],
            self.garden.settings['y'],
        ).toPoint()
        screen = QApplication.screenAt(saved_position) or QApplication.primaryScreen()
        width = screen.availableGeometry().width() if screen else 1920
        side = max(320, min(520, round(width * .2)))
        self.setFixedSize(side, side)

    def _set_style(self):
        self.setStyleSheet('''
            QWidget {background:#f8f7ef;color:#334e41;font-size:13px;}
            QPushButton {background:#e5ecde;border:0;border-radius:9px;padding:7px;}
            QPushButton:hover {background:#d5e1cb;} QPushButton:disabled {color:#a7afa3;}
            QLabel#title {font-size:18px;font-weight:600;} QLabel#small {color:#778575;font-size:11px;}
            QLabel#section {font-size:16px;font-weight:600;}
            QProgressBar {border:0;background:#e5e9df;border-radius:4px;height:8px;text-align:center;}
            QProgressBar::chunk {background:#8faa79;border-radius:4px;}
            QComboBox {background:#ffffff;border:1px solid #dce3d6;border-radius:8px;padding:6px;}
            QSlider::groove:horizontal {height:5px;background:#dfe5d8;border-radius:2px;}
            QSlider::sub-page:horizontal {background:#8faa79;border-radius:2px;}
            QSlider::handle:horizontal {width:13px;margin:-4px 0;background:#647f5b;border-radius:6px;}
        ''')

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 12)
        root.setSpacing(5)
        top = QHBoxLayout()
        self.title = QLabel('아침 한 송이' + (' · 데모' if self.demo else ''))
        self.title.setObjectName('title')
        self.title.mousePressEvent = self.drag
        top.addWidget(self.title)
        top.addStretch()
        close = QPushButton('X')
        close.setFixedSize(34, 30)
        close.clicked.connect(self.close)
        top.addWidget(close)
        root.addLayout(top)

        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        self._build_garden_page()
        self._build_settings_page()

    def _build_garden_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.flower = Flower(self.garden)
        layout.addWidget(self.flower, 1)
        self.status = QLabel()
        self.status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.remaining = QLabel()
        self.remaining.setAlignment(Qt.AlignCenter)
        self.remaining.setObjectName('small')
        layout.addWidget(self.remaining)

        row = QHBoxLayout()
        self.species_picker = QComboBox()
        for definition in PLANTS.values():
            self.species_picker.addItem(
                f'{definition.name} · {definition.growth_seconds // 86400}일',
                definition.key,
            )
        self.species_picker.currentIndexChanged.connect(self.refresh)
        row.addWidget(self.species_picker, 1)
        self.plant_button = self.button(row, '씨앗 심기', self.plant_selected)
        layout.addLayout(row)

        row = QHBoxLayout()
        self.water_button = self.button(row, '물주기', lambda: self.care('water'))
        self.mist_button = self.button(row, '분무', lambda: self.care('mist'))
        self.harvest_button = self.button(row, '꽃 보관', lambda: self.garden.harvest(self.now()))
        layout.addLayout(row)

        row = QHBoxLayout()
        self.inventory = QLabel()
        self.inventory.setObjectName('small')
        self.inventory.setMinimumWidth(0)
        self.inventory.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        row.addWidget(self.inventory, 1)
        self.sell_button = self.button(row, '꽃 판매', self.garden.sell)
        settings = self.button(row, '설정', lambda: self.pages.setCurrentIndex(1))
        settings.setFixedWidth(48)
        if self.demo:
            demo_button = self.button(row, '+6h', self.fast_forward)
            demo_button.setFixedWidth(44)
        layout.addLayout(row)
        self.message = QLabel(self.store.notice or '첫 꽃은 60초, 다음 꽃부터 실제 성장 시간을 사용해요.')
        self.message.setWordWrap(True)
        self.message.setMaximumHeight(30)
        self.message.setObjectName('small')
        layout.addWidget(self.message)
        self.pages.addWidget(page)

    def _build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(12)
        title = QLabel('환경 설정')
        title.setObjectName('section')
        layout.addWidget(title)
        hint = QLabel('창 설정은 종료 후에도 그대로 유지됩니다.')
        hint.setObjectName('small')
        layout.addWidget(hint)
        self.vacation = QCheckBox('휴가 모드 · 성장과 돌봄 시계 정지')
        self.vacation.setChecked(self.garden.vacation)
        self.vacation.toggled.connect(
            lambda checked: self.act(lambda: self.garden.set_vacation(checked, self.now()))
        )
        layout.addWidget(self.vacation)
        self.topmost = QCheckBox('항상 위에 표시')
        self.topmost.setChecked(self.garden.settings['topmost'])
        self.topmost.toggled.connect(self.toggle_topmost)
        layout.addWidget(self.topmost)
        row = QHBoxLayout()
        row.addWidget(QLabel('불투명도'))
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(10, 100)
        self.opacity.setValue(round(self.garden.settings['opacity'] * 100))
        self.opacity.valueChanged.connect(self.set_opacity)
        row.addWidget(self.opacity, 1)
        reset = QPushButton('100%')
        reset.clicked.connect(lambda: self.opacity.setValue(100))
        row.addWidget(reset)
        layout.addLayout(row)
        catalog = QLabel(
            '식물 카탈로그\n'
            + '\n'.join(
                f'• {item.name}: {item.growth_seconds // 86400}일 · 씨앗 {item.seed_price}G · 판매 {item.sale_price}G'
                for item in PLANTS.values()
            )
        )
        catalog.setObjectName('small')
        catalog.setWordWrap(True)
        layout.addWidget(catalog)
        layout.addStretch()
        back = QPushButton('정원으로 돌아가기')
        back.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        layout.addWidget(back)
        self.pages.addWidget(page)

    def _place_window(self):
        position = QPointF(self.garden.settings['x'], self.garden.settings['y']).toPoint()
        screen = QApplication.screenAt(position) or QApplication.primaryScreen()
        if not screen:
            return
        rect = screen.availableGeometry()
        x = max(rect.left(), min(position.x(), rect.right() - self.width() + 1))
        y = max(rect.top(), min(position.y(), rect.bottom() - self.height() + 1))
        if position.x() == -99999:
            x, y = rect.right() - self.width() - 16, rect.bottom() - self.height() - 16
        self.move(x, y)

    def now(self):
        return time.time() + self.offset

    def drag(self, event):
        if event.button() == Qt.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()

    def button(self, layout, text, callback):
        button = QPushButton(text)
        button.clicked.connect(lambda: self.act(callback))
        layout.addWidget(button)
        return button

    def act(self, callback):
        result = callback()
        if result is False:
            self.message.setText('지금은 할 수 없는 행동이에요.')
        self.refresh()
        self.persist()

    def plant_selected(self):
        return self.garden.plant(self.now(), self.species_picker.currentData())

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
        position = self.pos()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        self.move(position)
        self.show()
        self.persist()

    def set_opacity(self, value):
        self.garden.settings['opacity'] = value / 100
        self.setWindowOpacity(value / 100)

    def refresh(self):
        garden = self.garden
        garden.advance(self.now())
        self.status.setText(garden.health)
        self.progress.setValue(int(garden.ratio * 100))
        seconds = max(0, math.ceil(garden.duration - garden.growth))
        stage = ('씨앗', '새싹', '자라는 중', '봉오리', '개화')[garden.stage]
        if garden.planted:
            self.remaining.setText(
                f'{garden.definition.name} · {stage} · {seconds // 3600}시간 '
                f'{(seconds % 3600) // 60}분 {seconds % 60}초'
            )
        else:
            self.remaining.setText('빈 화분 · 키울 식물을 선택하세요')

        selected = self.species_picker.currentData()
        definition = plant_definition(selected)
        count = garden.seed_count(selected)
        self.plant_button.setText('씨앗 심기' if count else f'구매해 심기 · {definition.seed_price}G')
        self.plant_button.setEnabled(garden.can_plant(selected))
        self.species_picker.setEnabled(not garden.planted and not garden.vacation)
        for button in (self.water_button, self.mist_button):
            button.setEnabled(garden.planted and not garden.bloomed and not garden.vacation)
        self.harvest_button.setEnabled(garden.bloomed)

        seed_total = sum(garden.seeds.values())
        self.inventory.setText(f'{garden.coins}G · 씨앗 {seed_total} · 꽃 {len(garden.collection)}')
        seeds = ' / '.join(f'{item.name} {garden.seed_count(key)}' for key, item in PLANTS.items())
        self.inventory.setToolTip(f'씨앗 {seeds} · 보관 꽃 {len(garden.collection)}')
        if garden.collection:
            last = plant_definition(garden.collection[-1]['species'])
            self.sell_button.setText(f'판매 {last.sale_price}G')
        else:
            self.sell_button.setText('꽃 판매')
        self.sell_button.setEnabled(bool(garden.collection))
        self.flower.update()

    def persist(self):
        self.garden.advance(self.now())
        self.garden.settings.update(x=self.x(), y=self.y())
        try:
            self.store.save(self.garden)
        except (SaveError, ValueError) as exc:
            self.message.setText('저장 실패 · ' + str(exc))
            return False
        return True

    def resizeEvent(self, event):
        compact = self.width() < 360
        self.message.setVisible(not compact)
        self.flower.setMinimumHeight(88 if compact else 118)
        super().resizeEvent(event)

    def closeEvent(self, event):
        if self.persist():
            event.accept()
        else:
            result = QMessageBox.question(
                self,
                '저장 실패',
                '저장하지 않고 종료할까요?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            event.accept() if result == QMessageBox.Yes else event.ignore()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true', help='별도 저장과 +6시간 버튼')
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName('MorningBloomPython')
    font = Path(__file__).resolve().parents[2] / 'assets/fonts/NotoSansKR-Subset.otf'
    if font.exists():
        font_id = QFontDatabase.addApplicationFont(str(font))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 10))
    path = Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))
    path.mkdir(parents=True, exist_ok=True)
    name = 'demo-garden' if args.demo else 'garden'
    lock = QLockFile(str(path / (name + '.lock')))
    if not lock.tryLock(0):
        QMessageBox.warning(None, '이미 실행 중', '같은 정원이 이미 실행 중입니다.')
        return 1
    store = Store(path / (name + '.json'))
    try:
        garden = store.load(time.time())
    except SaveError as exc:
        QMessageBox.critical(None, '저장 파일 보호', str(exc) + '\n' + str(path))
        return 1
    window = Window(store, garden, args.demo)
    if args.demo:
        window.offset = max(0, garden.last_update - time.time())
    window.show()
    return app.exec()
