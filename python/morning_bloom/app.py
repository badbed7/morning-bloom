import argparse
import math
import sys
import time
from pathlib import Path

from PySide6.QtCore import QLockFile, QPointF, QRectF, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .flower_art import paint_potted_flower
from .garden_view import CollectionGarden, sale_price
from .navigation import SlideStack
from .plant_catalog import PLANTS, plant_definition
from .storage import SaveError, Store

POT_PAGE, SHOP_PAGE, GARDEN_PAGE, SETTINGS_PAGE = range(4)
MAIN_PAGE_NAMES = ('화분', '상점', '정원')


def format_duration(seconds):
    if seconds is None:
        return '첫 물주기 후 계산'
    seconds = max(0, math.ceil(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        return f'{days}일 {hours}시간'
    if hours:
        return f'{hours}시간 {minutes}분'
    return f'{minutes}분 {seconds}초'


class Flower(QWidget):
    def __init__(self, garden):
        super().__init__()
        self.garden = garden
        self.phase = 0
        self.drops = 0
        self.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.setInterval(50)

    def showEvent(self, event):
        self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def animate(self):
        self.phase += .08
        self.drops = max(0, self.drops - 1)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        scale = min(self.width() / 380, self.height() / 180)
        painter.translate((self.width() - 380 * scale) / 2, 0)
        painter.scale(scale, scale)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#e8efdf'))
        painter.drawEllipse(QRectF(75, 144, 230, 24))
        paint_potted_flower(
            painter, self.garden.definition, stage=self.garden.stage,
            phase=0 if self.garden.vacation else self.phase,
            planted=self.garden.planted, drops=self.drops,
        )
        painter.end()


class Window(QWidget):
    def __init__(self, store, garden, demo=False):
        super().__init__()
        self.store, self.garden, self.demo = store, garden, demo
        self.offset = 0
        self._main_page = POT_PAGE
        self._message_important = False
        self._action_busy = False
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
            QLabel#title {font-size:15px;font-weight:600;} QLabel#small {color:#778575;font-size:11px;}
            QLabel#section {font-size:16px;font-weight:600;}
            QProgressBar {border:0;background:#e5e9df;border-radius:4px;height:8px;text-align:center;}
            QProgressBar::chunk {background:#8faa79;border-radius:4px;}
            QComboBox {background:#ffffff;border:1px solid #dce3d6;border-radius:8px;padding:6px;}
            QSlider::groove:horizontal {height:5px;background:#dfe5d8;border-radius:2px;}
            QSlider::sub-page:horizontal {background:#8faa79;border-radius:2px;}
            QSlider::handle:horizontal {width:13px;margin:-4px 0;background:#647f5b;border-radius:6px;}
            QScrollBar:vertical {background:#eef0e5;width:8px;margin:0;}
            QScrollBar::handle:vertical {background:#9bae83;border-radius:4px;min-height:22px;}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {background:transparent;}
        ''')

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(3)
        self.title = QLabel('아침 한 송이' + (' · 데모' if self.demo else ''))
        self.title.setObjectName('title')
        self.title.setMinimumWidth(0)
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.title.mousePressEvent = self.drag
        top.addWidget(self.title, 1)
        self.previous_page = QPushButton('‹')
        self.previous_page.setFixedSize(26, 28)
        self.previous_page.setAccessibleName('이전 화면')
        self.previous_page.clicked.connect(lambda: self.navigate(-1))
        top.addWidget(self.previous_page)
        self.page_name = QLabel('화분')
        self.page_name.setAlignment(Qt.AlignCenter)
        self.page_name.setFixedWidth(36)
        top.addWidget(self.page_name)
        self.next_page = QPushButton('›')
        self.next_page.setFixedSize(26, 28)
        self.next_page.setAccessibleName('다음 화면')
        self.next_page.clicked.connect(lambda: self.navigate(1))
        top.addWidget(self.next_page)
        close = QPushButton('X')
        close.setFixedSize(28, 28)
        close.setAccessibleName('저장 후 종료')
        close.clicked.connect(self.close)
        top.addWidget(close)
        root.addLayout(top)

        self.pages = SlideStack()
        root.addWidget(self.pages, 1)
        self._build_pot_page()
        self._build_shop_page()
        self.collection_garden = CollectionGarden(self.garden, self.sell_flower)
        self.pages.addWidget(self.collection_garden)
        self._build_settings_page()

        welcome = '' if self.garden.tutorial_used else '첫 꽃은 첫 물주기 후 60초에 피어요.'
        self.message = QLabel(self.store.notice or welcome)
        self.message.setWordWrap(True)
        self.message.setMaximumHeight(30)
        self.message.setMinimumWidth(0)
        self.message.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.message.setObjectName('small')
        root.addWidget(self.message)

        footer = QHBoxLayout()
        self.inventory = QLabel()
        self.inventory.setObjectName('small')
        self.inventory.setMinimumWidth(0)
        self.inventory.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        footer.addWidget(self.inventory, 1)
        if self.demo:
            demo_button = self.button(footer, '+6h', self.fast_forward)
            demo_button.setFixedWidth(44)
        self.settings_button = QPushButton('설정')
        self.settings_button.setFixedWidth(72)
        self.settings_button.setAccessibleName('설정 열기 또는 이전 화면으로 돌아가기')
        self.settings_button.clicked.connect(self.toggle_settings_page)
        footer.addWidget(self.settings_button)
        root.addLayout(footer)
        self.pages.currentChanged.connect(self._page_changed)
        self._page_changed(POT_PAGE)

    def _page_changed(self, index):
        is_settings = index == SETTINGS_PAGE
        if not is_settings:
            self._main_page = index
        self.page_name.setText('설정' if is_settings else MAIN_PAGE_NAMES[index])
        self.previous_page.setEnabled(not is_settings)
        self.next_page.setEnabled(not is_settings)
        self.settings_button.setText('돌아가기' if is_settings else '설정')
        if not is_settings:
            self.previous_page.setToolTip(MAIN_PAGE_NAMES[(index - 1) % 3] + '으로 이동')
            self.next_page.setToolTip(MAIN_PAGE_NAMES[(index + 1) % 3] + '으로 이동')

    def navigate(self, direction):
        if self.pages.currentIndex() == SETTINGS_PAGE:
            return
        target = (self.pages.currentIndex() + direction) % len(MAIN_PAGE_NAMES)
        self.pages.slide_to(target, direction)

    def toggle_settings_page(self):
        if self.pages.currentIndex() == SETTINGS_PAGE:
            self.pages.slide_to(self._main_page, -1)
        else:
            self.pages.slide_to(SETTINGS_PAGE)

    def _build_pot_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.pot_picker = QComboBox()
        self.pot_picker.setMinimumWidth(0)
        self.pot_picker.setFixedHeight(28)
        self.pot_picker.currentIndexChanged.connect(lambda index: self.act(lambda: self.garden.select(index)))
        layout.addWidget(self.pot_picker)
        self.flower = Flower(self.garden)
        layout.addWidget(self.flower, 1)
        self.status = QLabel()
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFixedHeight(18)
        self.status.setMinimumWidth(0)
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        layout.addWidget(self.progress)
        self.remaining = QLabel()
        self.remaining.setAlignment(Qt.AlignCenter)
        self.remaining.setObjectName('small')
        self.remaining.setFixedHeight(16)
        layout.addWidget(self.remaining)
        self.care_info = QLabel()
        self.care_info.setAlignment(Qt.AlignCenter)
        self.care_info.setObjectName('small')
        self.care_info.setFixedHeight(16)
        layout.addWidget(self.care_info)

        row = QHBoxLayout()
        self.species_picker = QComboBox()
        self.species_picker.setMinimumWidth(0)
        self.species_picker.setFixedHeight(28)
        self.species_picker.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        for definition in PLANTS.values():
            self.species_picker.addItem(
                f'{definition.name} · {format_duration(definition.growth_seconds)}',
                definition.key,
            )
        self.species_picker.currentIndexChanged.connect(self.refresh)
        row.addWidget(self.species_picker, 1)
        self.plant_button = self.button(row, '씨앗 심기', self.plant_selected)
        layout.addLayout(row)

        row = QHBoxLayout()
        self.water_button = self.button(row, '물주기', lambda: self.care('water'))
        self.mist_button = self.button(row, '분무', lambda: self.care('mist'))
        self.harvest_button = self.button(row, '정원 보관', self.harvest_flower)
        for button in (self.water_button, self.mist_button, self.harvest_button, self.plant_button):
            button.setFixedHeight(28)
        layout.addLayout(row)

        self.pages.addWidget(page)

    def _scrollable_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        return page, layout

    def _build_settings_page(self):
        page, layout = self._scrollable_page()
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
                f'• {item.name}: {format_duration(item.growth_seconds)} · 씨앗 {item.seed_price}G · 판매 {item.sale_price}G'
                f' (+분무 {item.mist_bonus}G)'
                for item in PLANTS.values()
            )
        )
        catalog.setObjectName('small')
        catalog.setWordWrap(True)
        layout.addWidget(catalog)
        layout.addStretch()
        self.pages.addWidget(page)

    def _build_shop_page(self):
        page, layout = self._scrollable_page()
        self.shop_wallet = QLabel()
        layout.addWidget(self.shop_wallet)
        self.shop_picker = QComboBox()
        for item in PLANTS.values():
            self.shop_picker.addItem(f'{item.name} · {format_duration(item.growth_seconds)}', item.key)
        layout.addWidget(self.shop_picker)
        self.shop_info = QLabel()
        self.shop_info.setWordWrap(True)
        self.shop_info.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(self.shop_info)
        self.buy_seed_button = self.button(layout, '씨앗 구매', lambda: self.garden.buy_seed(self.shop_picker.currentData()))
        layout.addWidget(QLabel('화분 확장 · 씨앗은 별도 구매'))
        self.buy_pot_button = self.button(layout, '두 번째 화분 구매 · 150G', self.garden.buy_pot)
        layout.addStretch()
        self.pages.addWidget(page)
        self.shop_picker.currentIndexChanged.connect(self.refresh)

    def harvest_flower(self):
        result = self.garden.harvest(self.now())
        if result:
            self.notify('꽃을 정원에 보관했어요. 정원에서 확인해 보세요.')
        return result

    def sell_flower(self, item_id):
        item = next((item for item in self.garden.collection if item['id'] == item_id), None)
        if item is None:
            return False
        name, price = plant_definition(item['species']).name, sale_price(item)
        if self.act(lambda: self.garden.sell(item_id)):
            self.notify(f'{name} 판매 +{price}G', important=True)
            return True
        return False

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

    def notify(self, text, important=False):
        self._message_important = important
        self.message.setText(text)
        self.message.setToolTip(text)
        self.message.setVisible(bool(text) and (important or self.width() >= 360))

    def act(self, callback):
        if self._action_busy:
            return False
        self._action_busy = True
        before = self.garden.to_dict()
        try:
            result = callback()
            if result is False:
                self.notify('지금은 할 수 없는 행동이에요.', important=True)
                self.refresh()
                return False
            if not self.persist():
                error = self.message.text()
                self.garden.restore(before)
                self.refresh()
                self.notify(error + ' · 행동을 되돌렸습니다.', important=True)
                return False
            self.refresh()
            return True
        finally:
            self._action_busy = False

    def plant_selected(self):
        return self.garden.plant(self.now(), self.species_picker.currentData())

    def care(self, kind):
        previous_status = self.garden.water_status
        done = self.garden.care(kind, self.now())
        if done:
            self.flower.drops = 30
            if kind == 'mist':
                self.notify(f'분무 완료 · 수확한 꽃의 판매가에 {self.garden.pot["mist_bonus_g"]}G가 더해져요.')
            elif previous_status == 'initial':
                self.notify('첫 물주기 완료 · 지금부터 성장 시간이 흐릅니다.')
            elif previous_status == 'slow':
                self.notify('물주기 완료 · 지금부터 원래 속도로 자랍니다.')
            else:
                self.notify('물주기 완료 · 성장 속도는 그대로 유지됩니다.')
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
        self.status.setToolTip(garden.health)
        self.status.setText(self.status.fontMetrics().elidedText(garden.health, Qt.ElideRight, max(0, self.width() - 24)))
        self.progress.setValue(int(garden.ratio * 100))
        stage = ('씨앗', '새싹', '자라는 중', '봉오리', '개화')[garden.stage]
        if garden.planted:
            self.remaining.setText(f'{garden.definition.name} · {stage} · 예상 {format_duration(garden.remaining_seconds())}')
            self.care_info.setText(self._care_text())
        else:
            self.remaining.setText('빈 화분 · 키울 식물을 선택하세요')
            self.care_info.setText('모든 꽃은 심은 뒤 첫 물주기를 해야 성장해요')

        selected = self.species_picker.currentData()
        count = garden.seed_count(selected)
        self.plant_button.setText('씨앗 심기' if count else '씨앗 없음')
        self.plant_button.setEnabled(garden.can_plant(selected))
        self.species_picker.setEnabled(not garden.planted and not garden.vacation)
        self.species_picker.blockSignals(True)
        for index, item in enumerate(PLANTS.values()):
            self.species_picker.setItemText(
                index, f'{item.name} · {format_duration(item.growth_seconds)} · {garden.seed_count(item.key)}개'
            )
        self.species_picker.blockSignals(False)
        self.vacation.blockSignals(True)
        self.vacation.setChecked(garden.vacation)
        self.vacation.blockSignals(False)
        water_status = garden.water_status
        water_labels = {
            'initial': '첫 물주기', 'early': '미리 물주기',
            'due': '물주기 권장', 'slow': '회복 물주기',
        }
        self.water_button.setText(water_labels.get(water_status, '물주기 완료'))
        self.water_button.setEnabled(water_status in water_labels and not garden.vacation)
        can_mist = (
            garden.planted and garden.pot['initial_watered'] and not garden.pot['misted']
            and not garden.bloomed and not garden.vacation
        )
        mist_bonus = garden.pot['mist_bonus_g'] if garden.planted else 0
        self.mist_button.setText('분무 완료' if garden.planted and garden.pot['misted'] else f'분무 +{mist_bonus}G')
        self.mist_button.setEnabled(can_mist)
        self.harvest_button.setEnabled(garden.bloomed)

        seed_total = sum(garden.seeds.values())
        self.inventory.setText(f'{garden.coins}G · 씨앗 {seed_total} · 꽃 {len(garden.collection)}')
        seeds = ' / '.join(f'{item.name} {garden.seed_count(key)}' for key, item in PLANTS.items())
        self.inventory.setToolTip(f'씨앗 {seeds} · 보관 꽃 {len(garden.collection)}')
        self.pot_picker.blockSignals(True)
        self.pot_picker.clear()
        for i, pot in enumerate(garden.pots):
            name = plant_definition(pot['species']).name if pot['species'] else '빈 화분'
            self.pot_picker.addItem(f'화분 {i + 1} · {name} · {self._pot_state(pot)}')
        self.pot_picker.setCurrentIndex(garden.selected)
        self.pot_picker.blockSignals(False)
        self.shop_wallet.setText(f'보유 {garden.coins}G · 화분 {len(garden.pots)}/2개')
        species = self.shop_picker.currentData()
        item = plant_definition(species)
        care = '첫 물만 필요' if item.care_profile == 'start_only' else '24시간 물 권장 · 30시간부터 감속'
        self.shop_info.setText(
            f'{item.shop_tag}\n성장 {format_duration(item.growth_seconds)} · {care}\n'
            f'판매 {item.sale_price}G · 분무 시 {item.sale_price + item.mist_bonus}G'
        )
        self.buy_seed_button.setText(f'{item.name} 씨앗 구매 · {item.seed_price}G')
        self.buy_seed_button.setEnabled(garden.coins >= item.seed_price)
        self.buy_pot_button.setEnabled(len(garden.pots) < 2 and garden.coins >= 150)
        self.buy_pot_button.setText('두 번째 화분 보유 중' if len(garden.pots) == 2 else '두 번째 화분 구매 · 150G')
        self.collection_garden.sync()
        self.flower.update()

    def _care_text(self):
        garden = self.garden
        if garden.bloomed:
            return f'판매가 {garden.pot["base_sale_g"] + (garden.pot["mist_bonus_g"] if garden.pot["misted"] else 0)}G'
        if not garden.pot['initial_watered']:
            return '첫 물주기 전 · 성장 정지'
        status = garden.water_status
        if status == 'waiting':
            return f'중간 물주기까지 {format_duration(22 * 3600 - garden.pot["care_elapsed"])}'
        if status == 'early':
            return f'미리 물주기 가능 · 권장까지 {format_duration(24 * 3600 - garden.pot["care_elapsed"])}'
        if status == 'due':
            return f'정상 성장 중 · 감속까지 {format_duration(30 * 3600 - garden.pot["care_elapsed"])}'
        if status == 'slow':
            return (
                f'50% 속도 · 지금 물주면 {format_duration(garden.remaining_seconds(True))} / '
                f'그대로면 {format_duration(garden.remaining_seconds())}'
            )
        bonus = garden.pot['mist_bonus_g']
        return '추가 물주기 없음 · ' + ('분무 완료' if garden.pot['misted'] else f'분무 시 +{bonus}G')

    @staticmethod
    def _pot_state(pot):
        if not pot['planted']:
            return '비어 있음'
        if pot['growth'] >= pot['duration']:
            return '개화 완료'
        if not pot['initial_watered']:
            return '첫 물 필요'
        if pot['care_profile'] == 'tulip_midwater' and not pot['mid_watered'] and not pot['legacy_care_exempt']:
            if pot['care_elapsed'] >= 30 * 3600:
                return '감속 중'
            if pot['care_elapsed'] >= 24 * 3600:
                return '물 권장'
        return '성장 중'

    def persist(self):
        self.garden.advance(self.now())
        self.garden.settings.update(x=self.x(), y=self.y())
        try:
            self.store.save(self.garden)
        except (SaveError, ValueError) as exc:
            self.notify('저장 실패 · ' + str(exc), important=True)
            return False
        return True

    def resizeEvent(self, event):
        compact = self.width() < 360
        self.message.setVisible(bool(self.message.text()) and (not compact or self._message_important))
        self.flower.setMinimumHeight(0)
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
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
    font = root / 'assets/fonts/NotoSansKR-Subset.otf'
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
