"""Event-boundary integration, with explicit offline and demo contexts."""
from uuid import uuid4
from . import effects as fx
from .plant_catalog import VACATION_PLANTS

BOUNDARIES=(.1,.2,.35,.5,.7,.8,1)

def advance(g,now,context='online'):
    if context not in ('online','offline','demo'):raise ValueError('시간 문맥')
    if now<=g.last_update or g.progression['board']['prepared'] is not None:return
    gap=now-g.last_update;elapsed=min(gap,3*fx.DAY)
    g.last_update=now
    if g.vacation:return
    g.reward_wait=max(0,g.reward_wait-elapsed)
    budgets=[min(gap,p['duration']) if p['species'] in VACATION_PLANTS else elapsed for p in g.pots]
    for p in g.pots:
        c=fx.crop(g,p)
        if c and context=='offline' and p['initial_watered'] and p['growth']<p['duration']:
            if gap>=3*fx.HOUR:fx.flag(c,'offline3')
            if gap>=6*fx.HOUR and 'G-A14' in fx.ids(g,p) and fx.flag(c,'shade_return'):
                old=sum(p['growth']/p['duration']>=v for v in (.1,.35,.7,1))
                fx.direct(g,p,1200,p['duration']*.03);fx.stage_events(g,p,old,context)
    while any(b>1e-7 for b in budgets):
        dt=min(b for b in budgets if b>1e-7)
        rates={}
        for index,p in enumerate(g.pots):
            if budgets[index]<=1e-7 or not p['planted'] or not p['initial_watered'] or p['growth']>=p['duration']:continue
            c=fx.crop(g,p);rate=fx.growth_rate(g,p,context) if c else (0.5 if p['care_profile']=='tulip_midwater' and not p['mid_watered'] and not p['legacy_care_exempt'] and p['care_elapsed']>=30*fx.HOUR else 1)
            rates[index]=rate
            marks=[p['duration']*r for r in BOUNDARIES]+[p['duration']-1800,p['duration']-6*fx.HOUR]
            candidates=[max(1e-6,(mark-p['growth'])/rate) for mark in marks if mark>p['growth']+1e-7]
            if candidates:dt=min(dt,*candidates)
            for age,marks_time in [(p['care_elapsed'],(1800,3600,30*fx.HOUR))]+([(c['since_water'],(1800,)),(c['offline'],(3600,))] if c else []):
                for mark in marks_time:
                    if age<mark-1e-7:dt=min(dt,mark-age)
        qualification={
            'G-S04':fx.diversity(g)>=4,'G-S05':fx.decor(g),
            'G-B19':len(g.collection)>=10,'G-B26':len(fx.growing(g))==4,
        }
        for index,p in enumerate(g.pots):
            if budgets[index]<=1e-7:continue
            amount=min(dt,budgets[index]);budgets[index]=max(0,budgets[index]-amount)
            c=fx.crop(g,p)
            if not c:
                g._advance_pot(p,amount);continue
            if p['initial_watered']:
                p['water_wait']=max(0,p['water_wait']-amount);p['mist_wait']=max(0,p['mist_wait']-amount)
            if index not in rates:continue
            ratio=p['growth']/p['duration'];stage=sum(ratio>=v-1e-10 for v in (.1,.35,.7,1))
            gain=min(p['duration']-p['growth'],amount*rates[index])
            p['care_elapsed']+=amount;p['growth']=min(p['duration'],p['growth']+gain)
            c['since_water']+=amount;c['since_mist']+=amount
            if context=='offline':c['offline']+=amount
            for key,qualifies in qualification.items():
                if key in c['ids'] and qualifies:c['qualified'][key]=c['qualified'].get(key,0)+gain
            fx.stage_events(g,p,stage,context)
    advance_sunlight(g,elapsed,now)
    fx.flush_fountain(g)

def advance_sunlight(g,elapsed,now):
    if not g.collection:g.sun_elapsed=0;return
    cycles=g.progression['sun_cycles']
    for key in set(cycles)-{item['id'] for item in g.collection}:del cycles[key]
    for item in g.collection:
        if item['id'] not in cycles:
            cycles[item['id']]=dict(elapsed=0.0,period=fx.sun_period(g,item,True),first=True,theme=g.equipped_theme)
    left=elapsed
    while left>1e-7:
        dt=min(left,min(c['period']-c['elapsed'] for c in cycles.values()))
        dt=max(0,dt)
        for c in cycles.values():c['elapsed']+=dt
        left-=dt
        ready=[item for item in g.collection if cycles[item['id']]['elapsed']>=cycles[item['id']]['period']-1e-7]
        if not ready:break
        order=sorted(ready,key=lambda item:(g.collection.index(item)-g.sun_cursor)%len(g.collection))
        for item in order:
            cycle=cycles[item['id']]
            key=fx.BY_ID['garden',cycle['theme']]['design_id']
            count=1+(key=='G-A15' and len(g.collection)>=10 and item['id']==g.collection[0]['id'])
            for _ in range(count):
                if len(g.sun_tokens)<fx.sun_cap(g):
                    g.sun_tokens.append(dict(id=str(uuid4()),source_flower_id=item['id'],created_at=float(now)))
                    g.sun_cursor=(g.collection.index(item)+1)%len(g.collection)
            cycle.update(elapsed=0.0,period=fx.sun_period(g,item,False),first=False,theme=g.equipped_theme)
        if len(g.sun_tokens)>=fx.sun_cap(g):
            # Production at capacity is discarded, preserving each in-flight cycle.
            for item in g.collection:
                cycle=cycles[item['id']];total=cycle['elapsed']+left
                if total>=cycle['period']:
                    total-=cycle['period'];cycle.update(period=fx.sun_period(g,item,False),first=False,theme=g.equipped_theme)
                    total%=cycle['period']
                cycle['elapsed']=total
            left=0
    g.sun_elapsed=cycles[g.collection[0]['id']]['elapsed']
