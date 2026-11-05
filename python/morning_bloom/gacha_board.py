"""Pure rules for the main flower board and four high-grade side boards.

This module does not spend a real garden balance or grant inventory. The eventual
save transaction must persist the complete draw result before showing animation.
"""

from copy import deepcopy
import secrets
from fractions import Fraction


LENGTH = 60
PRICE = 10
SILVER = frozenset((11, 26, 41))
GOLD = 56
SPECIALS = SILVER | {GOLD}
SIDE_LENGTH = 12
SIDE_DRAWS = 2
SIDE_BOARDS = {
    11: {'name': '새싹 곁길', 'ssr_cells': frozenset((6, 12))},
    26: {'name': '이슬 곁길', 'ssr_cells': frozenset((4, 8, 12))},
    41: {'name': '꽃망울 곁길', 'ssr_cells': frozenset((3, 6, 9, 12))},
    56: {'name': '황금 곁길', 'ssr_cells': frozenset(range(1, 13))},
}

REWARDS = {
    'pot': {'R': ('ivory',), 'SR': ('sage',), 'SSR': ('rose',)},
    'garden': {'R': ('cream',), 'SR': ('sky',), 'SSR': ('lavender',)},
}

# Explicit stable tier assignment; equal item weights within a tier.
from .plant_catalog import CATALOG_GACHA_PLANTS, ROSE_VARIETIES, ROSE_GACHA_PLANTS
from .cosmetics import POT_SKINS, THEMES
PLANT_TIERS = ('SSR', 'SR', 'R', 'SSR', 'SR', 'SR', 'R', 'R')
REWARDS['plant'] = {tier: tuple(k for k, t in zip(CATALOG_GACHA_PLANTS, PLANT_TIERS) if t == tier)
                    for tier in ('R', 'SR', 'SSR')}
REWARDS['rose'] = {tier: tuple(k for k in ROSE_GACHA_PLANTS if ROSE_VARIETIES[k][1] == tier)
                   for tier in ('R', 'SR', 'SSR')}
for category, catalog, prefix in (('pot', POT_SKINS, 'catalog_pot_'), ('garden', THEMES, 'catalog_garden_')):
    for key in catalog:
        if key.startswith(prefix):
            index = int(key.rsplit('_', 1)[1])
            tier = ('R', 'SR', 'SSR')[index % 3]
            REWARDS[category][tier] += (key,)


def board_name(gate):
    return SIDE_BOARDS[gate]['name'] if gate is not None else '일반 꽃길'


def reward_pool(category, rarity, gate=None):
    # Side boards exclude R; per-item weights are shared with the published rate table.
    if gate is not None and (rarity == 'R' or (gate == GOLD and rarity != 'SSR')):
        return ()
    return REWARDS[category].get(rarity, ())

def reward_weight(category, item):
    return ROSE_VARIETIES[item][4] if category == 'rose' else 1


def select_reward(category, rarity, gate, randbelow):
    pool = reward_pool(category, rarity, gate)
    total = sum(reward_weight(category, key) for key in pool)
    ticket = randbelow(total)
    if type(ticket) is not int or not 0 <= ticket < total:
        raise ValueError('아이템 추첨값 범위')
    for key in pool:
        ticket -= reward_weight(category, key)
        if ticket < 0:
            return key
    raise ValueError('빈 보상 목록')


def rarity_weights(state, position, gate):
    forced_ssr = (position in SIDE_BOARDS[gate]['ssr_cells'] if gate is not None
                  else position == GOLD) or state['ssr_miss'] == 59
    forced_sr = gate is not None or position in SILVER or state['sr_miss'] == 9
    if forced_ssr:
        return {'R': 0, 'SR': 0, 'SSR': 10000}
    return {'R': 0, 'SR': 9500, 'SSR': 500} if forced_sr else {'R': 7000, 'SR': 2500, 'SSR': 500}


def next_rarity_probabilities(state):
    """Exact next-roll rates including 36 dice pairs, board cells and pity."""
    validate(state)
    gate = state['side_gate']
    start = state['side_position'] if gate is not None else state['position']
    length = SIDE_LENGTH if gate is not None else LENGTH
    totals = dict.fromkeys(('R', 'SR', 'SSR'), 0)
    for first in range(1, 7):
        for second in range(1, 7):
            position = (start + first + second - 1) % length + 1
            for tier, value in rarity_weights(state, position, gate).items():
                totals[tier] += value
    return {tier: Fraction(total, 36 * 10000) for tier, total in totals.items()}


def _weighted_probabilities(category, tiers, gate=None):
    result = {}
    for tier, chance in tiers.items():
        pool = reward_pool(category, tier, gate)
        total = sum(reward_weight(category, key) for key in pool)
        for key in REWARDS[category][tier]:
            result[key] = chance * Fraction(reward_weight(category, key), total) if total else Fraction(0)
    return result


def ordinary_item_probabilities(category):
    weights = rarity_weights(initial_state(), 1, None)
    return _weighted_probabilities(category, {tier: Fraction(weight, 10000) for tier, weight in weights.items()})


def item_probabilities(category, state):
    return _weighted_probabilities(category, next_rarity_probabilities(state), state['side_gate'])


def initial_state():
    return {
        'position': 0,
        'total': 0,
        'sr_miss': 0,
        'ssr_miss': 0,
        'side_gate': None,
        'side_step': 0,
        'side_position': 0,
    }


def initial_account():
    return {'board': initial_state(), 'tickets': 3, 'leaves': 0, 'history': []}


def validate_account(account, side_draws=SIDE_DRAWS):
    if not isinstance(account, dict) or set(account) != set(initial_account()):
        raise ValueError('뽑기 저장 항목')
    validate(account['board'], side_draws)
    if any(type(account[key]) is not int or account[key] < 0 for key in ('tickets', 'leaves')):
        raise ValueError('뽑기 재화')
    history = account['history']
    if not isinstance(history, list) or len(history) > 200:
        raise ValueError('뽑기 이력')
    for result in history:
        if not isinstance(result, dict) or set(result) != {'position', 'category', 'rarity', 'item', 'duplicate', 'leaves', 'board_gate'}:
            raise ValueError('뽑기 결과')
        gate = result['board_gate']
        if gate is not None and (type(gate) is not int or gate not in SIDE_BOARDS):
            raise ValueError('보상 보드')
        length = SIDE_LENGTH if gate is not None else LENGTH
        if type(result['position']) is not int or result['position'] not in range(1, length + 1) or result['category'] not in REWARDS:
            raise ValueError('뽑기 결과 칸')
        if result['item'] not in reward_pool(result['category'], result['rarity'], gate):
            raise ValueError('뽑기 결과 아이템')
        if type(result['duplicate']) is not bool or type(result['leaves']) is not int or result['leaves'] < 1:
            raise ValueError('뽑기 결과 지급')


def validate(state, side_draws=SIDE_DRAWS):
    if not isinstance(state, dict) or set(state) != set(initial_state()):
        raise ValueError('보드 저장 항목')
    for key in ('position', 'total', 'sr_miss', 'ssr_miss', 'side_step', 'side_position'):
        if type(state[key]) is not int or state[key] < 0:
            raise ValueError('보드 저장 값')
    if not 0 <= state['position'] < LENGTH or not 0 <= state['sr_miss'] <= 9:
        raise ValueError('보드 진행')
    if not 0 <= state['ssr_miss'] <= 59 or not 0 <= state['side_step'] < side_draws:
        raise ValueError('보드 보장')
    if state['side_gate'] is not None and (type(state['side_gate']) is not int or state['side_gate'] not in SPECIALS):
        raise ValueError('곁길 출입구')
    if not 0 <= state['side_position'] < SIDE_LENGTH:
        raise ValueError('곁길 위치')
    if state['side_gate'] is None and (state['side_step'] != 0 or state['side_position'] != 0):
        raise ValueError('닫힌 곁길 진행')


def _next(state, randbelow):
    dice = []
    for _ in range(2):
        face = randbelow(6)
        if type(face) is not int or not 0 <= face < 6:
            raise ValueError('주사위 범위')
        dice.append(face + 1)
    gate = state['side_gate']  # Board on which THIS roll takes place.
    start = state['side_position'] if gate is not None else state['position']
    length = SIDE_LENGTH if gate is not None else LENGTH
    distance = sum(dice)
    path = [(start + step - 1) % length + 1 for step in range(1, distance + 1)]
    position = path[-1]
    forced_ssr = (position in SIDE_BOARDS[gate]['ssr_cells'] if gate is not None
                  else position == GOLD) or state['ssr_miss'] == 59
    roll = randbelow(10000)
    if type(roll) is not int or not 0 <= roll < 10000:
        raise ValueError('추첨값 범위')
    weights = rarity_weights(state, position, gate)
    rarity = ('SSR' if roll < weights['SSR'] else
              'SR' if roll < weights['SSR'] + weights['SR'] else 'R')

    exited = False
    if gate is not None:
        state['side_position'] = position % SIDE_LENGTH
        state['side_step'] += 1
        if state['side_step'] == SIDE_DRAWS:
            state.update(side_gate=None, side_step=0, side_position=0)
            exited = True
    else:
        state['position'] = position % LENGTH
        if position in SPECIALS:
            state.update(side_gate=position, side_step=0, side_position=0)
    state['total'] += 1
    state['sr_miss'] = state['sr_miss'] + 1 if rarity == 'R' else 0
    state['ssr_miss'] = state['ssr_miss'] + 1 if rarity != 'SSR' else 0
    return {
        'dice': dice,
        'start': start,
        'distance': distance,
        'path': path,
        'position': position,
        'rarity': rarity,
        'special': forced_ssr if gate is not None else position in SPECIALS,
        'board_gate': gate,
        'side_position': state['side_position'],
        'exited': exited,
        'side_gate': state['side_gate'],
        'side_step': state['side_step'],
    }


def simulate(state, count, sunlight, free_tickets=0, randbelow=None):
    """Calculate a whole 1/10-draw without mutating inputs or real inventory.

    The caller must select concrete items, persist the complete outcome and debit
    exactly once before playing the one-space-at-a-time animation.
    """
    validate(state)
    if count not in (1, 10) or type(count) is not int:
        raise ValueError('뽑기 횟수')
    if any(type(value) is not int or value < 0 for value in (sunlight, free_tickets)):
        raise ValueError('재화 잔액')
    use_tickets = free_tickets >= count
    cost = count * PRICE
    if not use_tickets and sunlight < cost:
        raise ValueError('햇빛 부족')
    result_state = deepcopy(state)
    draw_random = randbelow or secrets.randbelow
    results = [_next(result_state, draw_random) for _ in range(count)]
    return {
        'state': result_state,
        'results': results,
        'sunlight': sunlight if use_tickets else sunlight - cost,
        'free_tickets': free_tickets - count if use_tickets else free_tickets,
        'payment': 'ticket' if use_tickets else 'sunlight',
    }


def item_rarity(category, key):
    """Return a collection tier without deriving it from a display name."""
    if category in ('plant', 'rose') and key in ROSE_VARIETIES:
        return ROSE_VARIETIES[key][1]
    for tier, pool in REWARDS.get(category, {}).items():
        if key in pool:
            return tier
    return None
