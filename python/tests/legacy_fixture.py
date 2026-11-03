from copy import deepcopy
from morning_bloom.model import V15_FIELDS
from morning_bloom.plant_catalog import REGULAR_PLANTS


def v14_shape(data):
    data = deepcopy(data)
    for key in V15_FIELDS:
        data.pop(key, None)
    data["seeds"] = {
        key: value for key, value in data["seeds"].items() if key in REGULAR_PLANTS
    }
    return data
