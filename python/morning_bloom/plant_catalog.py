"""Data-only plant definitions used by the model and the UI."""
from dataclasses import dataclass

DAY = 86400
HOUR = 3600


@dataclass(frozen=True)
class PlantDefinition:
    key: str
    name: str
    growth_seconds: int
    seed_price: int
    sale_price: int
    care_profile: str
    shop_tag: str
    temperature_min: int
    temperature_max: int
    petal_color: str
    center_color: str
    leaf_color: str
    pot_color: str

    @property
    def mist_bonus(self):
        return self.sale_price // 10


PLANTS = {
    'daisy': PlantDefinition(
        key='daisy', name='데이지', growth_seconds=DAY,
        seed_price=20, sale_price=50, care_profile='start_only',
        shop_tag='하루 단위 재배',
        temperature_min=18, temperature_max=26,
        petal_color='#fffdf3', center_color='#e6b953',
        leaf_color='#86a674', pot_color='#bd7e5c',
    ),
    'starflower': PlantDefinition(
        key='starflower', name='별꽃', growth_seconds=3 * HOUR,
        seed_price=8, sale_price=12, care_profile='start_only',
        shop_tag='빠른 성장 · 낮은 1회 수익',
        temperature_min=15, temperature_max=25,
        petal_color='#f5f7ff', center_color='#f2c96d',
        leaf_color='#7fa77a', pot_color='#b88970',
    ),
    'tulip': PlantDefinition(
        key='tulip', name='튤립', growth_seconds=2 * DAY,
        seed_price=35, sale_price=100, care_profile='tulip_midwater',
        shop_tag='긴 성장 · 높은 1회 보상',
        temperature_min=16, temperature_max=22,
        petal_color='#e9909b', center_color='#bc5f72',
        leaf_color='#739a69', pot_color='#ad8065',
    ),
}

LEGACY_REGULAR_PLANTS = tuple(PLANTS)
PLANTS.update({
    'rose': PlantDefinition(
        'rose', '빨강 장미', 3 * DAY, 50, 150, 'start_only', '겹겹이 피는 붉은 꽃 · 3일',
        18, 26, '#c74753', '#862d40', '#719460', '#c98c67'),
    'lily_of_the_valley': PlantDefinition(
        'lily_of_the_valley', '은방울꽃', 14 * DAY, 160, 560, 'start_only',
        '휴가용 · 14일 · 접속하지 않아도 개화까지 성장',
        15, 23, '#fff8e7', '#e8dfc9', '#70945b', '#c98c67'),
    'clover': PlantDefinition(
        'clover', '토끼풀', 6 * HOUR, 10, 20, 'start_only', '세 잎과 작은 흰 꽃 · 6시간',
        15, 25, '#fff8dc', '#bfd084', '#729b5f', '#c98c67'),
    'sunflower': PlantDefinition(
        'sunflower', '해바라기', 5 * DAY, 75, 240, 'start_only',
        '휴가용 · 5일 · 접속하지 않아도 개화까지 성장',
        20, 28, '#ffd15b', '#98683d', '#6d965d', '#c98c67'),
    'lavender': PlantDefinition(
        'lavender', '라벤더', 7 * DAY, 100, 330, 'start_only',
        '휴가용 · 7일 · 접속하지 않아도 개화까지 성장',
        18, 27, '#b68bd0', '#84609e', '#719366', '#c98c67'),
    'forget_me_not': PlantDefinition(
        'forget_me_not', '물망초', 12 * HOUR, 15, 32, 'start_only', '파란 꽃송이와 노란 꽃심 · 12시간',
        15, 24, '#87b7ed', '#f6d66c', '#729663', '#c98c67'),
})
V10_REGULAR_PLANTS = tuple(PLANTS)
PLANTS.update({
    'pansy': PlantDefinition(
        'pansy', '팬지', 2 * DAY, 35, 100, 'start_only',
        '주말용 · 2일 · 접속하지 않아도 개화까지 성장',
        15, 23, '#a480c0', '#f7d86b', '#789965', '#c98c67'),
    'cosmos': PlantDefinition(
        'cosmos', '코스모스', 3 * DAY, 50, 150, 'start_only',
        '주말용 · 3일 · 접속하지 않아도 개화까지 성장',
        18, 26, '#f5a7c7', '#f6d65c', '#809d68', '#c98c67'),
    'freesia': PlantDefinition(
        'freesia', '프리지아', 4 * DAY, 65, 195, 'start_only',
        '주말용 · 4일 · 접속하지 않아도 개화까지 성장',
        15, 24, '#f6d45d', '#eeb945', '#799965', '#c98c67'),
})
REGULAR_PLANTS = tuple(PLANTS)
WEEKEND_PLANTS = ('pansy', 'cosmos', 'freesia')
VACATION_PLANTS = WEEKEND_PLANTS + ('sunflower', 'lavender', 'lily_of_the_valley')
RANDOM_SEED_PRICE = 20
PLANTS['ancient'] = PlantDefinition(
    key='ancient', name='고대 꽃', growth_seconds=2 * DAY,
    seed_price=0, sale_price=500, care_profile='start_only',
    shop_tag='랜덤 씨앗에서만 발견 · 0.1%',
    temperature_min=16, temperature_max=26,
    petal_color='#70bfe9', center_color='#e2bd6e',
    leaf_color='#659b91', pot_color='#8a759b',
)
PLANTS['dandelion'] = PlantDefinition(
    key='dandelion', name='민들레', growth_seconds=DAY,
    seed_price=0, sale_price=1, care_profile='start_only',
    shop_tag='홀씨 바람놀이 완료 보상', temperature_min=15, temperature_max=25,
    petal_color='#f5cf4d', center_color='#dfa943',
    leaf_color='#719d58', pot_color='#c98c67',
)


# Gacha unlocks are separate from ordinary shop and mystery-seed pools.
from .content_names import PLANT_NAMES
CATALOG_GACHA_PLANTS = tuple(f'catalog_plant_{i:03}' for i in range(8))
# hours, seed gold, sale gold: comparable margins to existing flowers.
GACHA_PLANT_STATS = ((48, 35, 100), (24, 20, 50), (12, 15, 32), (72, 50, 150),
                     (48, 35, 100), (72, 50, 150), (6, 10, 20), (24, 20, 50))
for i, (key, name, stats) in enumerate(zip(CATALOG_GACHA_PLANTS, PLANT_NAMES, GACHA_PLANT_STATS)):
    hours, price, sale = stats
    PLANTS[key] = PlantDefinition(key, name, hours * HOUR, price, sale, 'start_only',
        '꽃길 뽑기로 영구 해금 후 씨앗 구매', 18, 26,
        ('#ece9cf', '#f0ccd9', '#e7dba8', '#ed9eb9', '#f3dfe6', '#40564b', '#aaa08a', '#985c6d')[i],
        '#d3bd74', '#71966a', '#b98665')
# These are game tiers/weights, not measured natural occurrence probabilities.
# Black is a near-black dark red; blue is inspired by special molecular breeding.
ROSE_VARIETIES = {
    # key: (color label, tier, petal, spiral, weight within tier)
    'rose': ('빨강', 'R', '#c74753', '#862d40', 0),
    'rose_pink': ('핑크', 'R', '#ee8eb4', '#bc527f', 5),
    'rose_orange': ('주황', 'SR', '#ed9450', '#bd572d', 3),
    'rose_white': ('하양', 'R', '#fff9ed', '#c6bba9', 5),
    'rose_yellow': ('노랑', 'R', '#f3d259', '#b98c2d', 4),
    'rose_purple': ('보라', 'SR', '#a385c5', '#695188', 2),
    'rose_blue': ('파랑', 'SSR', '#6898de', '#385fa2', 1),
    'rose_black': ('검정', 'SSR', '#32212c', '#865165', 4),
}
ROSE_GACHA_PLANTS = tuple(key for key in ROSE_VARIETIES if key != 'rose')
for key in ROSE_GACHA_PLANTS:
    color, tier, petal, spiral, weight = ROSE_VARIETIES[key]
    detail = ' · 특수 육종 모티브' if key == 'rose_blue' else ' · 흑적색 품종 모티브' if key == 'rose_black' else ''
    PLANTS[key] = PlantDefinition(key, color + ' 장미', 3 * DAY, 50, 150, 'start_only',
        f'{tier} · 장미 씨앗 뽑기 전용{detail}', 18, 26, petal, spiral, '#719460', '#c98c67')
# Freeze the old inventory shape for lossless schema-19 migration.
V19_SEED_PLANTS = REGULAR_PLANTS + CATALOG_GACHA_PLANTS
GACHA_PLANTS = CATALOG_GACHA_PLANTS + ROSE_GACHA_PLANTS
SEED_PLANTS = V19_SEED_PLANTS + ROSE_GACHA_PLANTS
SHOP_SEED_PLANTS = V19_SEED_PLANTS


def roll_mystery_seed(draw):
    """Exactly one of 1,000 equally likely tickets is ancient."""
    ticket = draw(1000)
    if ticket == 0:
        return 'ancient'
    return ('starflower', 'daisy', 'tulip')[(ticket - 1) // 333]


def plant_definition(species: str) -> PlantDefinition:
    return PLANTS[species]
