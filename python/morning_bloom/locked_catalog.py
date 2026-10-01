"""Read-only previews for the planned gacha collection, separate from playable items."""
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


CATALOG_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2])) / 'assets/catalog'


@dataclass(frozen=True)
class LockedItem:
    key: str
    name: str
    sheet: str
    bounds: tuple[int, int, int, int]


# Sheet order is fixed. Keep these IDs when acquisition is implemented later.
PLANT_NAMES = (
    '몬스테라 알보', '호야 크림슨 퀸', '스투키 바리에가타', '필로덴드론 핑크 프린세스',
    '칼라디움 화이트 핑크', '알로카시아 블랙 벨벳', '리톱스', '부르고뉴 고사리',
)
GARDEN_NAMES = (
    '기본 잔디', '연한 잔디', '진한 잔디', '작은 꽃', '들꽃', '네잎클로버', '클로버', '화이트 플라워', '블루 플라워', '핑크 플라워',
    '라벤더', '데이지', '민들레', '튤립', '코스모스', '벚꽃', '벚꽃잎', '가을 잎', '단풍', '낙엽',
    '새싹', '허브', '잎사귀', '풀밭', '잔디+흰 꽃잎', '잔디+핑크 꽃잎', '잔디+노란 꽃잎', '잔디+보라 꽃잎', '잔디+낙엽', '잔디+열매',
    '이끼 느낌', '자연스러운 잡초', '야생화', '삼잎클로버', '토끼풀', '패랭꽃', '하트풀', '작은 열매', '밤하늘풀', '은방울꽃',
    '파스텔 잔디', '물든 잔디', '언덕 느낌', '그늘진 잔디', '햇빛 비추는 잔디', '비 온 뒤', '서리 낀 잔디', '눈 오는 잔디', '가을빛 잔디', '핑크빛 잔디',
    '흙바닥+잔디', '자갈길', '돌길', '징검다리', '나무 판자길', '벽돌길', '모래길', '흙길', '잔디+돌', '잔디+나무뿌리',
    '연못가 잔디', '물가 잔디', '시냇물 옆', '호수 옆', '울타리 옆', '나무 그늘 아래', '나무 주변', '큰 나무 아래', '꽃밭 가장자리', '돌담 옆',
    '정원 테두리', '정원 울타리', '화단 주변', '장미 정원', '수국 정원', '허브 정원', '라벤더 정원', '야외 테라스', '분수대 주변', '온실 주변',
)
POT_NAMES = (
    '토분', '아이보리', '세이지', '로즈', '스톤', '플라워', '체크', '리브드', '플라워 패턴',
    '핑크 스톤', '딥그린', '크림 스톤', '플루트', '핸들', '우드', '핑크 플라워', '블루 라인', '리프 패턴',
    '투톤', '그린 체크', '라운드', '머스터드', '블루 체크', '세로 리브드', '튤립 패턴', '시멘트', '버건디',
    '웨이브', '양손잡이', '하트 패턴', '테라조', '와이드', '주름', '데이지', '스트라이프', '블랙',
    '화이트 체크', '샬로우', '스카이 플라워', '샌드', '핸들 스톤', '미니', '그린 스트라이프', '라벤더', '도트',
)
_GARDEN_ROWS = ((46, 90), (169, 90), (292, 90), (419, 91),
                (546, 90), (672, 85), (789, 81), (906, 77))
_POT_ROWS = ((24, 69), (180, 80), (345, 77), (501, 74), (652, 64))
_POT_CENTERS = (126, 356, 580, 795, 1011, 1225, 1447, 1670, 1897)

# Existing grass and the first four pot skins retain their current ownership and prices.
# The larger garden sheet contains the patterns shown again in garden-examples.png.
LOCKED_COLLECTIONS = {
    '식물': tuple(LockedItem(f'catalog_plant_{i:03}', name, 'plants.png',
                         (i % 4 * 384, 20 if i < 4 else 550, 384, 440 if i < 4 else 357))
                for i, name in enumerate(PLANT_NAMES)),
    '정원': tuple(LockedItem(f'catalog_garden_{i:03}', name, 'gardens.png',
                         (15 + i % 10 * 152, _GARDEN_ROWS[i // 10][0] + 2,
                          139, _GARDEN_ROWS[i // 10][1] - 4))
                for i, name in enumerate(GARDEN_NAMES) if i != 0),
    '화분': tuple(LockedItem(f'catalog_pot_{i:03}', name, 'pots.png',
                         (_POT_CENTERS[i % 9] - 68, _POT_ROWS[i // 9][0], 136, _POT_ROWS[i // 9][1]))
                for i, name in enumerate(POT_NAMES) if i >= 4),
}


@lru_cache(maxsize=3)
def catalog_sheet(filename):
    return QImage(str(CATALOG_DIR / filename))


def preview_image(item):
    return catalog_sheet(item.sheet).copy(QRect(*item.bounds))


class LockedCatalog(QWidget):
    """Browse designs without acquiring items or modifying a garden save."""
    page_size = 4

    def __init__(self):
        super().__init__()
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
        title = QLabel('신규 수집 도감 · 잠김')
        title.setObjectName('section')
        layout.addWidget(title)
        note = QLabel('가챠 업데이트 예정 · 지금은 미리보기만 가능해요.')
        note.setObjectName('small')
        note.setWordWrap(True)
        layout.addWidget(note)
        categories = QHBoxLayout()
        categories.setSpacing(4)
        self.tabs = QButtonGroup(self)
        for category, items in LOCKED_COLLECTIONS.items():
            button = QPushButton(f'{category} {len(items)}')
            button.setCheckable(True)
            button.setChecked(category == self.category)
            button.setAccessibleName(f'{category} 잠금 도감 {len(items)}종')
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
            locked = QLabel('잠김')
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
        for button, step, label in ((self.previous, -1, '이전 잠금 항목'), (self.next, 1, '다음 잠금 항목')):
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
        if 0 <= page <= (len(LOCKED_COLLECTIONS[self.category]) - 1) // self.page_size:
            self.page = page
            self.show_page()

    def show_page(self):
        items = LOCKED_COLLECTIONS[self.category]
        visible = items[self.page * self.page_size:(self.page + 1) * self.page_size]
        for index, (card, picture, name) in enumerate(self.cards):
            card.setVisible(index < len(visible))
            if index < len(visible):
                item = visible[index]
                picture.setPixmap(QPixmap.fromImage(preview_image(item).scaled(
                    QSize(100, 78), Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                name.setText(item.name)
                card.setToolTip(f'{item.name} · 잠김 · 가챠 획득 예정')
                card.setAccessibleName(card.toolTip())
        pages = (len(items) + self.page_size - 1) // self.page_size
        self.counter.setText(f'{self.page + 1} / {pages}')
        self.previous.setEnabled(self.page > 0)
        self.next.setEnabled(self.page + 1 < pages)
