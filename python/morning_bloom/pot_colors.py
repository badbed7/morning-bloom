"""Stable pot color IDs, issue #29 presets and strict opaque RGB custom colors."""
import re

# Never recolor an existing save by reusing one of these IDs for a new preset.
LEGACY_POT_COLORS = {
    'original': ('기본', None),
    'beige': ('베이지', '#dec8a4'),
    'charcoal': ('차콜', '#35313d'),
    'burgundy': ('버건디', '#542c3f'),
    'ivory': ('아이보리', '#f0e5ce'),
    'sage': ('세이지', '#83977b'),
    'blue': ('더스티 블루', '#879eac'),
}

_PRESETS = {
    '뉴트럴': (
        ('neutral_ivory', '아이보리', '#f0e8d8'),
        ('cream_beige', '크림 베이지', '#e8d5b7'),
        ('sand_beige', '샌드 베이지', '#d4bfa3'),
        ('warm_gray', '웜 그레이', '#b8b0a3'),
        ('stone_gray', '스톤 그레이', '#a9a69e'),
        ('neutral_charcoal', '차콜', '#55534e'),
        ('milk_white', '밀크 화이트', '#f5f1e8'),
        ('taupe', '토프', '#a18c78'),
    ),
    '어스톤': (
        ('terracotta', '테라코타', '#b96f50'),
        ('brick_red', '브릭 레드', '#a65342'),
        ('cinnamon', '시나몬', '#b77c56'),
        ('mocha_brown', '모카 브라운', '#80634f'),
        ('clay_pink', '클레이 핑크', '#c58f83'),
        ('dusty_rose', '더스티 로즈', '#b98787'),
        ('olive_green', '올리브 그린', '#85865a'),
        ('sage_green', '세이지 그린', '#a3aa91'),
    ),
    '파스텔': (
        ('butter_yellow', '버터 옐로우', '#e8d99b'),
        ('dusty_mint', '더스티 민트', '#a9c5b5'),
        ('powder_blue', '파우더 블루', '#afc5d3'),
        ('pastel_lavender', '라벤더', '#b9a9ca'),
        ('baby_pink', '베이비 핑크', '#e3b9b7'),
        ('peach', '피치', '#e6b49a'),
        ('pistachio', '피스타치오', '#c0c99b'),
        ('ice_blue', '아이스 블루', '#d0e0e2'),
    ),
    '딥': (
        ('forest_green', '포레스트 그린', '#455b47'),
        ('deep_olive', '딥 올리브', '#555b3d'),
        ('navy', '네이비', '#46566a'),
        ('deep_burgundy', '버건디', '#793f46'),
        ('mustard', '머스타드', '#b18a3f'),
        ('deep_brown', '딥 브라운', '#594337'),
        ('plum', '플럼', '#695064'),
        ('slate_blue', '슬레이트 블루', '#637c88'),
    ),
}
POT_COLOR_GROUPS = {group: tuple(key for key, name, rgb in items) for group, items in _PRESETS.items()}
POT_COLORS = {**LEGACY_POT_COLORS, **{key: (name, rgb) for items in _PRESETS.values() for key, name, rgb in items}}
RECOMMENDED_COLORS = ('original', 'terracotta', 'sage_green', 'cream_beige', 'clay_pink', 'olive_green', 'pastel_lavender')
_HEX = re.compile(r'#[0-9a-fA-F]{6}')


def valid_pot_color(value):
    return type(value) is str and (value in POT_COLORS or _HEX.fullmatch(value) is not None)


def normalize_pot_color(value):
    if not valid_pot_color(value):
        raise ValueError('화분 색상은 등록된 색상 또는 #RRGGBB 형식이어야 합니다.')
    return value if value in POT_COLORS else value.lower()


def pot_color_hex(value):
    key = normalize_pot_color(value)
    return POT_COLORS[key][1] if key in POT_COLORS else key


def pot_color_name(value):
    key = normalize_pot_color(value)
    return POT_COLORS[key][0] if key in POT_COLORS else key.upper()
