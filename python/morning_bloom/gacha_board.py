"""Pure rules for the proposed 60-space flower board.

This module does not spend a real garden balance or grant inventory. The eventual
save transaction must persist the complete draw result before showing animation.
"""

from copy import deepcopy
import secrets


LENGTH = 60
PRICE = 10
SILVER = frozenset((11, 26, 41))
GOLD = 56
SPECIALS = SILVER | {GOLD}
REWARDS = {
    'pot': {'R': ('ivory',), 'SR': ('sage',), 'SSR': ('rose',)},
    'garden': {'R': ('cream',), 'SR': ('sky',), 'SSR': ('lavender',)},
}


def initial_state():
    return {
        'position': 0,
        'total': 0,
        'sr_miss': 0,
        'ssr_miss': 0,
        'side_gate': None,
        'side_step': 0,
    }


def initial_account():
    return {'board': initial_state(), 'tickets': 3, 'leaves': 0, 'history': []}


def validate_account(account):
    if not isinstance(account, dict) or set(account) != set(initial_account()):
        raise ValueError('뽑기 저장 항목')
    validate(account['board'])
    if any(type(account[key]) is not int or account[key] < 0 for key in ('tickets', 'leaves')):
        raise ValueError('뽑기 재화')
    history = account['history']
    if not isinstance(history, list) or len(history) > 200:
        raise ValueError('뽑기 이력')
    for result in history:
        if not isinstance(result, dict) or set(result) != {'position', 'category', 'rarity', 'item', 'duplicate', 'leaves'}:
            raise ValueError('뽑기 결과')
        if result['position'] not in range(1, 61) or result['category'] not in REWARDS:
            raise ValueError('뽑기 결과 칸')
        if result['item'] not in REWARDS[result['category']].get(result['rarity'], ()):
            raise ValueError('뽑기 결과 아이템')
        if type(result['duplicate']) is not bool or type(result['leaves']) is not int or result['leaves'] < 1:
            raise ValueError('뽑기 결과 지급')


def validate(state):
    if not isinstance(state, dict) or set(state) != set(initial_state()):
        raise ValueError('보드 저장 항목')
    for key in ('position', 'total', 'sr_miss', 'ssr_miss', 'side_step'):
        if type(state[key]) is not int or state[key] < 0:
            raise ValueError('보드 저장 값')
    if not 0 <= state['position'] < LENGTH or not 0 <= state['sr_miss'] <= 9:
        raise ValueError('보드 진행')
    if not 0 <= state['ssr_miss'] <= 59 or not 0 <= state['side_step'] <= 4:
        raise ValueError('보드 보장')
    if state['side_gate'] is not None and state['side_gate'] not in SPECIALS:
        raise ValueError('곁길 출입구')
    if state['side_gate'] is None and state['side_step'] != 0:
        raise ValueError('닫힌 곁길 진행')


def _next(state, randbelow):
    position = state['position'] + 1
    if position > LENGTH:
        position = 1
    if state['side_gate'] is not None:
        if state['side_step'] == 4:
            state['side_gate'] = None
            state['side_step'] = 0
        else:
            state['side_step'] += 1
    if position in SPECIALS:
        state['side_gate'] = position
        state['side_step'] = 0

    forced_ssr = position == GOLD or state['ssr_miss'] == 59
    forced_sr = forced_ssr or position in SILVER or state['sr_miss'] == 9
    roll = randbelow(10000)
    if type(roll) is not int or not 0 <= roll < 10000:
        raise ValueError('추첨값 범위')
    if forced_ssr:
        rarity = 'SSR'
    elif forced_sr:
        rarity = 'SSR' if roll < 500 else 'SR'
    else:
        rarity = 'SSR' if roll < 500 else 'SR' if roll < 3000 else 'R'

    state['position'] = position % LENGTH
    state['total'] += 1
    state['sr_miss'] = state['sr_miss'] + 1 if rarity == 'R' else 0
    state['ssr_miss'] = state['ssr_miss'] + 1 if rarity != 'SSR' else 0
    return {
        'position': position,
        'rarity': rarity,
        'special': position in SPECIALS,
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
