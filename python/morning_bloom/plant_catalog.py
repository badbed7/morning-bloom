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

REGULAR_PLANTS = tuple(PLANTS)
RANDOM_SEED_PRICE = 20
PLANTS['ancient'] = PlantDefinition(
    key='ancient', name='고대 꽃', growth_seconds=2 * DAY,
    seed_price=0, sale_price=500, care_profile='start_only',
    shop_tag='랜덤 씨앗에서만 발견 · 0.1%',
    temperature_min=16, temperature_max=26,
    petal_color='#b59bdc', center_color='#f6d878',
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
