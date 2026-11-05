from copy import deepcopy
from morning_bloom.model import V15_FIELDS
from morning_bloom.plant_catalog import REGULAR_PLANTS, V19_SEED_PLANTS


def v14_shape(data):
    data = deepcopy(data)
    data.pop("pot_skins", None)
    data.pop("pot_colors", None)
    data.pop("flower_pots", None)
    for key in V15_FIELDS:
        data.pop(key, None)
    data["seeds"] = {
        key: value for key, value in data["seeds"].items() if key in REGULAR_PLANTS
    }
    data['gacha']['board'].pop('side_position', None)
    for record in data['gacha']['history']:
        record.pop('board_gate', None)
    return data


def v19_shape(data):
    data = deepcopy(data)
    data['seeds'] = {key: value for key, value in data['seeds'].items() if key in V19_SEED_PLANTS}
    return data
