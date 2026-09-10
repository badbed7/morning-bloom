"""Data-only plant definitions used by the model and the UI."""
from dataclasses import dataclass

DAY = 86400


@dataclass(frozen=True)
class PlantDefinition:
    key: str
    name: str
    growth_seconds: int
    water_interval: int
    mist_interval: int
    mist_actions: int
    temperature_min: int
    temperature_max: int
    seed_price: int
    sale_price: int
    petal_color: str
    center_color: str
    leaf_color: str
    pot_color: str


PLANTS = {
    'daisy': PlantDefinition(
        key='daisy',
        name='데이지',
        growth_seconds=DAY,
        water_interval=2 * DAY,
        mist_interval=2 * DAY,
        mist_actions=1,
        temperature_min=18,
        temperature_max=26,
        seed_price=20,
        sale_price=50,
        petal_color='#fffdf3',
        center_color='#e6b953',
        leaf_color='#86a674',
        pot_color='#bd7e5c',
    ),
    'tulip': PlantDefinition(
        key='tulip',
        name='튤립',
        growth_seconds=2 * DAY,
        water_interval=2 * DAY,
        mist_interval=2 * DAY,
        mist_actions=1,
        temperature_min=16,
        temperature_max=22,
        seed_price=35,
        sale_price=100,
        petal_color='#e9909b',
        center_color='#bc5f72',
        leaf_color='#739a69',
        pot_color='#ad8065',
    ),
}


def plant_definition(species: str) -> PlantDefinition:
    return PLANTS[species]

