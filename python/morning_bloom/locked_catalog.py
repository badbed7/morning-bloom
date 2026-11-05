"""Read-only collection browser backed by playable plant and cosmetic definitions."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import sys

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from .navigation import chevron_icon
from .plant_catalog import PLANTS, ROSE_GACHA_PLANTS
from .cosmetics import THEMES, POT_SKINS

ITEM_SOURCES = {"plant": PLANTS, "garden": THEMES, "pot": POT_SKINS}
CATEGORY_IDS = {"식물": "plant", "정원": "garden", "화분": "pot"}


CATALOG_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2])) / 'assets/catalog'


@dataclass(frozen=True)
class LockedItem:
    key: str
    name: str
    sheet: str
    bounds: tuple[int, int, int, int]
    category: str

    def __post_init__(self):
        source = ITEM_SOURCES.get(self.category)
        if source is None or self.key not in source or self.name != source[self.key].name:
            raise ValueError('도감 분류·ID·이름이 실제 항목과 일치하지 않습니다.')


# Reference sheet order and existing item IDs remain stable.
from .content_names import PLANT_NAMES, GARDEN_NAMES, POT_NAMES
_GARDEN_ROWS = ((46, 90), (169, 90), (292, 90), (419, 91),
                (546, 90), (672, 85), (789, 81), (906, 77))
_POT_ROWS = ((24, 69), (180, 80), (345, 77), (501, 74), (652, 64))
_POT_CENTERS = (126, 356, 580, 795, 1011, 1225, 1447, 1670, 1897)

# Existing grass and the first four pot skins retain their current ownership and prices.
# The larger garden sheet contains the patterns shown again in garden-examples.png.
LOCKED_COLLECTIONS = {
    '식물': tuple(LockedItem(f'catalog_plant_{i:03}', name, 'plants.png',
                         (i % 4 * 384, 20 if i < 4 else 550, 384, 440 if i < 4 else 357), category="plant")
                for i, name in enumerate(PLANT_NAMES)),
    '정원': tuple(LockedItem(f'catalog_garden_{i:03}', name, 'gardens.png',
                         (15 + i % 10 * 152, _GARDEN_ROWS[i // 10][0] + 2,
                          139, _GARDEN_ROWS[i // 10][1] - 4), category="garden")
                for i, name in enumerate(GARDEN_NAMES) if i != 0),
    '화분': tuple(LockedItem(f'catalog_pot_{i:03}', name, 'pots.png',
                         (_POT_CENTERS[i % 9] - 68, _POT_ROWS[i // 9][0], 136, _POT_ROWS[i // 9][1]), category="pot")
                for i, name in enumerate(POT_NAMES) if i >= 4),
}


@lru_cache(maxsize=3)
def catalog_sheet(filename):
    return QImage(str(CATALOG_DIR / filename))


@lru_cache(maxsize=150)
def preview_image(item):
    from PySide6.QtGui import QPainter
    from PySide6.QtCore import QRectF
    from .flower_art import paint_collection_flower, paint_potted_flower
    from .cosmetic_icons import theme_icon
    image = QImage(160, 120, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    if item.category == "plant":
        paint_collection_flower(painter, QRectF(25, 0, 110, 120), PLANTS[item.key])
    elif item.category == "garden":
        painter.drawPixmap(30, 20, theme_icon(THEMES[item.key]).pixmap(100, 80))
    elif item.category == "pot":
        painter.translate(80 - 190 * .9, 10 - 100 * .9)
        painter.scale(.9, .9)
        paint_potted_flower(painter, PLANTS['daisy'], planted=False, skin=item.key)
    painter.end()
    return image

COLLECTIONS = {category: tuple(LockedItem(k, v.name, '', (0, 0, 0, 0), CATEGORY_IDS[category]) for k, v in source.items())
               for category, source in (('식물', PLANTS), ('정원', THEMES), ('화분', POT_SKINS))}


class LockedCatalog(QWidget):
    """Browse designs without acquiring items or modifying a garden save."""
    page_size = 4

    def __init__(self, garden=None):
        super().__init__()
        self.garden = garden
        self.category = '식물'
        self.page = 0
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.setStyleSheet('''
            QFrame#lockedCard {background:#fbf7ed;border:1px solid #ded2bd;border-radius:6px;}
            QFrame#lockedCard QLabel {background:transparent;border:0;font-size:11px;}
            QPushButton {padding:5px 1px;font-size:11px;}
            QPushButton:checked {background:#e7ebdd;border-color:#7c8968;}
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        title = QLabel('수집 도감')
        title.setObjectName('section')
        layout.addWidget(title)
        note = QLabel('식물은 개화하면 영구 기록 · 신규 식물·정원·화분은 꽃길 뽑기로 획득합니다.')
        note.setObjectName('small')
        note.setWordWrap(True)
        layout.addWidget(note)
        categories = QHBoxLayout()
        categories.setSpacing(4)
        self.tabs = QButtonGroup(self)
        for category, items in COLLECTIONS.items():
            button = QPushButton(f'{category} {len(items)}')
            button.setCheckable(True)
            button.setChecked(category == self.category)
            button.setAccessibleName(f'{category} 수집 도감 {len(items)}종')
            button.clicked.connect(lambda checked=False, key=category: self.select_category(key))
            self.tabs.addButton(button)
            categories.addWidget(button, 1)
        layout.addLayout(categories)
        grid = QGridLayout()
        grid.setSpacing(6)
        self.cards = []
        for index in range(self.page_size):
            card = QFrame()
            card.setObjectName('lockedCard')
            card.setMinimumWidth(0)
            policy = QSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            policy.setRetainSizeWhenHidden(True)
            card.setSizePolicy(policy)
            body = QVBoxLayout(card)
            body.setContentsMargins(4, 4, 4, 4)
            body.setSpacing(2)
            picture = QLabel()
            picture.setFixedHeight(78)
            picture.setAlignment(Qt.AlignCenter)
            picture.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            name = QLabel()
            name.setWordWrap(True)
            name.setFixedHeight(34)
            name.setAlignment(Qt.AlignCenter)
            locked = QLabel('')
            locked.setWordWrap(True)
            locked.setFixedHeight(44)
            locked.setObjectName('small')
            locked.setAlignment(Qt.AlignCenter)
            for widget in (picture, name, locked):
                body.addWidget(widget)
            self.cards.append((card, picture, name))
            grid.addWidget(card, index // 2, index % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        navigation = QHBoxLayout()
        self.previous = QPushButton()
        self.next = QPushButton()
        self.counter = QLabel()
        self.counter.setAlignment(Qt.AlignCenter)
        self.counter.setObjectName('small')
        for button, step, label in ((self.previous, -1, '이전 수집 항목'), (self.next, 1, '다음 수집 항목')):
            button.setFixedWidth(28)
            button.setIcon(chevron_icon(step))
            button.setAccessibleName(label)
            button.clicked.connect(lambda checked=False, delta=step: self.change_page(delta))
        navigation.addWidget(self.previous)
        navigation.addWidget(self.counter, 1)
        navigation.addWidget(self.next)
        layout.addLayout(navigation)
        self.show_page()

    def select_category(self, category):
        self.category, self.page = category, 0
        self.show_page()

    def change_page(self, step):
        page = self.page + step
        if 0 <= page <= (len(COLLECTIONS[self.category]) - 1) // self.page_size:
            self.page = page
            self.show_page()

    def show_page(self):
        items = COLLECTIONS[self.category]
        visible = items[self.page * self.page_size:(self.page + 1) * self.page_size]
        for index, (card, picture, name) in enumerate(self.cards):
            card.setVisible(index < len(visible))
            if index < len(visible):
                item = visible[index]
                picture.setPixmap(QPixmap.fromImage(preview_image(item).scaled(
                    QSize(100, 78), Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                name.setText(item.name)
                garden = self.garden
                if self.category == '식물':
                    state = '발견' if garden and item.key in garden.discovered_plants else '미발견'
                    if item.key in ROSE_GACHA_PLANTS:
                        state += f' · 장미 뽑기 전용 · 씨앗 {garden.seeds[item.key] if garden else 0}개'
                    elif item.key.startswith('catalog_plant_'):
                        state += ' · 재배 해금' if garden and item.key in garden.unlocked_plants else ' · 식물 뽑기로 해금'
                    elif item.key == 'dandelion':
                        state += ' · 홀씨 바람놀이'
                    elif item.key == 'ancient':
                        state += ' · 랜덤 씨앗 0.1%'
                    else:
                        state += ' · 골드 씨앗 상점'
                else:
                    owned = garden.owned_themes if self.category == '정원' and garden else garden.owned_skins if garden else []
                    equipped = garden.equipped_theme if self.category == '정원' and garden else garden.equipped_skin if garden else None
                    definition = THEMES[item.key] if self.category == '정원' else POT_SKINS[item.key]
                    state = '사용 중' if item.key == equipped else '보유' if item.key in owned else '미보유'
                    state += ' · 뽑기 전용' if definition.gacha_only else ' · 햇빛 상점/기본 지급'
                from .gacha_board import item_rarity
                category = item.category
                tier = item_rarity(category, item.key)
                if tier:
                    state = f'{tier} · {state}'
                card.layout().itemAt(2).widget().setText(state)
                card.setToolTip(f'{item.name} · {state}')
                card.setAccessibleName(card.toolTip())
        pages = (len(items) + self.page_size - 1) // self.page_size
        self.counter.setText(f'{self.page + 1} / {pages}')
        self.previous.setEnabled(self.page > 0)
        self.next.setEnabled(self.page + 1 < pages)
