"""Garden backgrounds and reusable pot skins with explicit acquisition routes."""
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class GardenTheme:
    key: str
    name: str
    price: int
    description: str
    top: str
    bottom: str
    tuft: str
    text: str
    label: str
    gacha_only: bool = False


THEMES = {
    theme.key: theme for theme in (
        GardenTheme('grass', '기본 초록 잔디', 0, '꽃이 편안하게 보이는 기본 정원',
                    '#c7dfa6', '#94bd7d', '#85ad70', '#42603a', '잔디'),
        GardenTheme('cream', '따뜻한 크림 정원', 12, '햇살이 번지는 포근한 아이보리 정원',
                    '#f5eacb', '#dccb9d', '#cab783', '#64583c', '크림'),
        GardenTheme('sky', '맑은 하늘 정원', 24, '맑은 오전을 닮은 푸른빛 정원',
                    '#d9edf1', '#a9ced5', '#8ab7bd', '#36565d', '하늘'),
        GardenTheme('lavender', '저녁 라벤더 정원', 36, '해 질 무렵처럼 차분한 보랏빛 정원',
                    '#e4dcef', '#baacd2', '#9d8dbc', '#514363', '라벤더'),
    )
}


@dataclass(frozen=True)
class PotSkin:
    key: str
    name: str
    label: str
    price: int
    description: str
    body: str | None
    rim: str
    edge: str
    pattern: str = ''
    gacha_only: bool = False


POT_SKINS = {
    skin.key: skin for skin in (
        PotSkin('terracotta', '기본 토분', '토분', 0, '식물마다 원래의 토분 색을 사용해요',
                None, '#e6ad86', '#d99b75'),
        PotSkin('ivory', '아이보리 도자기', '아이보리', 12, '세로 결을 새긴 따뜻한 크림색 도자기',
                '#f0e3c7', '#d8c6a0', '#bbaa87', 'stripes'),
        PotSkin('sage', '세이지 물방울', '세이지', 18, '작은 점무늬가 있는 세이지색 화분',
                '#8eaa83', '#dbe3c7', '#647e5d', 'dots'),
        PotSkin('rose', '로즈 리본', '로즈', 24, '아이보리 띠를 두른 차분한 장밋빛 화분',
                '#c78e92', '#f0dfcb', '#9f6f77', 'band', gacha_only=True),
    )
}


def pot_skin(key):
    try:
        return POT_SKINS[key]
    except KeyError as exc:
        raise ValueError('알 수 없는 화분 스킨') from exc


# Re-export the shared palette for existing catalog consumers.
from .pot_colors import POT_COLORS, pot_color_hex


def colored_pot_skin(key, color='original', base_color=None):
    style = pot_skin(key)
    body = pot_color_hex(color) or base_color
    if body is None:
        return style
    channels = [int(body[i:i+2], 16) for i in (1, 3, 5)]
    rim = '#' + ''.join(f'{round(value + (255-value)*.23):02x}' for value in channels)
    edge = '#' + ''.join(f'{round(value*.72):02x}' for value in channels)
    return replace(style, body=body, rim=rim, edge=edge)


def garden_theme(key):
    try:
        return THEMES[key]
    except KeyError as exc:
        raise ValueError('알 수 없는 정원 배경') from exc



# Runtime styles use clean vector shapes, never text/card crops from preview sheets.
from .content_names import GARDEN_NAMES, POT_NAMES
_POT_COLORS = (
    '#e8dfc9','#f0e6cf','#e4ba70','#879571','#9db4c9','#e6bcb3','#667251','#eee4d0',
    '#d4b78c','#e6e0d0','#ad805b','#e6bdb1','#b7cae0','#ece6d0','#e9dfc9','#92a277',
    '#d7a99b','#e2b853','#c5d8e1','#a0b18c','#efe8db','#b8b7ad','#823d40','#e9dcc2',
    '#8b9872','#d5a7a6','#d9cbb2','#7897a4','#e1c19f','#7e8962','#e8e0ce','#42413e',
    '#eae0c9','#bb7c4b','#a5bed9','#d8c49e','#d9cfb5','#dfb7a3','#e6e2ce','#ad9aba','#e9e1cf')

for i, name in enumerate(GARDEN_NAMES):
    if i == 0:
        continue
    top, bottom, tuft = '#d6dfb7', '#adc38c', '#789967'
    if any(x in name for x in ('핑크', '벚꽃')):
        top, bottom, tuft = '#f1d3d0', '#e3bbb8', '#b67f8b'
    elif any(x in name for x in ('낙엽', '단풍', '가을')):
        top, bottom, tuft = '#ebd6aa', '#d8b985', '#b17e58'
    elif any(x in name for x in ('물가', '연못', '시냇물', '호수', '비 온')):
        top, bottom, tuft = '#c9e0dc', '#a2c8bf', '#648e85'
    elif '밤하늘' in name:
        top, bottom, tuft = '#3d565a', '#273e47', '#92aaa0'
    elif any(x in name for x in ('눈', '서리')):
        top, bottom, tuft = '#eef0e7', '#c9d7d2', '#95b5aa'
    key = f'catalog_garden_{i:03}'
    THEMES[key] = GardenTheme(key, name, 0, name + ' · 꽃길 뽑기 전용',
        top, bottom, tuft, '#f3efdb' if '밤하늘' in name else '#354b38', name, True)
for i, name in enumerate(POT_NAMES):
    if i < 4:
        continue
    key = f'catalog_pot_{i:03}'
    POT_SKINS[key] = PotSkin(key, name, name, 0, name + ' · 꽃길 뽑기 전용',
        _POT_COLORS[i - 4], '#e8d5b6', '#b89e80', name, True)
