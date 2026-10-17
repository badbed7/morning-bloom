"""Real dice-board transitions and durable, replayable reward transactions."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
import secrets
from .content import BY_ID, LEGACY_PLANTS, POOLS

POSITIONS = ('plant','garden','pot','plant','garden','pot','plant','garden','special','pot',
             'plant','garden','pot','plant','garden','pot','plant','garden','special','pot')
GATES = (8,18)
SPECIAL = tuple((grade,category) for grade in ('A','S') for category in ('plant','garden','pot'))
DUPLICATE = dict(C=1,B=2,A=5,S=10)
EXCHANGE = dict(C=3,B=8,A=20,S=40)

def new_state(skin='terracotta', count=1):
    return dict(version=1,tickets=0,petals=0,week=None,max_time=0.0,unlocked=list(LEGACY_PLANTS),
        board=dict(position=0,paid=0,completed=0,seq=0,prepared=None,special=None,last_result=None,history=[]),
        slots=[dict(skin=skin,previous=None,sequence=[]) for _ in range(count)],crops={},flower_skins={},
        sun_cycles={},first_harvest=[],counters=dict(suns=0,rings=0,fountain=0,fountain_at=0.0,pending_fertilizer=0),fraction=0)

def _integer(value, low=0, high=10**15):
    return type(value) is int and low<=value<=high

def _number(value):
    return type(value) in (int,float) and math.isfinite(value) and value>=0

def _ids(value):
    return isinstance(value,list) and all(type(x) is str for x in value) and len(value)==len(set(value))

def validate(state, garden):
    if not isinstance(state,dict) or set(state)!=set(new_state()): raise ValueError('수집 저장 항목')
    if state['version']!=1 or type(state['version']) is not int: raise ValueError('수집 버전')
    if any(not _integer(state[k]) for k in ('tickets','petals','fraction')) or state['fraction']>=10000: raise ValueError('수집 재화')
    if not _number(state['max_time']): raise ValueError('주간 시각')
    if state['week'] is not None:
        try:
            day=datetime.strptime(state['week'],'%Y-%m-%d')
            if day.weekday()!=0: raise ValueError()
        except (TypeError,ValueError): raise ValueError('주간 지급 ID') from None
    unlocked=state['unlocked']
    if not _ids(unlocked) or any(('plant',x) not in BY_ID or not BY_ID['plant',x]['board_eligible'] for x in unlocked): raise ValueError('품종 해금')
    if not set(LEGACY_PLANTS)<=set(unlocked): raise ValueError('기존 품종 해금')
    slots=state['slots']
    if not isinstance(slots,list) or len(slots)!=len(garden.pots): raise ValueError('슬롯 수')
    for slot in slots:
        if not isinstance(slot,dict) or set(slot)!=set(new_state()['slots'][0]) or type(slot['skin']) is not str or slot['skin'] not in garden.owned_skins: raise ValueError('슬롯 장착')
        if slot['previous'] is not None and (type(slot['previous']) is not str or ('plant',slot['previous']) not in BY_ID): raise ValueError('이전 품종')
        if not _ids(slot['sequence']) or len(slot['sequence'])>2 or any(('plant',x) not in BY_ID for x in slot['sequence']): raise ValueError('품종 연속 기록')
    valid_ids={p['plant_id'] for p in garden.pots if p['planted']}|{x['id'] for x in garden.collection}
    for key in ('crops','flower_skins','sun_cycles'):
        if not isinstance(state[key],dict) or not set(state[key])<=valid_ids: raise ValueError(key)
    if any(skin not in garden.owned_skins for skin in state['flower_skins'].values()): raise ValueError('꽃 외형')
    if not _ids(state['first_harvest']) or any(('plant',x) not in BY_ID for x in state['first_harvest']): raise ValueError('최초 수확')
    counters=state['counters']
    if not isinstance(counters,dict) or set(counters)!=set(new_state()['counters']) or any(not _number(x) for x in counters.values()): raise ValueError('효과 카운터')
    if any(not _integer(counters[k]) for k in ('suns','rings','fountain','pending_fertilizer')) or counters['pending_fertilizer']>1: raise ValueError('보상 카운터')
    board=state['board']
    if not isinstance(board,dict) or set(board)!=set(new_state()['board']): raise ValueError('보드 항목')
    if not _integer(board['position'],0,19) or any(not _integer(board[k]) for k in ('paid','completed','seq')) or board['completed']>board['paid']: raise ValueError('보드 진행')
    if not isinstance(board['history'],list) or len(board['history'])>200: raise ValueError('보드 이력')
    for result in board['history']+([board['last_result']] if board['last_result'] else []):
        if not isinstance(result,dict) or set(result)!={'seq','category','item_id','grade','duplicate','petals'}: raise ValueError('보상 이력')
        _validate_reward(result)
        if not _integer(result['seq'],1,board['seq']) or type(result['duplicate']) is not bool or not _integer(result['petals'],1,11): raise ValueError('보상 이력 값')
    special=board['special']
    if special is not None:
        _validate_reward(special)
        if set(special)!={'category','grade','item_id','die'} or not _integer(special['die'],1,6) or SPECIAL[special['die']-1]!=(special['grade'],special['category']) or board['position'] not in GATES: raise ValueError('스페셜 대기')
    if board['paid']-board['completed']!=int(special is not None): raise ValueError('미완료 보상 수')
    prepared=board['prepared']
    if prepared is not None:
        if not isinstance(prepared,dict) or set(prepared)!={'seq','kind','die','target','reward'} or not _integer(prepared['seq'],1) or prepared['seq']!=board['seq']+1: raise ValueError('준비 거래')
        if prepared['kind']=='roll':
            if special is not None or state['tickets']<1 or not _integer(prepared['die'],1,6) or prepared['target']!=(board['position']+prepared['die'])%20: raise ValueError('준비 이동')
            reward=prepared['reward'];_validate_reward(reward)
            if prepared['target'] in GATES:
                if set(reward)!={'category','grade','item_id','die'} or not _integer(reward['die'],1,6) or SPECIAL[reward['die']-1]!=(reward['grade'],reward['category']): raise ValueError('준비 무료 보상')
            elif set(reward)!={'category','grade','item_id'} or reward['category']!=POSITIONS[prepared['target']] or reward['grade']=='S': raise ValueError('준비 일반 보상')
        elif prepared['kind']=='special':
            if special is None or prepared['die']!=0 or prepared['target']!=board['position'] or prepared['reward']!=special: raise ValueError('준비 스페셜')
        else: raise ValueError('거래 종류')

def _validate_reward(value):
    if not isinstance(value,dict) or value.get('category') not in ('plant','garden','pot') or value.get('grade') not in ('S','A','B','C'): raise ValueError('보상 정의')
    pool=POOLS[value['category'],value['grade']]
    if type(value.get('item_id')) is not str or value['item_id'] not in pool: raise ValueError('보상 풀')

def available_week(garden,now):
    """Return an unclaimed KST week without changing the player's save."""
    if not _number(now) or garden.progression['board']['prepared']: return None
    state=garden.progression
    date=datetime.fromtimestamp(now,timezone(timedelta(hours=9))).date()
    week=(date-timedelta(days=date.weekday())).isoformat()
    if state['week'] is not None and week<=state['week']: return None
    if now<state['max_time']: return None
    return week

def claim_weekly(garden,now):
    week=available_week(garden,now)
    if week is None:return False
    state=garden.progression
    state.update(week=week,max_time=max(float(now),state['max_time']),tickets=state['tickets']+5)
    return True

def _choose(category,grade,draw):
    pool=POOLS[category,grade]
    return dict(category=category,grade=grade,item_id=pool[draw(len(pool))])

def prepare(garden,kind='roll',draw=None):
    draw=draw or secrets.randbelow
    state=garden.progression;board=state['board']
    if board['prepared'] is not None: return False
    if kind=='special':
        if board['special'] is None:return False
        plan=dict(seq=board['seq']+1,kind=kind,die=0,target=board['position'],reward=deepcopy(board['special']))
    elif kind=='roll':
        if state['tickets']<=0 or board['special'] is not None:return False
        die=1+draw(6);target=(board['position']+die)%20
        if target in GATES:
            special_die=1+draw(6);grade,category=SPECIAL[special_die-1]
            reward={**_choose(category,grade,draw),'die':special_die}
        else:
            ticket=draw(9);grade='C' if ticket<5 else 'B' if ticket<8 else 'A'
            reward=_choose(POSITIONS[target],grade,draw)
        plan=dict(seq=board['seq']+1,kind=kind,die=die,target=target,reward=reward)
    else:return False
    board['prepared']=plan
    return True

def grant(garden,reward,petals=True):
    state=garden.progression;category=reward['category'];key=reward['item_id'];grade=reward['grade']
    owned=state['unlocked'] if category=='plant' else garden.owned_themes if category=='garden' else garden.owned_skins
    duplicate=key in owned
    if not duplicate:owned.append(key)
    if category=='plant':garden.seeds[key]=garden.seeds.get(key,0)+1
    amount=1+(DUPLICATE[grade] if duplicate else 0) if petals else 0
    state['petals']+=amount
    return dict(category=category,item_id=key,grade=grade,duplicate=duplicate,petals=amount)

def commit(garden):
    state=garden.progression;board=state['board'];plan=board['prepared']
    if plan is None:return False
    if plan['seq']!=board['seq']+1:raise ValueError('거래 순서')
    result=None
    if plan['kind']=='roll':
        if state['tickets']<1:raise ValueError('주사위 부족')
        state['tickets']-=1;board['paid']+=1;board['position']=plan['target']
        if plan['target'] in GATES:board['special']=deepcopy(plan['reward'])
        else:result=grant(garden,plan['reward'])
    else:
        result=grant(garden,plan['reward']);board['special']=None
    board['seq']=plan['seq'];board['prepared']=None
    if result is not None:
        result['seq']=board['seq'];board['completed']+=1;board['last_result']=result
        board['history']=(board['history']+[result])[-200:]
    return deepcopy(plan)

def transact(garden,store,kind='roll',draw=None):
    """A failed second write leaves a durable plan; retry never rerolls."""
    if garden.progression['board']['prepared'] is None:
        before=garden.to_dict()
        if not prepare(garden,kind,draw):return False
        try:store.save(garden)
        except Exception:
            garden.restore(before)
            raise
    prepared=garden.to_dict()
    try:
        result=commit(garden)
        store.save(garden)
    except Exception:
        garden.restore(prepared)
        raise
    return result

def exchange(garden,category,key):
    state=garden.progression
    if state['board']['prepared'] is not None:return False
    item=BY_ID.get((category,key))
    if not item or not item['board_eligible']:return False
    owned=state['unlocked'] if category=='plant' else garden.owned_themes if category=='garden' else garden.owned_skins
    price=EXCHANGE[item['grade']]
    if key in owned or state['petals']<price:return False
    state['petals']-=price
    grant(garden,dict(category=category,item_id=key,grade=item['grade']),petals=False)
    return True
