"""Decorative garden themes bought with sunlight."""
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


THEMES = {
    theme.key: theme for theme in (
        GardenTheme('grass', '기본 초록 잔디', 0, '꽃이 편안하게 보이는 기본 정원',
                    '#c7dfa6', '#94bd7d', '#85ad70', '#42603a'),
        GardenTheme('cream', '따뜻한 크림 정원', 12, '햇살이 번지는 포근한 아이보리 정원',
                    '#f5eacb', '#dccb9d', '#cab783', '#64583c'),
        GardenTheme('sky', '맑은 하늘 정원', 24, '맑은 오전을 닮은 푸른빛 정원',
                    '#d9edf1', '#a9ced5', '#8ab7bd', '#36565d'),
        GardenTheme('lavender', '저녁 라벤더 정원', 36, '해 질 무렵처럼 차분한 보랏빛 정원',
                    '#e4dcef', '#baacd2', '#9d8dbc', '#514363'),
    )
}


def garden_theme(key):
    try:
        return THEMES[key]
    except KeyError as exc:
        raise ValueError('알 수 없는 정원 배경') from exc
