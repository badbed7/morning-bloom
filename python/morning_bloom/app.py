import argparse
import hashlib
import json
import math
import sys
import time
from concurrent.futures import Future
from threading import Thread
from pathlib import Path

from PySide6.QtCore import QEvent, QLockFile, QPointF, QRectF, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from .cosmetics import POT_SKINS, THEMES, garden_theme, pot_skin
from .cosmetic_icons import skin_icon, theme_icon
from .collection_picker import CollectionPicker
from .flower_art import paint_potted_flower
from .fertilizer_game import FertilizerGame
from .mist_game import MistGame
from .desktop_flowers import DesktopFlowers
from .garden_view import CollectionGarden, sale_price
from .google_cloud import CloudError, GoogleDriveSync
from .model import FERTILIZER_CAP, FERTILIZER_SECONDS, POT_PRICES, TYCOON_RULE
from .icon_picker import IconPicker
from .navigation import SlideStack, chevron_icon
from .plant_catalog import PLANTS, REGULAR_PLANTS, RANDOM_SEED_PRICE, plant_definition
from .seed_picker import SeedPicker
from .storage import SaveError, Store

POT_PAGE, SHOP_PAGE, GARDEN_PAGE, SETTINGS_PAGE = range(4)
MAIN_PAGE_NAMES = ('화분', '상점', '정원')
CLOUD_AUTO_BACKUP_MS = 5 * 60 * 1000


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
        self.setFixedHeight(112)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.setInterval(50)

    def set_window_side(self, side):
        """Keep scene scale stable while status and notification text changes."""
        target = round(max(112, min(200, 112 + (side - 320) * .625)))
        if self.height() != target:
            self.setFixedHeight(target)

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
        painter.setBrush(QColor('#e4e6d2'))
        painter.drawEllipse(QRectF(75, 144, 230, 24))
        paint_potted_flower(
            painter, self.garden.definition, stage=self.garden.stage,
            phase=0 if self.garden.vacation else self.phase,
            planted=self.garden.planted, drops=self.drops,
            skin=self.garden.equipped_skin,
        )
        painter.end()


class Window(QWidget):
    def __init__(self, store, garden, demo=False, save_lock=None, cloud=None):
        super().__init__()
        self.store, self.garden, self.demo = store, garden, demo
        self.offset = max(0, garden.last_update - time.time()) if demo else 0
        self._save_lock = save_lock
        self._main_page = POT_PAGE
        self._message_important = False
        self._action_busy = False
        self._fertilizer_game = None
        self._mist_game = None
        self._collection_picker = None
        self._normal_position = QPointF(garden.settings['x'], garden.settings['y']).toPoint()
        self._minimized = False
        self._closing = False
        self._message_text = ''
        self.cloud = cloud
        self._cloud_future = None
        self._cloud_done = None
        self._cloud_busy = False
        self._cloud_silent_error = False
        self._cloud_last_uploaded_digest = None
        self._cloud_known_saved_at = None
        self._cloud_last_backup_at = None
        self._cloud_auto_error = False
        self._pending_cloud_prompt = None
        self._local_saved_at = store.path.stat().st_mtime if getattr(store, 'path', None) and store.path.exists() else 0
        self._load_cloud_state()
        self.desktop = DesktopFlowers(self)
        self.setWindowTitle('아침 한 송이')
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinimizeButtonHint)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, garden.settings['topmost'])
        self._set_responsive_square()
        self._set_style()
        self._build_ui()
        self.flower.set_window_side(min(self.width(), self.height()))
        self._place_window()
        self._normal_position = self.pos()
        self.setWindowOpacity(garden.settings['opacity'])

        self.clock = QTimer(self)
        self.clock.timeout.connect(self.refresh)
        self.clock.start(1000)
        self.autosave = QTimer(self)
        self.autosave.timeout.connect(self.persist)
        self.autosave.start(30000)
        self.cloud_poll = QTimer(self)
        self.cloud_poll.setInterval(100)
        self.cloud_poll.timeout.connect(self._poll_cloud)
        self.cloud_auto = QTimer(self)
        self.cloud_auto.setInterval(CLOUD_AUTO_BACKUP_MS)
        self.cloud_auto.timeout.connect(self.auto_backup_cloud)
        self.cloud_auto.start()
        self.cloud_start = QTimer(self)
        self.cloud_start.setSingleShot(True)
        self.cloud_start.timeout.connect(self.check_cloud)
        self.cloud_start.start(1500)
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
            QWidget {background:#f7f1e5;color:#5b5142;font-size:13px;}
            QPushButton {background:#eee4d2;border:1px solid #d8cbb6;border-radius:5px;padding:6px;}
            QPushButton:hover {background:#e5dac3;border-color:#b09a78;}
            QPushButton:disabled {background:#f0eadd;color:#a69c89;border-color:#e2d9c9;}
            QPushButton:focus, QToolButton:focus {border:1px solid #7c8968;}
            QPushButton#navigationButton, QPushButton#quiet {background:transparent;border:1px solid transparent;padding:0;}
            QPushButton#navigationButton:hover, QPushButton#quiet:hover {background:#eee4d2;border-color:#d8cbb6;}
            QPushButton#navigationButton:focus, QPushButton#quiet:focus {border-color:#7c8968;}
            QToolButton#iconChoice {background:#fbf7ed;border:1px solid #d8cbb6;border-radius:5px;padding:3px;color:#5b5142;font-size:11px;}
            QToolButton#iconChoice:hover {background:#f0e6d3;border-color:#b09a78;}
            QToolButton#iconChoice:checked {background:#e7ebdd;border:2px solid #7c8968;padding:2px;}
            QToolButton#iconChoice:focus {border-color:#526647;}
            QToolButton#iconChoice:disabled {color:#a69c89;}
            QLabel#title {font-size:15px;font-weight:600;color:#705a40;} QLabel#small {color:#80745e;font-size:11px;}
            QLabel#section {font-size:16px;font-weight:600;}
            QLabel#potTitle {font-weight:600;}
            QWidget#fertilizerTools {background:#eee7d7;border:1px solid #ded2bd;border-radius:5px;}
            QWidget#fertilizerTools QLabel {background:transparent;}
            QPushButton#primary {background:#657957;color:#fffaf0;border-color:#657957;}
            QPushButton#primary:hover {background:#526647;}
            QProgressBar {border:0;background:#e6decd;border-radius:3px;height:8px;text-align:center;}
            QProgressBar::chunk {background:#93a47b;border-radius:3px;}
            QSlider::groove:horizontal {height:5px;background:#e6decd;border-radius:2px;}
            QSlider::sub-page:horizontal {background:#93a47b;border-radius:2px;}
            QSlider::handle:horizontal {width:13px;margin:-4px 0;background:#657957;border-radius:6px;}
            QScrollBar:vertical {background:#f0eadd;width:8px;margin:0;}
            QScrollBar::handle:vertical {background:#b7ad94;border-radius:4px;min-height:22px;}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {background:transparent;}
        ''')

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(3)
        self.title = QLabel('개발자 · 테스트 정원' if self.demo else '아침 한 송이')
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
        self.minimize_button = QPushButton('—')
        self.minimize_button.setObjectName('quiet')
        self.minimize_button.setFixedSize(28, 28)
        self.minimize_button.setAccessibleName('최소화')
        self.minimize_button.setToolTip('작업 표시줄로 최소화')
        self.minimize_button.clicked.connect(self.showMinimized)
        top.addWidget(self.minimize_button)
        close = QPushButton('X')
        close.setObjectName('quiet')
        close.setFixedSize(28, 28)
        close.setAccessibleName('저장 후 종료')
        close.clicked.connect(self.close)
        top.addWidget(close)
        root.addLayout(top)

        self.pages = SlideStack()
        root.addWidget(self.pages, 1)
        self._build_pot_page()
        self._build_shop_page()
        self.collection_garden = CollectionGarden(self.garden, self.sell_flower, self.collect_sun)
        self.collection_garden.meadow.desktopRequested.connect(self.toggle_desktop_flower)
        self.pages.addWidget(self.collection_garden)
        self._build_settings_page()

        welcome = '' if self.garden.tutorial_used else '첫 꽃은 첫 물주기 후 60초에 피어요.'
        self.message = QLabel()
        self.message.setWordWrap(False)
        self.message.setFixedHeight(18)
        self.message.setMinimumWidth(0)
        self.message.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.message.setObjectName('small')

        footer = QHBoxLayout()
        footer_status = QWidget()
        self.footer_status = QStackedLayout(footer_status)
        self.footer_status.setContentsMargins(0, 0, 0, 0)
        self.inventory = QLabel()
        self.inventory.setObjectName('small')
        self.inventory.setMinimumWidth(0)
        self.inventory.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.footer_status.addWidget(self.inventory)
        self.footer_status.addWidget(self.message)
        footer.addWidget(footer_status, 1)
        self.collection_button = QPushButton()
        self.collection_button.setFixedWidth(78)
        self.collection_button.setAccessibleName('보관한 정원 꽃 목록 열기')
        self.collection_button.clicked.connect(self.open_collection_picker)
        footer.addWidget(self.collection_button)
        self.settings_button = QPushButton('설정')
        self.settings_button.setFixedWidth(72)
        self.settings_button.setAccessibleName('설정 열기 또는 이전 화면으로 돌아가기')
        self.settings_button.clicked.connect(self.toggle_settings_page)
        footer.addWidget(self.settings_button)
        root.addLayout(footer)
        self.notify(self.store.notice or welcome, important=bool(self.store.notice))
        self.pages.currentChanged.connect(self._page_changed)
        self._page_changed(POT_PAGE)
        for button, direction in ((self.previous_page, -1), (self.previous_pot, -1),
                                  (self.next_page, 1), (self.next_pot, 1)):
            button.setText('')
            button.setIcon(chevron_icon(direction))
            button.setObjectName('navigationButton')

    def _page_changed(self, index):
        if index != POT_PAGE:
            self._cancel_fertilizer_game()
            self._cancel_mist_game()
            self.close_collection_picker()
        is_settings = index == SETTINGS_PAGE
        if not is_settings:
            self._main_page = index
        self.page_name.setText('설정' if is_settings else MAIN_PAGE_NAMES[index])
        self.previous_page.setEnabled(not is_settings)
        self.next_page.setEnabled(not is_settings)
        self.settings_button.setText('돌아가기' if is_settings else '설정')
        self.collection_button.setVisible(index == POT_PAGE)
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

    def navigate_pot(self, direction):
        count = len(self.garden.pots)
        if count < 2 or self._action_busy or direction not in (-1, 1):
            return False
        target = self.garden.selected + direction
        if not 0 <= target < count:
            return False
        self._cancel_mist_game()

        def select():
            if not self.act(lambda: self.garden.select(target)):
                return False
            self.flower.drops = 0
            self.flower.update()
            return True

        return self.pot_slides.slide_update(select, direction)

    def _build_pot_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        selector = QHBoxLayout()
        selector.setSpacing(4)
        self.previous_pot = QPushButton('‹')
        self.previous_pot.setFixedSize(28, 28)
        self.previous_pot.setAccessibleName('이전 화분')
        self.previous_pot.clicked.connect(lambda: self.navigate_pot(-1))
        selector.addWidget(self.previous_pot)
        self.pot_name = QLabel()
        self.pot_name.setObjectName('potTitle')
        self.pot_name.setAlignment(Qt.AlignCenter)
        self.pot_name.setMinimumWidth(0)
        self.pot_name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        selector.addWidget(self.pot_name, 1)
        self.next_pot = QPushButton('›')
        self.next_pot.setFixedSize(28, 28)
        self.next_pot.setAccessibleName('다음 화분')
        self.next_pot.clicked.connect(lambda: self.navigate_pot(1))
        selector.addWidget(self.next_pot)
        outer.addLayout(selector)

        self.pot_slides = SlideStack()
        self.pot_slides.setMinimumWidth(0)
        self.pot_slides.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        outer.addWidget(self.pot_slides, 1)
        content = QWidget()
        content.setMinimumWidth(0)
        content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.flower = Flower(self.garden)
        layout.addWidget(self.flower)
        controls_scroll = QScrollArea()
        controls_scroll.setMinimumWidth(0)
        controls_scroll.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        controls_scroll.setFrameShape(QFrame.NoFrame)
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        controls = QWidget()
        controls.setMinimumWidth(0)
        controls.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(4)
        self.status = QLabel()
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFixedHeight(18)
        self.status.setMinimumWidth(0)
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        controls_layout.addWidget(self.status)
        row = QHBoxLayout()
        self.water_button = QPushButton('물주기')
        self.water_button.clicked.connect(lambda: self.care('water'))
        row.addWidget(self.water_button)
        self.mist_button = QPushButton('분무')
        self.mist_button.clicked.connect(self.open_mist_game)
        row.addWidget(self.mist_button)
        self.fertilizer_button = QPushButton('비료 -10분')
        self.fertilizer_button.clicked.connect(self.use_fertilizer)
        row.addWidget(self.fertilizer_button)
        controls_layout.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        controls_layout.addWidget(self.progress)
        self.remaining = QLabel()
        self.remaining.setAlignment(Qt.AlignCenter)
        self.remaining.setObjectName('small')
        self.remaining.setFixedHeight(16)
        controls_layout.addWidget(self.remaining)
        self.care_info = QLabel()
        self.care_info.setAlignment(Qt.AlignCenter)
        self.care_info.setObjectName('small')
        self.care_info.setFixedHeight(16)
        controls_layout.addWidget(self.care_info)

        self.species_picker = SeedPicker()
        self.species_picker.selectionChanged.connect(self.refresh)
        controls_layout.addWidget(self.species_picker)
        self.plant_button = self.button(controls_layout, '씨앗 심기', self.plant_selected)

        for button in (self.water_button, self.mist_button, self.fertilizer_button, self.plant_button):
            button.setFixedHeight(32)
        self.harvest_button = self.button(controls_layout, '정원에 보관하기', self.harvest_flower)
        self.harvest_button.setObjectName('primary')
        self.harvest_button.setFixedHeight(32)
        self.fertilizer_tools = QWidget()
        self.fertilizer_tools.setObjectName('fertilizerTools')
        fertilizer_row = QHBoxLayout(self.fertilizer_tools)
        fertilizer_row.setContentsMargins(8, 4, 4, 4)
        self.fertilizer_stock = QLabel()
        self.fertilizer_stock.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        fertilizer_row.addWidget(self.fertilizer_stock, 1)
        self.make_fertilizer_button = QPushButton('비료 만들기')
        self.make_fertilizer_button.clicked.connect(self.open_fertilizer_game)
        self.make_fertilizer_button.setFixedHeight(28)
        fertilizer_row.addWidget(self.make_fertilizer_button)
        controls_layout.addWidget(self.fertilizer_tools)
        controls_layout.addStretch(1)
        controls_scroll.setWidget(controls)
        layout.addWidget(controls_scroll, 1)
        self.pot_slides.addWidget(content)

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
        desktop_row = QHBoxLayout()
        desktop_row.addWidget(QLabel('바탕화면 꽃 불투명도'))
        self.desktop_opacity = QSlider(Qt.Horizontal)
        self.desktop_opacity.setRange(10, 100)
        self.desktop_opacity.setValue(round(self.garden.desktop_opacity * 100))
        self.desktop_opacity.valueChanged.connect(self.set_desktop_opacity)
        desktop_row.addWidget(self.desktop_opacity, 1)
        layout.addLayout(desktop_row)
        desktop_hint = QLabel('정원의 꽃을 우클릭하면 화면 맨 위에 띄웁니다.\n꽃 주변 햇빛을 클릭해 수집 · 꽃을 드래그해 이동')
        desktop_hint.setWordWrap(True)
        desktop_hint.setObjectName('small')
        layout.addWidget(desktop_hint)
        self.button(layout, '바탕화면 꽃 모두 정원으로', self.return_all_desktop)
        cloud_title = QLabel('Google Drive 저장')
        cloud_title.setObjectName('section')
        layout.addWidget(cloud_title)
        self.cloud_status = QLabel()
        self.cloud_status.setObjectName('small')
        self.cloud_status.setWordWrap(True)
        layout.addWidget(self.cloud_status)
        self.cloud_connect_button = QPushButton('Google 계정 연결')
        self.cloud_connect_button.clicked.connect(self.toggle_cloud_connection)
        layout.addWidget(self.cloud_connect_button)
        cloud_row = QHBoxLayout()
        self.cloud_backup_button = QPushButton('지금 백업')
        self.cloud_backup_button.clicked.connect(self.backup_cloud)
        cloud_row.addWidget(self.cloud_backup_button)
        self.cloud_restore_button = QPushButton('클라우드 복원')
        self.cloud_restore_button.clicked.connect(self.restore_cloud)
        cloud_row.addWidget(self.cloud_restore_button)
        layout.addLayout(cloud_row)
        catalog = QLabel(
            '식물 카탈로그\n'
            + '\n'.join(
                f'• {item.name}: {format_duration(item.growth_seconds)} · 씨앗 {item.seed_price}G · 판매 {item.sale_price}G'
                f' (+분무 {item.mist_bonus}G)'
                for item in (PLANTS[key] for key in REGULAR_PLANTS)
            )
            + '\n• 랜덤 씨앗 20G · 고대 0.1% · 고대 꽃 기본 판매 500G'
        )
        catalog.setObjectName('small')
        catalog.setWordWrap(True)
        layout.addWidget(catalog)
        developer_title = QLabel('개발자 도구')
        developer_title.setObjectName('section')
        layout.addWidget(developer_title)
        self.developer_mode = QCheckBox('개발자 모드 · 별도 테스트 정원')
        self.developer_mode.setChecked(self.demo)
        self.developer_mode.toggled.connect(self.set_developer_mode)
        layout.addWidget(self.developer_mode)
        developer_hint = QLabel(
            '켜면 새 테스트 정원 또는 이전 테스트 저장을 엽니다. '
            '끄면 원래 정원으로 돌아갑니다. 꽃·재화는 서로 옮겨지지 않습니다.'
        )
        developer_hint.setObjectName('small')
        developer_hint.setWordWrap(True)
        layout.addWidget(developer_hint)
        self.developer_status = QLabel()
        self.developer_status.setObjectName('small')
        self.developer_status.setWordWrap(True)
        layout.addWidget(self.developer_status)
        self.fast_forward_button = QPushButton('시간 +6시간')
        self.fast_forward_button.setToolTip('테스트 정원의 모든 화분과 대기시간을 진행합니다. 비료를 자동 지급하지 않습니다.')
        self.fast_forward_button.clicked.connect(self.fast_forward)
        layout.addWidget(self.fast_forward_button)
        layout.addStretch()
        self.pages.addWidget(page)
        self._sync_cloud_controls()

    def _cloud_state_path(self):
        path = getattr(self.store, 'path', None)
        return path.with_suffix('.cloud-sync.json') if path is not None else None

    def _cloud_account_key(self):
        email = (self.cloud.email if self.cloud and self.cloud.connected else '').strip().casefold()
        return hashlib.sha256(email.encode('utf-8')).hexdigest() if email else ''

    def _reset_cloud_state(self):
        self._cloud_last_uploaded_digest = None
        self._cloud_known_saved_at = None
        self._cloud_last_backup_at = None
        self._cloud_auto_error = False

    def _load_cloud_state(self):
        self._reset_cloud_state()
        path, account = self._cloud_state_path(), self._cloud_account_key()
        if self.demo or path is None or not account or not path.is_file():
            return
        try:
            state = json.loads(path.read_text(encoding='utf-8'))
            if (
                not isinstance(state, dict)
                or set(state) != {'schema', 'account', 'saved_at', 'digest'}
                or state['schema'] != 1
                or state['account'] != account
                or type(state['saved_at']) not in (int, float)
                or not math.isfinite(state['saved_at'])
                or not isinstance(state['digest'], str)
                or len(state['digest']) != 64
            ):
                return
            self._cloud_known_saved_at = state['saved_at']
            self._cloud_last_backup_at = state['saved_at']
            self._cloud_last_uploaded_digest = state['digest']
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return

    def _save_cloud_state(self):
        path, account = self._cloud_state_path(), self._cloud_account_key()
        if (
            self.demo or path is None or not account
            or self._cloud_known_saved_at is None or self._cloud_last_uploaded_digest is None
        ):
            return False
        temporary = path.with_suffix(path.suffix + '.tmp')
        state = {
            'schema': 1,
            'account': account,
            'saved_at': self._cloud_known_saved_at,
            'digest': self._cloud_last_uploaded_digest,
        }
        try:
            temporary.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
            temporary.replace(path)
            return True
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            return False

    def _sync_cloud_controls(self):
        configured = bool(self.cloud and self.cloud.configured)
        connected = configured and self.cloud.connected
        active = connected and not self.demo and not self._cloud_busy
        if not configured:
            status = 'Google OAuth 클라이언트 설정이 필요합니다.'
        elif connected:
            status = '연결됨 · ' + (self.cloud.email or 'Google 계정')
            if self.demo:
                status += ' · 테스트 정원은 동기화하지 않음'
            else:
                status += ' · 5분마다 자동 백업'
                if self._cloud_auto_error:
                    status += ' · 다음 주기에 재시도'
                elif self._cloud_last_backup_at:
                    status += ' · 최근 ' + time.strftime('%H:%M', time.localtime(self._cloud_last_backup_at))
        else:
            status = '연결하면 일반 정원을 비공개 앱 데이터에 저장합니다.'
        self.cloud_status.setText(status)
        self.cloud_connect_button.setText('연결 해제' if connected else 'Google 계정 연결')
        self.cloud_connect_button.setEnabled(configured and not self._cloud_busy)
        self.cloud_backup_button.setEnabled(active)
        self.cloud_restore_button.setEnabled(active)

    def _run_cloud(self, action, done, message, silent_error=False):
        if not self.cloud or self._cloud_busy:
            return False
        self._cloud_busy = True
        self._cloud_done = done
        self._cloud_silent_error = silent_error
        self._cloud_future = Future()

        def work():
            try:
                self._cloud_future.set_result(action())
            except BaseException as exc:
                self._cloud_future.set_exception(exc)

        Thread(target=work, name='MorningBloomCloud', daemon=True).start()
        self._sync_cloud_controls()
        if message:
            self.notify(message)
        self.cloud_poll.start()
        return True

    def _poll_cloud(self):
        if not self._cloud_future or not self._cloud_future.done():
            return
        self.cloud_poll.stop()
        future, done = self._cloud_future, self._cloud_done
        silent_error = self._cloud_silent_error
        self._cloud_future = self._cloud_done = None
        self._cloud_busy = False
        self._cloud_silent_error = False
        self._sync_cloud_controls()
        try:
            result = future.result()
        except (CloudError, OSError, ValueError) as exc:
            if silent_error:
                self._cloud_auto_error = True
                self._sync_cloud_controls()
            else:
                self.notify('Google Drive 실패 · ' + str(exc), important=True)
            return
        done(result)

    def toggle_cloud_connection(self):
        if not self.cloud:
            return False
        if self.cloud.connected:
            return self._run_cloud(
                self.cloud.disconnect,
                self._after_cloud_disconnect,
                'Google 연결을 해제하는 중…',
            )
        return self._run_cloud(self.cloud.connect, self._after_cloud_connect, '브라우저에서 Google 로그인을 완료하세요.')

    def _after_cloud_disconnect(self, _result):
        self._reset_cloud_state()
        self._sync_cloud_controls()
        self.notify('Google 계정 연결을 해제했습니다.', important=True)

    def _after_cloud_connect(self, _email):
        self._load_cloud_state()
        self._sync_cloud_controls()
        self.notify('Google 계정이 연결되었습니다.', important=True)
        self.check_cloud()

    def check_cloud(self):
        if not self.cloud or not self.cloud.connected or self.demo or self._cloud_busy:
            return False
        return self._run_cloud(
            self.cloud.download_save,
            lambda envelope: self._consider_cloud_save(envelope, manual=False),
            '클라우드 저장을 확인하는 중…',
        )

    @staticmethod
    def _cloud_digest(snapshot):
        payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
        return hashlib.sha256(payload).hexdigest()

    def auto_backup_cloud(self):
        """Upload changed local data every five minutes without overwriting a newer cloud save."""
        if not self.cloud or not self.cloud.connected or self.demo or self._cloud_busy:
            return False
        if not self.persist():
            return False
        return self._run_cloud(
            self.cloud.download_save,
            self._finish_auto_backup_check,
            '',
            silent_error=True,
        )

    def _finish_auto_backup_check(self, envelope):
        self._cloud_auto_error = False
        self._sync_cloud_controls()
        self._consider_cloud_save(envelope, manual=False, quiet=True)

    def backup_cloud(self, _checked=False, silent=False):
        if not self.cloud or not self.cloud.connected or self.demo or self._cloud_busy:
            return False
        if not self.persist():
            return False
        snapshot = self.garden.to_dict()
        digest = self._cloud_digest(snapshot)
        return self._run_cloud(
            lambda: self.cloud.upload_save(snapshot),
            lambda saved_at: self._after_cloud_backup(saved_at, digest, silent),
            '' if silent else 'Google Drive에 백업하는 중…',
            silent_error=silent,
        )

    def _after_cloud_backup(self, saved_at, digest, silent):
        self._cloud_last_uploaded_digest = digest
        self._cloud_known_saved_at = saved_at
        self._cloud_last_backup_at = saved_at
        self._cloud_auto_error = False
        self._save_cloud_state()
        self._sync_cloud_controls()
        if not silent:
            self.notify('Google Drive 백업 완료', important=True)

    def restore_cloud(self):
        if not self.cloud or not self.cloud.connected or self.demo or self._cloud_busy:
            return False
        return self._run_cloud(
            self.cloud.download_save,
            lambda envelope: self._consider_cloud_save(envelope, manual=True),
            '클라우드 저장을 불러오는 중…',
        )

    def _consider_cloud_save(self, envelope, manual, quiet=False):
        if envelope is None:
            if manual:
                self.notify('Google Drive에 저장된 정원이 없습니다.', important=True)
            else:
                self.backup_cloud(silent=True)
            return
        local_digest = self._cloud_digest(self.garden.to_dict())
        cloud_digest = self._cloud_digest(envelope['save'])
        if not manual:
            if cloud_digest == local_digest:
                remote_changed = local_changed = False
            elif self._cloud_last_uploaded_digest is None:
                remote_changed = cloud_digest != local_digest
                local_changed = False
            else:
                remote_changed = cloud_digest != self._cloud_last_uploaded_digest
                local_changed = local_digest != self._cloud_last_uploaded_digest
            if not remote_changed:
                if local_changed:
                    self.backup_cloud(silent=True)
                else:
                    self._cloud_last_uploaded_digest = local_digest
                    self._cloud_known_saved_at = envelope['saved_at']
                    self._cloud_last_backup_at = envelope['saved_at']
                    self._cloud_auto_error = False
                    self._save_cloud_state()
                    self._sync_cloud_controls()
                    if not quiet:
                        self.notify('Google Drive와 동기화되었습니다.')
                return
        if self.isMinimized():
            self._pending_cloud_prompt = (envelope, manual)
            self.notify('Google Drive 저장을 확인하려면 창을 복원하세요.', important=True)
            return
        answer = QMessageBox.question(
            self,
            '클라우드 저장 복원',
            'Google Drive의 정원으로 현재 정원을 교체할까요?\n'
            '현재 저장은 복원 전 백업으로 보존합니다.\n'
            '아니요를 선택하면 로컬 정원을 Google Drive에 백업합니다.',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self._apply_cloud_save(envelope)
        else:
            self.notify('로컬 정원을 유지했습니다. Google Drive에 자동 백업합니다.', important=True)
            self.backup_cloud(silent=True)

    def _apply_cloud_save(self, envelope):
        try:
            restored = self.store.replace_from_cloud(envelope['save'], self.now())
            self.close_collection_picker()
            self.desktop.close()
            self.garden.restore(restored.to_dict())
            self._local_saved_at = self.store.path.stat().st_mtime
            self._cloud_last_uploaded_digest = self._cloud_digest(self.garden.to_dict())
            self._cloud_known_saved_at = envelope['saved_at']
            self._cloud_last_backup_at = envelope['saved_at']
            self._cloud_auto_error = False
            self._save_cloud_state()
            self._apply_session_settings()
            self.refresh()
            self.notify('Google Drive 저장을 복원했습니다.', important=True)
            return True
        except (SaveError, ValueError, OSError) as exc:
            self.notify('클라우드 복원 실패 · ' + str(exc), important=True)
            return False

    def _build_shop_page(self):
        page, layout = self._scrollable_page()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.shop_wallet = QLabel()
        self.shop_wallet.setObjectName('small')
        layout.addWidget(self.shop_wallet)
        seed_title = QLabel('재배 상점 · 골드')
        seed_title.setObjectName('section')
        layout.addWidget(seed_title)
        self.shop_picker = SeedPicker(shop=True)
        layout.addWidget(self.shop_picker)
        self.shop_info = QLabel()
        self.shop_info.setObjectName('small')
        self.shop_info.setWordWrap(True)
        self.shop_info.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(self.shop_info)
        self.buy_seed_button = self.button(layout, '씨앗 구매', lambda: self.garden.buy_seed(self.shop_picker.selected))
        layout.addWidget(QLabel('화분 확장 · 씨앗은 별도 구매'))
        self.buy_pot_button = self.button(layout, '두 번째 화분 구매 · 150G', self.garden.buy_pot)
        theme_title = QLabel('정원 배경 · 햇빛')
        theme_title.setObjectName('section')
        layout.addWidget(theme_title)
        self.theme_picker = IconPicker((theme.key, theme.label, theme_icon(theme)) for theme in THEMES.values())
        self.theme_picker.buttons[self.garden.equipped_theme].setChecked(True)
        layout.addWidget(self.theme_picker)
        self.theme_info = QLabel()
        self.theme_info.setObjectName('small')
        self.theme_info.setWordWrap(True)
        layout.addWidget(self.theme_info)
        theme_row = QHBoxLayout()
        self.buy_theme_button = self.button(theme_row, '배경 구매', self.buy_selected_theme)
        self.apply_theme_button = self.button(theme_row, '배경 적용', self.apply_selected_theme)
        layout.addLayout(theme_row)
        skin_title = QLabel('화분 스킨 · 햇빛')
        skin_title.setObjectName('section')
        layout.addWidget(skin_title)
        skin_scope = QLabel('한 번 구매하면 재배·정원의 모든 화분에 계속 사용할 수 있어요.')
        skin_scope.setObjectName('small')
        skin_scope.setWordWrap(True)
        layout.addWidget(skin_scope)
        self.skin_picker = IconPicker((skin.key, skin.label, skin_icon(skin)) for skin in POT_SKINS.values())
        self.skin_picker.buttons[self.garden.equipped_skin].setChecked(True)
        layout.addWidget(self.skin_picker)
        self.skin_info = QLabel()
        self.skin_info.setObjectName('small')
        self.skin_info.setWordWrap(True)
        layout.addWidget(self.skin_info)
        skin_row = QHBoxLayout()
        self.buy_skin_button = self.button(skin_row, '스킨 구매', self.buy_selected_skin)
        self.apply_skin_button = self.button(skin_row, '스킨 적용', self.apply_selected_skin)
        layout.addLayout(skin_row)
        layout.addStretch()
        self.pages.addWidget(page)
        self.shop_picker.selectionChanged.connect(self.refresh)
        self.theme_picker.selectionChanged.connect(self.refresh)
        self.skin_picker.selectionChanged.connect(self.refresh)

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
        if self.act(lambda: self.garden.sell(item_id, self.now())):
            self.notify(f'{name} 판매 +{price}G', important=True)
            return True
        return False

    def collect_sun(self, token_id):
        if self.act(lambda: self.garden.collect_sun(token_id, self.now())):
            self.notify('햇빛 수집 +1 · 꾸미기 상점에서 사용할 수 있어요.', important=True)
            return True
        return False

    def buy_selected_theme(self):
        theme = garden_theme(self.theme_picker.selected)
        if not self.garden.buy_theme(theme.key):
            return False
        self.notify(f'{theme.name} 구매 · 햇빛 {theme.price} 사용', important=True)
        return True

    def apply_selected_theme(self):
        theme = garden_theme(self.theme_picker.selected)
        if not self.garden.equip_theme(theme.key):
            return False
        self.notify(f'{theme.name}을 정원에 적용했어요.', important=True)
        return True

    def buy_selected_skin(self):
        skin = pot_skin(self.skin_picker.selected)
        if not self.garden.buy_skin(skin.key):
            return False
        self.notify(f'{skin.name} 구매 · 햇빛 {skin.price} 사용', important=True)
        return True

    def apply_selected_skin(self):
        skin = pot_skin(self.skin_picker.selected)
        if not self.garden.equip_skin(skin.key):
            return False
        self.notify(f'{skin.name}을 모든 화분에 적용했어요.', important=True)
        return True

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
        self._message_text = text
        self.message.setText(text.replace('\n', ' '))
        self.message.setToolTip(text)
        self.footer_status.setCurrentWidget(self.message if text else self.inventory)

    def open_collection_picker(self):
        if self.pages.currentIndex() != POT_PAGE:
            return
        if self._collection_picker is None:
            self._collection_picker = CollectionPicker(
                self,
                self.garden,
                self.set_desktop_flower,
                lambda: set(self.desktop.windows),
            )
        self._collection_picker.sync(force=True)
        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            picker = self._collection_picker
            x = self.x() - picker.width() - 8
            if x < area.left():
                x = self.x() + self.width() + 8
            x = max(area.left(), min(x, area.right() - picker.width() + 1))
            y = max(area.top(), min(self.y(), area.bottom() - picker.height() + 1))
            picker.move(x, y)
        self._collection_picker.show()
        self._collection_picker.raise_()
        self._collection_picker.activateWindow()

    def close_collection_picker(self):
        if self._collection_picker is not None:
            self._collection_picker.hide()

    def set_desktop_flower(self, item_id, floating):
        if floating:
            return self.desktop.ensure_floating(item_id)
        return self.desktop.return_to_garden(item_id)

    def toggle_desktop_flower(self, item_id):
        return self.set_desktop_flower(item_id, item_id not in self.garden.desktop_flowers)

    def act(self, callback):
        if self._action_busy:
            return False
        self._action_busy = True
        before = self.garden.to_dict()
        before_offset = self.offset
        try:
            result = callback()
            if result is False:
                self.notify('지금은 할 수 없는 행동이에요.', important=True)
                self.refresh()
                return False
            if not self.persist():
                error = self._message_text
                self.offset = before_offset
                self.garden.restore(before)
                self.refresh()
                self.notify(error + ' · 행동을 되돌렸습니다.', important=True)
                return False
            self.refresh()
            return True
        finally:
            self._action_busy = False

    def plant_selected(self):
        return self.garden.plant(self.now(), self.species_picker.selected)

    def care(self, kind):
        previous_status = self.garden.water_status
        first_mist = not self.garden.pot['misted']
        done = self.act(lambda: self.garden.care(kind, self.now()))
        if done:
            self.flower.drops = 30
            if self.garden.pot['ruleset_id'] == TYCOON_RULE and previous_status != 'initial':
                effect = 3 if kind == 'water' else 1
                bonus = f' · 판매 +{self.garden.pot["mist_bonus_g"]}G' if kind == 'mist' and first_mist and not self.garden.mystery_hidden else ''
                self.notify(f'돌봄 완료 · 성장 -{effect}분' + bonus)
            elif kind == 'mist':
                self.notify(f'분무 완료 · 수확한 꽃의 판매가에 {self.garden.pot["mist_bonus_g"]}G가 더해져요.')
            elif previous_status == 'initial':
                self.notify('첫 물주기 완료 · 지금부터 성장 시간이 흐릅니다.')
            elif previous_status == 'slow':
                self.notify('물주기 완료 · 지금부터 원래 속도로 자랍니다.')
            else:
                self.notify('물주기 완료 · 성장 속도는 그대로 유지됩니다.')
        return done

    def _cancel_mist_game(self):
        if self._mist_game is not None:
            self._mist_game.reject()

    def open_mist_game(self):
        if self._mist_game is not None:
            self._mist_game.raise_()
            return
        self.garden.advance(self.now())
        if not self.garden.can_care('mist'):
            return
        self._cancel_fertilizer_game()
        game = MistGame(self, self.garden)
        self._mist_game = game
        store, plant_id = self.store, self.garden.pot['plant_id']

        def complete():
            if (self._mist_game is not game or self.store is not store
                    or self.garden.pot['plant_id'] != plant_id):
                return
            if self.care('mist'):
                game.result.setText('분무 효과를 적용했어요!')
            else:
                game.result.setText('분무를 적용하지 못했어요. ' + self.message.text())

        game.completed.connect(complete)
        game.finished.connect(lambda _: setattr(self, '_mist_game', None))
        game.open()
        game.raise_()
        game.activateWindow()

    def set_desktop_opacity(self, value):
        self.act(lambda: self.garden.set_desktop_opacity(value / 100))

    def return_all_desktop(self):
        self.garden.desktop_flowers.clear()
        return True

    def use_fertilizer(self):
        if not self.act(lambda: self.garden.use_fertilizer(self.now())):
            return False
        self.flower.drops = 30
        self.notify('비료 1개 사용 · ' + ('즉시 개화!' if self.garden.bloomed else '성장 -10분'), important=True)
        return True

    def _cancel_fertilizer_game(self):
        if self._fertilizer_game is not None:
            self._fertilizer_game.reject()

    def open_fertilizer_game(self):
        self._cancel_mist_game()
        if not self.garden.tutorial_reward_claimed:
            self.notify('첫 꽃을 정원에 보관하면 비료 만들기가 열려요.', important=True)
            return
        if self._fertilizer_game is not None:
            self._fertilizer_game.raise_()
            return
        self.garden.advance(self.now())
        if self.garden.vacation:
            hint = '휴가 중에는 연습만 할 수 있어요.'
        elif self.garden.fertilizer >= FERTILIZER_CAP:
            hint = '비료가 가득 찼어요. 사용한 뒤 실전에 도전하세요.'
        elif self.garden.reward_wait > 0:
            hint = '다음 보상까지 ' + format_duration(self.garden.reward_wait)
        else:
            hint = '성공 보상 뒤 3분 후에 다시 비료를 받을 수 있어요.'
        game = FertilizerGame(self, self.garden.can_reward_fertilizer, hint)
        self._fertilizer_game = game
        store, demo = self.store, self.demo

        def complete(game_id, success, rewarded):
            if self._fertilizer_game is not game or self.store is not store or self.demo != demo:
                return
            if not success or not rewarded:
                if success:
                    game.result.setText('연습 성공 · 보상은 없어요.')
                return
            if self.act(lambda: self.garden.reward_fertilizer(game_id, self.now())):
                game.result.setText('성공 · 비료 +1! 다음 보상은 3분 뒤에 열려요.')
                self.notify('비료 만들기 성공 · 비료 +1', important=True)
            else:
                game.result.setText('비료를 받지 못했어요. ' + self.message.text())

        game.completed.connect(complete)
        game.finished.connect(lambda result: setattr(self, '_fertilizer_game', None))
        game.open()
        game.raise_()
        game.activateWindow()
        game.start_button.setFocus(Qt.OtherFocusReason)

    def fast_forward(self):
        if not self.demo or self._action_busy:
            return False

        def advance_clock():
            self.offset += 6 * 3600

        if not self.act(advance_clock):
            return False
        message = '테스트 정원만 6시간 이동했습니다.'
        if self.garden.vacation:
            message += ' 휴가 중이라 성장·돌봄은 정지합니다.'
        self.notify(message, important=True)
        return True

    def _sync_developer_controls(self):
        self.developer_mode.blockSignals(True)
        self.developer_mode.setChecked(self.demo)
        self.developer_mode.blockSignals(False)
        self.fast_forward_button.setEnabled(self.demo)
        title = '개발자 · 테스트 정원' if self.demo else '아침 한 송이'
        self.title.setText(title)
        self.setWindowTitle(title)
        self.developer_status.setText(
            f'테스트 저장 · 실제 시각보다 {format_duration(self.offset)} 앞섬'
            if self.demo else '일반 정원 · 시간 이동 잠김'
        )
        self._sync_cloud_controls()

    def set_developer_mode(self, enabled):
        """Switch locked save files, retaining the Garden object used by every view."""
        if enabled == self.demo or self._action_busy or self._cloud_busy:
            if self._cloud_busy:
                self.notify('Google Drive 작업이 끝난 뒤 전환하세요.', important=True)
            self._sync_developer_controls()
            return enabled == self.demo
        self._cancel_fertilizer_game()
        self._cancel_mist_game()
        self.close_collection_picker()
        self._action_busy = True
        target_lock = None
        try:
            path = getattr(self.store, 'path', None)
            if path is None:
                raise SaveError('전환할 저장 위치를 찾을 수 없습니다.')
            name = 'demo-garden' if enabled else 'garden'
            target_path = path.with_name(name + '.json')
            if target_path == path:
                raise SaveError('일반 정원과 테스트 정원은 서로 다른 파일이어야 합니다.')
            target_lock = QLockFile(str(target_path.with_suffix('.lock')))
            if not target_lock.tryLock(0):
                raise SaveError('전환할 정원이 이미 열려 있거나 저장 잠금을 얻을 수 없습니다.')
            target_store = Store(target_path)
            target_garden = target_store.load(time.time())
            if not self.persist():
                return False
            # Verify the destination is writable before replacing the active session.
            target_store.save(target_garden)
            self.desktop.close()
            self.garden.restore(target_garden.to_dict())
            self.store, self.demo = target_store, enabled
            self._local_saved_at = target_store.path.stat().st_mtime
            self._load_cloud_state()
            self.offset = max(0, target_garden.last_update - time.time()) if enabled else 0
            previous_lock = self._save_lock
            self._save_lock, target_lock = target_lock, None
            if previous_lock is not None:
                previous_lock.unlock()
            self._apply_session_settings()
            self.refresh()
            message = (
                '개발자 모드 · 별도 테스트 정원입니다.' if enabled
                else '일반 정원으로 돌아왔습니다. 테스트 시간과 재화는 옮겨지지 않습니다.'
            )
            if target_store.notice:
                message += ' ' + target_store.notice
            self.notify(message, important=True)
            return True
        except (SaveError, ValueError, OSError) as exc:
            self.notify('정원 전환 실패 · ' + str(exc), important=True)
            return False
        finally:
            if target_lock is not None:
                target_lock.unlock()
            self._action_busy = False
            self._sync_developer_controls()

    def _apply_session_settings(self):
        settings = self.garden.settings
        self.topmost.blockSignals(True)
        self.topmost.setChecked(settings['topmost'])
        self.topmost.blockSignals(False)
        self.opacity.blockSignals(True)
        self.opacity.setValue(round(settings['opacity'] * 100))
        self.opacity.blockSignals(False)
        self.desktop_opacity.blockSignals(True)
        self.desktop_opacity.setValue(round(self.garden.desktop_opacity * 100))
        self.desktop_opacity.blockSignals(False)
        position, visible, minimized = self.pos(), self.isVisible(), self.isMinimized()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, settings['topmost'])
        self.move(position)
        self.setWindowOpacity(settings['opacity'])
        if visible:
            self.showMinimized() if minimized else self.show()

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
        if self._fertilizer_game is not None:
            self._fertilizer_game.setWindowOpacity(self.windowOpacity())
        if self._mist_game is not None:
            self._mist_game.setWindowOpacity(self.windowOpacity())

    def refresh(self):
        garden = self.garden
        self._sync_developer_controls()
        garden.advance(self.now())
        counts = {'첫 물': 0, '물': 0, '분무': 0, '개화': 0}
        for pot in garden.pots:
            water = garden.care_status('water', pot)
            counts['첫 물'] += int(water == 'initial')
            counts['물'] += int(water in ('ready', 'early', 'due', 'slow'))
            counts['분무'] += int(garden.care_status('mist', pot) == 'ready')
            counts['개화'] += int(pot['planted'] and pot['growth'] >= pot['duration'])
        ready = ' · '.join(f'{name} {count}' for name, count in counts.items() if count)
        summary = '돌봄 준비 · ' + ready if ready else '지금 필요한 돌봄 없음'
        status = summary if len(garden.pots) > 1 and not garden.vacation else garden.health
        self.status.setToolTip(summary + '\n' + garden.health)
        self.status.setText(self.status.fontMetrics().elidedText(status, Qt.ElideRight, max(0, self.width() - 24)))
        self.progress.setValue(int(garden.ratio * 100))
        stage = ('씨앗', '새싹', '자라는 중', '봉오리', '개화')[garden.stage]
        if garden.planted:
            remaining = format_duration(garden.remaining_seconds())
            self.remaining.setText('꽃이 활짝 피었어요' if garden.bloomed else
                                   '첫 물을 주면 성장이 시작돼요' if not garden.pot['initial_watered'] else
                                   f'{stage} · 개화까지 {remaining}')
            self.care_info.setText(self._care_text())
            if garden.mystery_hidden:
                self.remaining.setText(f'{stage} · 어떤 꽃일까요? 외관을 관찰해 보세요')
        else:
            self.remaining.setText('빈 화분 · 키울 식물을 선택하세요')
            self.care_info.setText('모든 꽃은 심은 뒤 첫 물주기를 해야 성장해요')

        selected = self.species_picker.selected
        count = garden.seed_count(selected)
        self.plant_button.setText(
            ('랜덤 씨앗 심기 · 정체는 개화 후 공개' if selected == 'random' else
             f'{PLANTS[selected].name} 심기 · {format_duration(PLANTS[selected].growth_seconds)}')
            if count else '씨앗 없음 · 상점에서 구매'
        )
        self.plant_button.setEnabled(garden.can_plant(selected))
        self.species_picker.setEnabled(not garden.planted and not garden.vacation)
        self.species_picker.setVisible(not garden.planted)
        self.plant_button.setVisible(not garden.planted)
        self.flower.setVisible(garden.planted)
        self.progress.setVisible(garden.planted and not garden.mystery_hidden)
        self.remaining.setVisible(garden.planted)
        caring = garden.planted and not garden.bloomed
        self.care_info.setVisible(garden.planted and not (caring and garden.pot['initial_watered']
                                      and garden.pot['ruleset_id'] == TYCOON_RULE
                                      and not garden.pot['is_tutorial']))
        self.remaining.setToolTip(self.care_info.text())
        self.water_button.setVisible(caring)
        self.mist_button.setVisible(caring and garden.pot['initial_watered'] and not garden.pot['is_tutorial'])
        self.fertilizer_button.setVisible(caring and garden.pot['initial_watered'] and garden.tutorial_reward_claimed)
        self.harvest_button.setVisible(garden.bloomed)
        visible_seeds = {**garden.seeds, 'random': len(garden.mystery_seeds)}
        self.species_picker.update_counts(visible_seeds)
        self.shop_picker.update_counts(visible_seeds)
        self.vacation.blockSignals(True)
        self.vacation.setChecked(garden.vacation)
        self.vacation.blockSignals(False)
        water_status = garden.water_status
        water_labels = {
            'initial': '첫 물주기', 'early': '미리 물주기',
            'due': '물주기 권장', 'slow': '회복 물주기',
        }
        self.water_button.setText(water_labels.get(water_status, '물주기 완료'))
        self.water_button.setEnabled(garden.can_care('water'))
        mist_bonus = garden.pot['mist_bonus_g'] if garden.planted else 0
        self.mist_button.setText('분무 완료' if garden.planted and garden.pot['misted'] else f'분무 +{mist_bonus}G')
        self.mist_button.setEnabled(garden.can_care('mist'))
        if garden.mystery_hidden:
            self.mist_button.setText('분무 미니게임')
        if garden.planted and garden.pot['ruleset_id'] == TYCOON_RULE and not garden.pot['is_tutorial']:
            for kind, button, minutes in (('water', self.water_button, 3), ('mist', self.mist_button, 1)):
                state = garden.care_status(kind)
                wait = garden.pot[kind + '_wait']
                label = '물' if kind == 'water' else '분무'
                if state == 'ready':
                    button.setText(f'{label} -{minutes}분')
                elif state == 'waiting':
                    button.setText(f'{label} {math.ceil(wait) // 60:02}:{math.ceil(wait) % 60:02}')
                elif state == 'unavailable':
                    button.setText(label)
        self.fertilizer_tools.setVisible(garden.tutorial_reward_claimed)
        if garden.reward_wait > 0:
            wait = math.ceil(garden.reward_wait)
            reward_status = f'{wait // 60}:{wait % 60:02}'
        elif garden.vacation:
            reward_status = '휴가 중'
        elif garden.fertilizer >= FERTILIZER_CAP:
            reward_status = '가득 참'
        else:
            reward_status = '보상 가능'
        self.fertilizer_stock.setText(
            f'비료{garden.fertilizer}/{FERTILIZER_CAP} {reward_status}'
        )
        self.fertilizer_stock.setToolTip(f'이전 버전 예비 비료 {garden.fertilizer_reserve}개 · 사용 시 자동 보충')
        self.fertilizer_button.setEnabled(garden.can_use_fertilizer)
        remaining = garden.remaining_seconds()
        if garden.can_use_fertilizer:
            result = max(0.0, remaining - FERTILIZER_SECONDS)
            preview = ('즉시 개화 · 비료 1개 사용' if result == 0 else
                       f'{format_duration(remaining)} → {format_duration(result)}')
        elif garden.planted and garden.pot['ruleset_id'] != TYCOON_RULE:
            preview = '이번 꽃은 기존 규칙 · 다음 재배부터 비료 사용 가능'
        elif garden.planted and garden.pot['fertilizer_used'] >= garden.pot['fertilizer_limit']:
            preview = '이 꽃의 비료 사용 상한에 도달했어요.'
        else:
            preview = '첫 물주기 후 성장 중인 꽃에 비료를 사용할 수 있어요.'
        self.fertilizer_button.setToolTip(
            f'비료 {garden.fertilizer}/{FERTILIZER_CAP} · 사용 {garden.pot["fertilizer_used"]}/'
            f'{garden.pot["fertilizer_limit"]}\n' + preview
        )
        if garden.mystery_hidden:
            self.fertilizer_button.setToolTip('비료 1개로 성장 10분 단축 · 개화 후 식물 이름 공개')
        self.make_fertilizer_button.setText('비료 만들기' if garden.can_reward_fertilizer else '연습 · 보상 없음')
        self.make_fertilizer_button.setToolTip(
            '3번 중 2번 성공하면 비료 1개' if garden.can_reward_fertilizer else
            '휴가 중에는 연습만 가능해요' if garden.vacation else
            '비료를 사용하면 보상을 받을 수 있어요' if garden.fertilizer >= FERTILIZER_CAP else
            '다음 보상까지 ' + format_duration(garden.reward_wait)
        )
        self.harvest_button.setEnabled(garden.bloomed)

        seed_total = sum(garden.seeds.values()) + len(garden.mystery_seeds)
        self.inventory.setText(
            f'{garden.coins}G · 햇빛 {garden.sunlight} · 씨앗 {seed_total} · 꽃 {len(garden.collection)}'
        )
        seeds = ' / '.join(f'{PLANTS[key].name} {garden.seed_count(key)}' for key in REGULAR_PLANTS)
        seeds += f' / 랜덤 {len(garden.mystery_seeds)}'
        self.inventory.setToolTip(f'씨앗 {seeds} · 보관 꽃 {len(garden.collection)}')
        self.collection_button.setText(f'정원 꽃 {len(garden.collection)}')
        if self._collection_picker is not None and self._collection_picker.isVisible():
            self._collection_picker.sync()
        count = len(garden.pots)
        name = garden.display_name if garden.planted else '빈 화분'
        self.pot_name.setText(f'화분 {garden.selected + 1} / {count} · {name}')
        self.pot_name.setToolTip(self.pot_name.text() + ' · ' + self._pot_state(garden.pot))
        for button, direction in ((self.previous_pot, -1), (self.next_pot, 1)):
            target = garden.selected + direction
            button.setEnabled(0 <= target < count)
            button.setToolTip(
                '상점에서 화분을 추가하면 넘길 수 있어요' if count == 1 else
                f'화분 {target + 1}로 이동' if 0 <= target < count else
                '첫 화분이에요' if direction < 0 else '마지막 화분이에요'
            )
        self.shop_wallet.setText(
            f'보유 {garden.coins}G · 햇빛 {garden.sunlight} · 화분 {len(garden.pots)}/{len(POT_PRICES)}개'
        )
        species = self.shop_picker.selected
        item = plant_definition('daisy' if species == 'random' else species)
        self.shop_info.setText(
            f'성장 {format_duration(item.growth_seconds)} · 판매 {item.sale_price}G\n'
            f'첫 물 이후 성장 · 분무 판매 +{item.mist_bonus}G'
        )
        self.shop_info.setToolTip(item.shop_tag + '\n첫 물 후 성장 · 반복 돌봄은 선택')
        self.buy_seed_button.setText(f'{item.name} 씨앗 구매 · {item.seed_price}G')
        self.buy_seed_button.setEnabled(garden.coins >= item.seed_price)
        if species == 'random':
            self.shop_info.setText('외관으로 정체를 추측해 보세요 · 개화 후 이름 공개\n고대 0.1% · 일반 3종 각 33.3% · 고대 꽃 기본 500G')
            self.shop_info.setToolTip('구매할 때 결과가 결정·저장됩니다. 고대 꽃 분무 시 550G')
            self.buy_seed_button.setText(f'랜덤 씨앗 구매 · {RANDOM_SEED_PRICE}G')
            self.buy_seed_button.setEnabled(garden.coins >= RANDOM_SEED_PRICE)
        price = garden.next_pot_price
        self.buy_pot_button.setEnabled(price is not None and garden.coins >= price)
        self.buy_pot_button.setText('화분 4개 보유 중' if price is None else f'{len(garden.pots) + 1}번 화분 구매 · {price}G')
        if price is not None:
            after = garden.coins - price
            warning = ' · 다음 씨앗을 살 골드가 부족해요' if not sum(garden.seeds.values()) and after < 8 else ''
            self.buy_pot_button.setToolTip(f'부족 {max(0, price - garden.coins)}G · 구매 후 {after}G' + warning)
        for picker, catalog, owned, equipped in (
            (self.theme_picker, THEMES, garden.owned_themes, garden.equipped_theme),
            (self.skin_picker, POT_SKINS, garden.owned_skins, garden.equipped_skin),
        ):
            for key, button in picker.buttons.items():
                item = catalog[key]
                state = '사용 중' if key == equipped else ('보유' if key in owned else f'햇빛 {item.price}')
                button.setText(f'{item.label}\n{state}')
                button.setAccessibleName(f'{item.name} · {state}')
                button.setToolTip(f'{item.name} · {state}\n{item.description}')
        theme = garden_theme(self.theme_picker.selected)
        owned = theme.key in garden.owned_themes
        equipped = theme.key == garden.equipped_theme
        state = '사용 중' if equipped else ('소유 중' if owned else f'가격 햇빛 {theme.price}')
        self.theme_info.setText(f'{theme.description} · {state}')
        self.buy_theme_button.setText('보유한 배경' if owned else f'구매 · 햇빛 {theme.price}')
        self.buy_theme_button.setEnabled(not owned and garden.sunlight >= theme.price)
        self.apply_theme_button.setText('사용 중' if equipped else '정원에 적용')
        self.apply_theme_button.setEnabled(owned and not equipped)
        skin = pot_skin(self.skin_picker.selected)
        owned = skin.key in garden.owned_skins
        equipped = skin.key == garden.equipped_skin
        self.skin_info.setText(skin.description)
        self.buy_skin_button.setText('보유한 스킨' if owned else f'구매 · 햇빛 {skin.price}')
        self.buy_skin_button.setEnabled(not owned and garden.sunlight >= skin.price)
        self.buy_skin_button.setToolTip(f'보유 햇빛 {garden.sunlight} · 부족 {max(0, skin.price - garden.sunlight)}')
        self.apply_skin_button.setText('사용 중' if equipped else '모든 화분에 적용')
        self.apply_skin_button.setEnabled(owned and not equipped)
        self.desktop_opacity.blockSignals(True)
        self.desktop_opacity.setValue(round(garden.desktop_opacity * 100))
        self.desktop_opacity.blockSignals(False)
        self.desktop.sync()
        self.collection_garden.meadow.desktop_ids = set(self.desktop.windows)
        self.collection_garden.sync()
        self.flower.update()

    def _care_text(self):
        garden = self.garden
        if garden.bloomed:
            return f'판매가 {garden.pot["base_sale_g"] + (garden.pot["mist_bonus_g"] if garden.pot["misted"] else 0)}G'
        if not garden.pot['initial_watered']:
            return '첫 물주기 전 · 성장 정지'
        if garden.pot['ruleset_id'] == TYCOON_RULE:
            return ('첫 꽃 안내 · 첫 물주기만 필요' if garden.pot['is_tutorial'] else
                    '물 30분 · 분무 15분 · 늦게 돌봐도 정상 성장')
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
        if not self.isMinimized():
            self._normal_position = self.pos()
        self.garden.settings.update(x=self._normal_position.x(), y=self._normal_position.y())
        try:
            self.store.save(self.garden)
        except (SaveError, ValueError, OSError) as exc:
            self.notify('저장 실패 · ' + str(exc), important=True)
            return False
        if getattr(self.store, 'path', None) and self.store.path.exists():
            self._local_saved_at = self.store.path.stat().st_mtime
        return True

    def resizeEvent(self, event):
        if hasattr(self, 'flower'):
            self.flower.set_window_side(min(self.width(), self.height()))
        if hasattr(self, 'message'):
            self.notify(self._message_text, self._message_important)
        super().resizeEvent(event)

    def moveEvent(self, event):
        if hasattr(self, '_normal_position') and not self.isMinimized():
            self._normal_position = event.pos()
        super().moveEvent(event)

    def _prepare_minimize(self):
        self.pages.finish_transition()
        self.pot_slides.finish_transition()
        self.close_collection_picker()
        self._cancel_fertilizer_game()
        self._cancel_mist_game()
        self.flower.timer.stop()
        self.collection_garden.meadow.timer.stop()
        self.persist()

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange and not self._closing:
            minimized = self.isMinimized()
            if minimized and not self._minimized:
                self._minimized = True
                self._prepare_minimize()
            elif not minimized and self._minimized:
                self._minimized = False
                self.refresh()
                if self.flower.isVisible():
                    self.flower.timer.start()
                if self.collection_garden.isVisible():
                    self.collection_garden.meadow.timer.start()
                if self._pending_cloud_prompt is not None:
                    pending = self._pending_cloud_prompt
                    self._pending_cloud_prompt = None
                    QTimer.singleShot(0, lambda: self._consider_cloud_save(*pending))
        super().changeEvent(event)

    def closeEvent(self, event):
        self._closing = True
        self.close_collection_picker()
        self._cancel_fertilizer_game()
        self._cancel_mist_game()
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
        if not event.isAccepted():
            self._closing = False
        if event.isAccepted():
            self.desktop.close()
            self.clock.stop()
            self.autosave.stop()
            self.cloud_poll.stop()
            self.cloud_auto.stop()
            self.cloud_start.stop()
            if self._save_lock is not None:
                self._save_lock.unlock()
                self._save_lock = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true', help='별도 테스트 정원과 설정의 +6시간 버튼')
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
    window = Window(store, garden, args.demo, save_lock=lock, cloud=GoogleDriveSync())
    window.show()
    return app.exec()
