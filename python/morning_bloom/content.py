"""Stable content IDs, rarity and versioned board pools. No Qt dependency."""
import json
from pathlib import Path

CONTENT_VERSION = 1
ITEMS = json.loads(Path(__file__).with_name('content_data.json').read_text(encoding='utf-8'))
BY_ID = {(item['category'], item['item_id']): item for item in ITEMS}
BY_DESIGN = {item['design_id']: item for item in ITEMS}
GRADES = ('S', 'A', 'B', 'C')
POOLS = {(category, grade): tuple(item['item_id'] for item in ITEMS
    if item['category']==category and item['grade']==grade and item['board_eligible'])
    for category in ('plant','garden','pot') for grade in GRADES}
LEGACY_PLANTS = tuple(item['item_id'] for item in ITEMS if item['category']=='plant' and not item['item_id'].startswith('catalog_') and item['board_eligible'])
NEW_PLANTS = tuple(f'catalog_plant_{i:03}' for i in range(8))

def definition(category, key):
    return BY_ID[(category, key)]

def rarity(category, key):
    return definition(category,key)['grade']

def description(category,key):
    return definition(category,key).get('description','')

assert len(BY_ID)==150 and sum(item['board_eligible'] for item in ITEMS)==140
assert all(POOLS.values())
