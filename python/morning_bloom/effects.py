"""Version-one equipment effects. Conditions use stable IDs, never display text."""
from .content import BY_ID, BY_DESIGN

HOUR=3600; DAY=86400
PINK=('rose','tulip','cosmos'); WHITE=('daisy','lily_of_the_valley'); PURPLE=('lavender','pansy')

# (fraction, condition); multiple sources add and share the documented caps.
GROWTH={
 'G-S01':[(.12,'offline')], 'G-S03':[(.15,'species:rose')],
 'G-S04':[(.10,'diverse4')], 'G-S07':[(.08,'always'),(.12,'long72')],
 'G-A03':[(.10,'long72')], 'G-A04':[(.12,'species:lily_of_the_valley')],
 'G-A05':[(.10,'care3')], 'G-A07':[(.12,'recent_water')], 'G-A08':[(.12,'offline_last6')],
 'G-A18':[(.08,'same_display6')], 'G-B01':[(.06,'species:starflower')],
 'G-B02':[(.05,'ordinary_mystery')], 'G-B05':[(.06,'species:forget_me_not')],
 'G-B07':[(.06,'species:lavender')], 'G-B11':[(.06,'species:cosmos')],
 'G-B16':[(.06,'species:sunflower')], 'G-B17':[(.05,'purple')],
 'G-B20':[(.05,'rotate')], 'G-B22':[(.05,'diverse3')],
 'G-C00':[(.02,'first_hour')], 'G-C01':[(.03,'first_half_hour')],
 'G-C02':[(.03,'last_half_hour')], 'G-C03':[(.04,'species:clover')],
 'G-C04':[(.03,'first20')], 'G-C07':[(.01,'offline')],
 'G-C09':[(.02,'unmisted')], 'G-C14':[(.02,'duration24')],
 'G-C15':[(.03,'offline_first_hour')], 'G-C19':[(.02,'short6')],
 'G-C20':[(.01,'always')], 'G-C22':[(.02,'over72')], 'G-C24':[(.04,'species:rose')],
 'G-C25':[(.02,'last20_misted')],
 'P-S01':[(.12,'species:tulip')], 'P-S02':[(.12,'species:starflower,forget_me_not')],
 'P-A05':[(.10,'species:daisy')], 'P-A06':[(.08,'offline_lavender')],
 'P-B01':[(.06,'new_species')], 'P-B04':[(.07,'white')],
 'P-B05':[(.06,'phases24')], 'P-B08':[(.05,'species:clover')],
 'P-C05':[(.02,'after_half')], 'P-C07':[(.02,'phases13')],
 'P-C11':[(.03,'species:rose,cosmos')], 'P-C14':[(.02,'ancient_mystery')],
 'P-C15':[(.05,'short_first10')],
}
SALES={
 'G-S01':[(.08,'offline_bloom')], 'G-S03':[(.15,'species:rose')],
 'G-S04':[(.10,'qualified:G-S04')], 'G-S05':[(.12,'qualified:G-S05')],
 'G-A01':[(.12,'new_species')], 'G-A02':[(.08,'flag:four_mist')],
 'G-A03':[(.03,'long72')], 'G-A12':[(.10,'care30m')],
 'G-A17':[(.05,'long7_misted')], 'G-B04':[(.06,'white')],
 'G-B06':[(.03,'tulip_misted')], 'G-B10':[(.07,'species:tulip')],
 'G-B12':[(.07,'long_no_fert')], 'G-B13':[(.04,'no_water')],
 'G-B15':[(.04,'misted')], 'G-B18':[(.06,'offline_bloom')],
 'G-B19':[(.05,'qualified:G-B19')], 'G-B23':[(.06,'weekend_price')],
 'G-B26':[(.05,'qualified:G-B26')], 'G-C10':[(.04,'species:clover')],
 'G-C13':[(.02,'flag:late_water')], 'G-C21':[(.03,'unmisted')],
 'P-S01':[(.15,'tulip_misted')], 'P-S02':[(.12,'species:starflower,forget_me_not')],
 'P-A02':[(.08,'pink'),(.06,'pink_misted')], 'P-A04':[(.10,'pairs3')],
 'P-B03':[(.07,'pink')], 'P-B08':[(.03,'species:clover')],
 'P-B12':[(.06,'white_misted')], 'P-C01':[(.03,'lily_misted')],
 'P-C09':[(.02,'sunflower_misted')], 'P-C17':[(.03,'short12')],
 'P-C18':[(.03,'dot')], 'P-C19':[(.03,'balanced_care')],
}
COOLDOWNS={
 'G-A16':[('water',.08,'misted'),('mist',.08,'misted')],
 'G-C17':[('water',.03,'always')], 'G-C18':[('mist',.03,'always')],
 'P-B09':[('mist',.12,'species:forget_me_not')], 'P-C00':[('water',.05,'unmisted')],
}
FERTILIZER={
 'G-S02':[(.20,'long72')], 'G-S06':[(.10,'always')],
 'P-S03':[(.10,'not_first_fert')], 'P-A01':[(.30,'first_fert_diverse3')],
 'P-A06':[(.50,'first_fert_lavender')], 'P-A08':[(.30,'fert24')],
 'P-B02':[(.20,'flag:fert_charge')], 'P-B11':[(.20,'last_stage')],
 'P-C03':[(.05,'first_fert_pink')], 'P-C04':[(.10,'first_fert')],
}
EVENT_IDS={
 'G-S02','G-S05','G-S06','G-S07','G-A02','G-A06','G-A09','G-A10','G-A11','G-A13','G-A14','G-A15',
 'G-B03','G-B08','G-B09','G-B14','G-B19','G-B21','G-B24','G-B25','G-B26','G-B27','G-B28','G-B29','G-B30',
 'G-C05','G-C06','G-C08','G-C11','G-C12','G-C13','G-C16','G-C23','G-C26','G-C27',
 'P-S03','P-S04','P-A03','P-A04','P-A05','P-A07','P-B02','P-B06','P-B07','P-B10','P-B13',
 'P-C02','P-C06','P-C08','P-C10','P-C12','P-C13','P-C16',
}
SUPPORTED=set(GROWTH)|set(SALES)|set(COOLDOWNS)|set(FERTILIZER)|EVENT_IDS
assert SUPPORTED=={key for key in BY_DESIGN if key[0] in 'GP'}, (set(BY_DESIGN)-SUPPORTED)

def new_crop():
    return dict(version=1,ids=[],skin=None,theme=None,flags=[],qualified={},direct=0.0,stage_direct=0.0,
        fertilizer=0.0,care_saved=0.0,offline=0.0,since_water=0.0,since_mist=0.0,
        history=[],pairs=0,fountain_pairs=0,spray_waters=0,spray_boosts=0,charges=0,offline_bloom=False,
        sale_units=0,slot=0)

def crop(g,p):return g.progression['crops'].get(p.get('plant_id'))
def ids(g,p):
    c=crop(g,p)
    return set(c['ids']) if c and p['initial_watered'] and not p['is_tutorial'] else set()
def waters(p):return max(0,p['water_count']-1)
def growing(g):return [p for p in g.pots if p['planted'] and p['initial_watered'] and p['growth']<p['duration']]
def diversity(g):return len({p['species'] for p in growing(g)})
def display_diversity(g):return len({x['species'] for x in g.collection})
def decor(g):return display_diversity(g)>=3 and len({g.skin_for(x['id']) for x in g.collection})>=3
def flag(c,key):
    if key in c['flags']:return False
    c['flags'].append(key);return True

def condition(key,g,p,c,context='online'):
    species=p['species'];ratio=p['growth']/p['duration'];duration=p['duration']
    if key.startswith('species:'):return species in key.split(':')[1].split(',')
    if key.startswith('flag:'):return key[5:] in c['flags']
    if key.startswith('qualified:'):return c['qualified'].get(key[10:],0)>=duration*.5-1e-6
    return {
        'always':True,'offline':context=='offline','first_hour':p['care_elapsed']<HOUR,
        'first_half_hour':p['care_elapsed']<1800,'last_half_hour':duration-p['growth']<=1800+1e-6,
        'first20':ratio<.2-1e-10,'after_half':ratio>=.5-1e-10,'last20_misted':ratio>=.8-1e-10 and p['misted'],
        'unmisted':not p['misted'],'misted':p['misted'],'duration24':duration==DAY,
        'short6':duration<=6*HOUR,'short12':duration<=12*HOUR,'over72':duration>3*DAY,
        'long72':duration>=3*DAY,'under72':duration<3*DAY,'long7_misted':duration>=7*DAY and p['misted'],
        'offline_first_hour':context=='offline' and c['offline']<HOUR,
        'care3':waters(p)>=3 and p['mist_count']>=3,
        'recent_water':waters(p)>0 and c['since_water']<1800,
        'offline_last6':context=='offline' and duration-p['growth']<=6*HOUR+1e-6,
        'same_display6':sum(x['species']==species for x in g.collection)>=6,
        'ordinary_mystery':p['plant_id'] in g.mystery_plants and species!='ancient',
        'ancient_mystery':p['plant_id'] in g.mystery_plants and species=='ancient',
        'purple':species in PURPLE,'white':species in WHITE,'pink':species in PINK,
        'diverse3':diversity(g)>=3,'diverse4':diversity(g)>=4,
        'rotate':g.progression['slots'][c['slot']]['previous'] not in (None,species),
        'new_species':species not in g.progression['first_harvest'],
        'phases24':sum(ratio>=v for v in (.1,.35,.7,1)) in (1,3),
        'phases13':sum(ratio>=v for v in (.1,.35,.7,1)) in (0,2),
        'short_first10':duration<=6*HOUR and ratio<.1-1e-10,
        'offline_lavender':context=='offline' and species=='lavender',
        'offline_bloom':c['offline_bloom'],'care30m':c['care_saved']>=1800,
        'tulip_misted':species=='tulip' and p['misted'],'pink_misted':species in PINK and p['misted'],
        'white_misted':species in WHITE and p['misted'],'lily_misted':species=='lily_of_the_valley' and p['misted'],
        'sunflower_misted':species=='sunflower' and p['misted'],
        'long_no_fert':duration>=2*DAY and p['fertilizer_used']==0,'no_water':waters(p)==0,
        'weekend_price':2*DAY<=duration<7*DAY,'pairs3':min(waters(p),p['mist_count'])>=3,
        'dot':p['misted'] and c['since_mist']>=3*HOUR,
        'balanced_care':waters(p)>=2 and waters(p)==p['mist_count'],
        'first_fert':p['fertilizer_used']==0,'not_first_fert':p['fertilizer_used']>0,
        'first_fert_diverse3':p['fertilizer_used']==0 and diversity(g)>=3,
        'first_fert_lavender':p['fertilizer_used']==0 and species=='lavender',
        'first_fert_pink':p['fertilizer_used']==0 and species in PINK,
        'fert24':p['fertilizer_used']+1 in (2,4),'last_stage':ratio>=.7-1e-10,
    }[key]

def modifier(table,g,p,context='online'):
    c=crop(g,p)
    return sum(value for key in ids(g,p) for value,when in table.get(key,[]) if condition(when,g,p,c,context)) if c else 0

def growth_rate(g,p,context):return 1+min(.2,modifier(GROWTH,g,p,context))

def cooldown(g,p,kind,initial=False):
    c=crop(g,p);effects=ids(g,p);base=1800 if kind=='water' else 900
    reduction=sum(value for key in effects for target,value,when in COOLDOWNS.get(key,[]) if target==kind and condition(when,g,p,c))
    if kind=='water' and waters(p)==0 and 'P-C08' in effects:reduction+=1/6
    if kind=='mist' and p['mist_count']==1:
        if 'G-C08' in effects:reduction+=.05
        if 'G-B24' in effects and p['species'] in PINK:reduction+=.1
    return base*(1-min(.2,reduction))

def direct(g,p,seconds,own_cap=None):
    c=crop(g,p)
    if not c or p['is_tutorial']:return 0
    available=max(0,p['duration']*.1-c['direct'])
    if own_cap is not None:available=min(available,own_cap)
    used=max(0,min(seconds,available,p['duration']-p['growth']))
    p['growth']+=used;c['direct']+=used;c['care_saved']+=used
    return used

def stage_events(g,p,old_stage,context):
    c=crop(g,p)
    if not c:return
    effects=ids(g,p)
    for stage in range(old_stage+1,5):
        if p['growth']/p['duration']+1e-10<(.1,.35,.7,1)[stage-1]:break
        if flag(c,'stage'+str(stage)):
            if 'P-A07' in effects:p['water_wait']=p['mist_wait']=0.0
            if 'G-A09' in effects:c['stage_direct']+=direct(g,p,180,min(p['duration']*.01-c['stage_direct'],180))
    if p['growth']>=p['duration'] and context=='offline':c['offline_bloom']=True

def start(g,p):
    c=crop(g,p)
    if not c:return
    slot=g.progression['slots'][g.selected]
    c.update(theme=g.equipped_theme,skin=slot['skin'],ids=[BY_ID['garden',g.equipped_theme]['design_id'],BY_ID['pot',slot['skin']]['design_id']])
    if p['is_tutorial']:return
    if 'G-C16' in ids(g,p):direct(g,p,30,p['duration']*.005)
    p['water_wait']=cooldown(g,p,'water',True)
    # The historical first spray remains immediately available. First-spray
    # cooldown perks shorten the wait after completing that first spray.
    p['mist_wait']=0.0

def after_care(g,p,kind):
    c=crop(g,p)
    if not c or p['is_tutorial']:return
    e=ids(g,p);w=waters(p);m=p['mist_count']
    c['history']=(c['history']+[kind])[-3:]
    if kind=='water':
        c['since_water']=0.0;c['spray_waters']+=1
        if 'G-S02' in e and p['duration']>=3*DAY:direct(g,p,36)
        if p['growth']>=p['duration']*.8:flag(c,'late_water')
        if 'G-C06' in e and w<=3:direct(g,p,30)
        if 'G-B03' in e and w==4:direct(g,p,180)
        if 'G-B21' in e and p['species'] in ('pansy','cosmos','freesia') and w<=5:direct(g,p,60)
        if 'G-C26' in e and p['species'] in ('starflower','forget_me_not') and w==1:direct(g,p,20)
        if 'G-A11' in e and w%2==0 and flag(c,'mist-reduce'+str(m)):p['mist_wait']=max(0,p['mist_wait']-60)
        if 'P-B10' in e and w%3==0 and w<=9:direct(g,p,120)
        if 'P-B02' in e:flag(c,'fert_charge')
        if 'P-A03' in e and c['charges']:
            direct(g,p,120);c['charges']=0
        if 'P-B07' in e and 'offline3' in c['flags'] and flag(c,'wood_used'):direct(g,p,180)
    else:
        c['since_mist']=0.0
        if m==1:
            if 'G-C05' in e:direct(g,p,30)
            if 'G-B14' in e:direct(g,p,120)
            if 'G-A02' in e and diversity(g)>=4:flag(c,'four_mist')
            if 'G-C27' in e and p['species'] in ('lavender','pansy'):p['water_wait']=max(0,p['water_wait']-60)
        if 'G-B30' in e and len(growing(g))==4:direct(g,p,12)
        if 'G-A10' in e and m%2==0 and flag(c,'water-reduce'+str(w)):p['water_wait']=max(0,p['water_wait']-180)
        if 'P-C02' in e and w and flag(c,'sage'+str(w)):p['water_wait']=max(0,p['water_wait']-30)
        if 'P-A03' in e and c['since_water']<=300:c['charges']=1
        if 'P-B13' in e and c['spray_waters']>=2 and c['spray_boosts']<3:
            direct(g,p,60);c['spray_boosts']+=1
        c['spray_waters']=0
    if 'P-C13' in e and c['history']==['water','mist','water'] and flag(c,'stripe'):direct(g,p,60)
    if 'G-S06' in e:
        pairs=min(w,m);g.progression['counters']['fountain']+=max(0,pairs-c['fountain_pairs']);c['fountain_pairs']=pairs
    p[kind+'_wait']=cooldown(g,p,kind)
    flush_fountain(g)

def flush_fountain(g):
    c=g.progression['counters']
    if c['fountain']>=3 and g.last_update>=c['fountain_at'] and not c['pending_fertilizer']:
        c['fountain']-=3;c['fountain_at']=g.last_update+DAY;c['pending_fertilizer']=1
    if c['pending_fertilizer'] and g.fertilizer<5 and not g.vacation:
        g.fertilizer+=1;c['pending_fertilizer']=0

def fertilizer_limit(g,p):return p['duration']*(.26 if 'P-C10' in ids(g,p) else .25)

def use_fertilizer(g,p):
    c=crop(g,p);e=ids(g,p)
    remaining=max(0,fertilizer_limit(g,p)-c['fertilizer'])
    if remaining<=1e-6:return False
    free='P-S03' in e and p['fertilizer_used']==0
    base=min(600,remaining,p['duration']-p['growth'])
    extra=600*modifier(FERTILIZER,g,p)
    if 'G-B25' in e and waters(p)>=3 and flag(c,'bridge_fert'):extra+=60
    extra=min(extra,max(0,remaining-base),max(0,p['duration']-p['growth']-base),max(0,p['duration']*.1-c['direct']))
    if base+extra<=0:return False
    if not free:
        g.fertilizer-=1
        if g.fertilizer_reserve:g.fertilizer_reserve-=1;g.fertilizer+=1
    p['fertilizer_used']+=1;p['growth']+=base+extra
    c['fertilizer']+=base+extra;c['direct']+=extra;c['care_saved']+=base+extra
    if 'fert_charge' in c['flags']:c['flags'].remove('fert_charge')
    flush_fountain(g)
    return True

def after_harvest(g,p,item):
    c=crop(g,p)
    if c and c['ids'] and not p['is_tutorial']:
        e=set(c['ids']);bonus=modifier(SALES,g,p)
        slot=g.progression['slots'][g.selected]
        if 'P-S04' in e:
            sequence=slot['sequence']
            if p['species'] in sequence:sequence.clear()
            sequence.append(p['species']);bonus+=.05*len(sequence)
            if len(sequence)==3:g.sunlight+=1;sequence.clear()
        else:slot['sequence'].clear()
        units=round(p['base_sale_g']*min(.25,bonus)*10000)
        c['sale_units']=units%10000
        item['bonus_g']+=units//10000
        if 'G-C12' in e and p['misted']:g.coins+=1
        if 'P-A05' in e and p['species']=='daisy':g.sunlight+=1
        if 'P-B06' in e:
            from .plant_catalog import plant_definition
            price=20 if 'mystery' in c['flags'] else plant_definition(p['species']).seed_price
            money(g,round(min(2,price*.05)*10000))
    g.progression['slots'][g.selected]['previous']=p['species']
    if p['species'] not in g.progression['first_harvest']:g.progression['first_harvest'].append(p['species'])

def money(g,units):
    total=g.progression['fraction']+units
    g.coins+=total//10000;g.progression['fraction']=total%10000

def garden_id(g):return BY_ID['garden',g.equipped_theme]['design_id']
def sun_cap(g):return 9+{'G-C23':1,'G-B29':3,'G-S07':5}.get(garden_id(g),0)
def sun_period(g,item,first=False):
    key=garden_id(g);reduction=0.0
    if key=='G-S05' and decor(g):reduction=.08
    if key=='G-A13' and len(g.sun_tokens)>=5:reduction=.1
    if key=='G-B08' and item['species']=='daisy':reduction=.06
    if key=='G-B27' and display_diversity(g)>=3:reduction=.05
    if key=='G-B28' and 1<=len(g.collection)<=5:reduction=.07
    c=g.progression['crops'].get(item['id'])
    if first and c and 'G-C11' in c['ids']:reduction+=.1
    return 1200*(1-min(.15,reduction))

def minigame_parameters(g):
    e=ids(g,g.pot)
    return dict(mist_clicks=2 if 'P-C06' in e else 3,mist_frames=12,mist_interval=20 if 'P-C12' in e else 25,
                fertilizer_width=1.05 if 'P-C16' in e else 1.0)

def validate(g):
    """Effect progress is save data, including after a crop enters the garden."""
    import math
    from .plant_catalog import plant_definition
    active={p['plant_id']:p for p in g.pots if p['planted']}
    flowers={x['id']:x for x in g.collection}
    for key,c in g.progression['crops'].items():
        if not isinstance(c,dict) or set(c)!=set(new_crop()) or type(c['version']) is not int or c['version']!=1:raise ValueError('효과 저장 항목')
        if not isinstance(c['ids'],list) or len(c['ids']) not in (0,2) or any(type(x) is not str or x not in SUPPORTED for x in c['ids']):raise ValueError('효과 ID')
        if c['ids']:
            if c['theme'] not in g.owned_themes or c['skin'] not in g.owned_skins or c['ids']!=[BY_ID['garden',c['theme']]['design_id'],BY_ID['pot',c['skin']]['design_id']]:raise ValueError('효과 출처')
        elif c['theme'] is not None or c['skin'] is not None:raise ValueError('미급수 효과')
        if type(c['slot']) is not int or not 0<=c['slot']<len(g.pots):raise ValueError('효과 슬롯')
        if not isinstance(c['flags'],list) or any(type(x) is not str or len(x)>100 for x in c['flags']) or len(set(c['flags']))!=len(c['flags']):raise ValueError('효과 플래그')
        if not isinstance(c['history'],list) or len(c['history'])>3 or any(x not in ('water','mist') for x in c['history']):raise ValueError('돌봄 순서')
        numeric=('direct','stage_direct','fertilizer','care_saved','offline','since_water','since_mist')
        if any(type(c[x]) not in (int,float) or not math.isfinite(c[x]) or c[x]<0 for x in numeric):raise ValueError('효과 수치')
        if any(type(c[x]) is not int or c[x]<0 for x in ('pairs','fountain_pairs','spray_waters','spray_boosts','charges','sale_units')) or c['sale_units']>=10000 or c['charges']>1:raise ValueError('효과 횟수')
        if type(c['offline_bloom']) is not bool:raise ValueError('오프라인 개화')
        if key in active:
            p=active[key]
            if bool(c['ids'])!=p['initial_watered'] or c['slot']!=g.pots.index(p):raise ValueError('재배 효과 연결')
            if bool(c['fertilizer'])!=bool(p['fertilizer_used']):raise ValueError('비료 효과 연결')
        if not isinstance(c['qualified'],dict) or any(x not in ('G-S04','G-S05','G-B19','G-B26') or type(v) not in (int,float) or not math.isfinite(v) or v<0 for x,v in c['qualified'].items()):raise ValueError('자격 성장량')
        duration=active[key]['duration'] if key in active else plant_definition(flowers[key]['species']).growth_seconds
        if c['direct']>duration*.1+1e-5 or c['stage_direct']>duration*.01+1e-5 or c['fertilizer']>duration*.26+1e-5 or any(v>duration+1e-5 for v in c['qualified'].values()):raise ValueError('효과 단축 상한')
    for c in g.progression['sun_cycles'].values():
        if not isinstance(c,dict) or set(c)!={'elapsed','period','first','theme'} or type(c['first']) is not bool or c['theme'] not in g.owned_themes:raise ValueError('햇빛 주기')
        if any(type(c[k]) not in (int,float) or not math.isfinite(c[k]) for k in ('elapsed','period')) or not 1020<=c['period']<=1200 or not 0<=c['elapsed']<c['period']:raise ValueError('햇빛 주기 범위')
