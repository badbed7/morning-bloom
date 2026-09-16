"""Garden backgrounds and reusable pot skins bought with sunlight."""
from dataclasses import dataclass


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


POT_SKINS = {
    skin.key: skin for skin in (
        PotSkin('terracotta', '기본 토분', '토분', 0, '식물마다 원래의 토분 색을 사용해요',
                None, '#e6ad86', '#d99b75'),
        PotSkin('ivory', '아이보리 도자기', '아이보리', 12, '세로 결을 새긴 따뜻한 크림색 도자기',
                '#f0e3c7', '#d8c6a0', '#bbaa87', 'stripes'),
        PotSkin('sage', '세이지 물방울', '세이지', 18, '작은 점무늬가 있는 세이지색 화분',
                '#8eaa83', '#dbe3c7', '#647e5d', 'dots'),
        PotSkin('rose', '로즈 리본', '로즈', 24, '아이보리 띠를 두른 차분한 장밋빛 화분',
                '#c78e92', '#f0dfcb', '#9f6f77', 'band'),
    )
}


def pot_skin(key):
    try:
        return POT_SKINS[key]
    except KeyError as exc:
        raise ValueError('알 수 없는 화분 스킨') from exc


def garden_theme(key):
    try:
        return THEMES[key]
    except KeyError as exc:
        raise ValueError('알 수 없는 정원 배경') from exc
