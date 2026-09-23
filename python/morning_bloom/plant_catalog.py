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
        'rose', '장미', 3 * DAY, 50, 150, 'start_only', '겹겹이 피는 붉은 꽃 · 3일',
        18, 26, '#f27179', '#bd485b', '#719460', '#c98c67'),
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


def roll_mystery_seed(draw):
    """Exactly one of 1,000 equally likely tickets is ancient."""
    ticket = draw(1000)
    if ticket == 0:
        return 'ancient'
    return ('starflower', 'daisy', 'tulip')[(ticket - 1) // 333]


def plant_definition(species: str) -> PlantDefinition:
    return PLANTS[species]
