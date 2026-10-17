"""Seed Garden Journey: the live board, collection, equipment and exchange."""
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox,QDialog,QFrame,QGridLayout,QHBoxLayout,QLabel,
    QListWidget,QListWidgetItem,QPushButton,QTabWidget,QTextBrowser,QVBoxLayout,QWidget)
from . import board_model as board
from .content import ITEMS,BY_ID,rarity
from .cosmetics import POT_SKINS,THEMES
from .cosmetic_icons import skin_icon,theme_icon
from .plant_catalog import plant_definition
from .seed_picker import seed_packet_icon
from .storage import SaveError

COORDS=((0,0),(0,1),(0,2),(0,3),(0,4),(0,5),(0,6),(1,6),(2,6),(3,6),
        (4,6),(4,5),(4,4),(4,3),(4,2),(4,1),(4,0),(3,0),(2,0),(1,0))
LABELS=dict(plant='씨앗',garden='정원',pot='화분',special='입구')
BASE='background:#f7f2e5;color:#594f3d;'

class BoardWindow(QDialog):
    def __init__(self,owner):
        super().__init__(owner)
        self.owner=owner;self.garden=owner.garden;self.store=owner.store
        self.animating=False;self.special_result=None;self.display_position=None
        self.setWindowTitle('씨앗 정원 여행 · Morning Bloom')
        self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowFlag(Qt.WindowStaysOnTopHint,owner.garden.settings['topmost'])
        self.setWindowOpacity(owner.windowOpacity())
        self.resize(720,620)
        self.setStyleSheet('QDialog{'+BASE+'} QLabel{color:#594f3d;} QPushButton{padding:8px;background:#e2e7d4;border:1px solid #aab396;border-radius:6px;color:#45553d;} QPushButton:disabled{color:#9b9d90;background:#eee9df;} QListWidget,QTextBrowser{background:#fffaf0;color:#594f3d;border:1px solid #d9cdb8;}')
        outer=QVBoxLayout(self)
        heading=QHBoxLayout();title=QLabel('씨앗 정원 여행');title.setStyleSheet('font-size:19px;font-weight:600;')
        self.wallet=QLabel();heading.addWidget(title);heading.addStretch();heading.addWidget(self.wallet);outer.addLayout(heading)
        self.tabs=QTabWidget();outer.addWidget(self.tabs)
        journey=QWidget();journey_layout=QVBoxLayout(journey);self.tabs.addTab(journey,'주사위 여행')
        grid=QGridLayout();grid.setSpacing(5);self.cells=[]
        for index,(row,column) in enumerate(COORDS):
            cell=QLabel();cell.setAlignment(Qt.AlignCenter);cell.setMinimumSize(42,45)
            cell.setAccessibleName(f'{index}번 {LABELS[board.POSITIONS[index]]}');grid.addWidget(cell,row,column);self.cells.append(cell)
        center=QWidget();center_layout=QVBoxLayout(center);center_layout.setContentsMargins(9,6,9,6)
        self.center_title=QLabel('씨앗 · 정원 · 화분');self.center_title.setAlignment(Qt.AlignCenter);center_layout.addWidget(self.center_title)
        self.normal_center=QWidget();normal_layout=QHBoxLayout(self.normal_center)
        for category,icon in (('plant',seed_packet_icon(plant_definition('daisy'))),('garden',theme_icon(THEMES['grass'])),('pot',skin_icon(POT_SKINS['terracotta']))):
            button=QPushButton(LABELS[category]);button.setIcon(icon);button.setIconSize(QSize(38,38));button.clicked.connect(lambda checked=False,c=category:self.open_category(c));normal_layout.addWidget(button)
        center_layout.addWidget(self.normal_center)
        self.special_center=QWidget();special_grid=QGridLayout(self.special_center);self.special_cells=[]
        for index,(grade,category) in enumerate(board.SPECIAL):
            label=QLabel(f'{grade} · {LABELS[category]}');label.setAlignment(Qt.AlignCenter);label.setMinimumHeight(36);special_grid.addWidget(label,index//3,index%3);self.special_cells.append(label)
        center_layout.addWidget(self.special_center);self.special_center.hide()
        grid.addWidget(center,1,1,3,5);journey_layout.addLayout(grid,1)
        self.roll_button=QPushButton();self.roll_button.clicked.connect(self.roll);journey_layout.addWidget(self.roll_button)
        self.result=QLabel('도착 칸에서 보상을 받아요. 좌우 입구는 무료 스페셜 보드로 이어져요.');self.result.setWordWrap(True);self.result.setMinimumHeight(44);journey_layout.addWidget(self.result)
        self.timer=QTimer(self);self.timer.setInterval(90);self.timer.timeout.connect(self.animation_step)
        collection=QWidget();collection_layout=QVBoxLayout(collection);self.tabs.addTab(collection,'도감 · 장착 · 교환')
        exchange_help=QLabel('교환할 미해금 아이템을 선택한 뒤 아래 꽃잎 해금 버튼을 누르세요.\n획득한 화분·정원은 상점의 스킨·배경 목록에도 추가돼요.')
        exchange_help.setWordWrap(True);collection_layout.addWidget(exchange_help)
        filters=QHBoxLayout();self.category=QComboBox();self.grade=QComboBox();self.slot=QComboBox()
        for text,key in (('전체',None),('식물','plant'),('정원','garden'),('화분','pot')):self.category.addItem(text,key)
        for value in ('전체','S','A','B','C'):self.grade.addItem(value)
        filters.addWidget(self.category);filters.addWidget(self.grade);filters.addWidget(QLabel('재배 화분'));filters.addWidget(self.slot);collection_layout.addLayout(filters)
        self.items=QListWidget();self.items.setIconSize(QSize(48,48));collection_layout.addWidget(self.items,1)
        self.detail=QLabel();self.detail.setWordWrap(True);collection_layout.addWidget(self.detail)
        actions=QHBoxLayout();self.equip=QPushButton();self.exchange=QPushButton();actions.addWidget(self.equip);actions.addWidget(self.exchange);collection_layout.addLayout(actions)
        self.category.currentIndexChanged.connect(self.populate);self.grade.currentIndexChanged.connect(self.populate)
        self.slot.currentIndexChanged.connect(self.select_slot);self.items.currentItemChanged.connect(self.show_item)
        self.equip.clicked.connect(self.apply_item);self.exchange.clicked.connect(self.exchange_item)
        self.info=QTextBrowser();self.tabs.addTab(self.info,'확률 · 보상 이력')
        before=self.garden.to_dict()
        if self.garden.claim_weekly(owner.now()) and not owner.persist():self.garden.restore(before)
        self.sync();self.populate()
        saved=self.garden.progression['board']['last_result']
        if saved and not self.garden.progression['board']['special']:self.show_result(saved)

    def owned(self,item):
        return item['item_id'] in (self.garden.progression['unlocked'] if item['category']=='plant' else self.garden.owned_themes if item['category']=='garden' else self.garden.owned_skins)

    def sync(self):
        state=self.garden.progression;b=state['board']
        self.wallet.setText(f"주사위 {state['tickets']} · 꽃잎 {state['petals']}")
        position=b['position'] if self.display_position is None else self.display_position
        for index,cell in enumerate(self.cells):
            kind=board.POSITIONS[index];current=index==position
            cell.setText(('● ' if current else '')+LABELS[kind]+(' ✦' if kind=='special' else ''))
            color='#d6bd8c' if current else '#dbc8df' if kind=='special' else '#e3e9d6' if kind=='garden' else '#eadfc9'
            cell.setStyleSheet(f'background:{color};border-radius:7px;padding:3px;font-size:12px;')
        pending=b['special'] is not None
        special=pending or self.special_result is not None
        self.normal_center.setVisible(not special);self.special_center.setVisible(special)
        self.center_title.setText('스페셜 보드 · A / S' if special else '씨앗 · 정원 · 화분')
        for index,cell in enumerate(self.special_cells):cell.setStyleSheet('background:'+('#dfca9b' if index==self.special_result else '#eee4ed')+';border-radius:6px;padding:4px;')
        self.roll_button.setText('저장 재시도 · 같은 결과 유지' if b['prepared'] else '무료 스페셜 주사위 · 1회' if pending else f"주사위 굴리기 · 1개 사용 ({state['tickets']}개 보유)")
        self.roll_button.setEnabled(not self.animating and bool(b['prepared'] or pending or state['tickets']))
        if pending and not self.animating:self.result.setText('입구에 도착했어요! 주사위 추가 소비 없이 A/S 아이템 하나를 받아요.')
        self.slot.blockSignals(True);self.slot.clear()
        for index in range(len(self.garden.pots)):self.slot.addItem(str(index+1))
        self.slot.setCurrentIndex(self.garden.selected);self.slot.blockSignals(False)
        history='\n'.join(f"{r['seq']} · {r['grade']} {BY_ID[r['category'],r['item_id']]['name']} · {'중복' if r['duplicate'] else '신규'} · 꽃잎 +{r['petals']}" for r in reversed(b['history']))
        self.info.setPlainText('일반 주사위: 1~6 각각 1/6 · 정확히 입구에 멈추면 스페셜 입장\n일반 칸: C 5/9 · B 3/9 · A 1/9 · S 없음\n스페셜: A 씨앗/정원/화분, S 씨앗/정원/화분 각각 1/6\n장기 평균: C 50% · B 30% · A 15% · S 5% (매회 독립 확률 아님)\n주간 지급: 월요일 00:00 한국 시각, 해당 주 첫 진입 5개 · 이월 가능 · 과거 미접속 주 소급 없음\n기본 꽃잎: 보상마다 1 · 중복 추가 C1/B2/A5/S10\n선택 교환: C3/B8/A20/S40 · 미해금 항목만 · 교환 보상은 보드 확률과 별도\n고대 꽃은 랜덤 씨앗 0.1%, 민들레는 홀씨놀이에서 획득\n\n보상 이력 (최근 200개)\n'+history)
        self.show_item()

    def roll(self):
        if self.animating or self.owner._action_busy:return
        self.owner._action_busy=True
        before=self.garden.progression['board']['position'];pending=self.garden.progression['board']['special'] is not None
        try:
            plan=board.transact(self.garden,self.store,'special' if pending else 'roll')
            if not plan:return
            self.special_result=None
            if plan['kind']=='roll':
                self.animating=True;self.display_position=before;self.remaining_steps=plan['die'];self.timer.start()
            else:self.special_result=plan['reward']['die']-1
            path=getattr(self.store,'path',None)
            if path and path.exists():self.owner._local_saved_at=path.stat().st_mtime
            if self.garden.progression['board']['last_result'] is not None and not self.garden.progression['board']['special']:self.show_result(self.garden.progression['board']['last_result'])
            self.sync();self.owner.refresh();self.populate()
        except (SaveError,ValueError,OSError) as exc:
            self.sync();self.result.setText('저장하지 못했어요. 결과는 유지됩니다. '+str(exc))
        finally:self.owner._action_busy=False

    def animation_step(self):
        self.display_position=(self.display_position+1)%20;self.remaining_steps-=1
        if self.remaining_steps==0:
            self.timer.stop();self.animating=False;self.display_position=None
        self.sync()

    def show_result(self,result):
        item=BY_ID[result['category'],result['item_id']]
        self.result.setText(f"{result['grade']} · {item['name']} · {'중복 보상' if result['duplicate'] else '새로 획득!'} · 꽃잎 +{result['petals']}")
        if result['category'] in ('garden','pot'):
            self.result.setText(self.result.text()+'\n상점의 정원 배경·화분 스킨 목록에서 선택해 적용할 수 있어요.')

    def open_category(self,category):
        self.category.setCurrentIndex({'plant':1,'garden':2,'pot':3}[category]);self.tabs.setCurrentIndex(1)

    def populate(self):
        selected=self.items.currentItem().data(Qt.UserRole) if self.items.currentItem() else None
        self.items.blockSignals(True);self.items.clear()
        for item in ITEMS:
            if self.category.currentData() not in (None,item['category']) or self.grade.currentText() not in ('전체',item['grade']):continue
            category,key=item['category'],item['item_id']
            icon=seed_packet_icon(plant_definition(key)) if category=='plant' else theme_icon(THEMES[key]) if category=='garden' else skin_icon(POT_SKINS[key])
            status=('해금' if category=='plant' else '보유') if self.owned(item) else '잠김' if item['board_eligible'] else '별도 획득'
            row=QListWidgetItem(icon,f"{item['grade']} · {item['name']} · {status}");row.setData(Qt.UserRole,(category,key));self.items.addItem(row)
            if selected and list(selected)==[category,key]:self.items.setCurrentItem(row)
        self.items.blockSignals(False)
        if self.items.currentRow()<0 and self.items.count():self.items.setCurrentRow(0)
        self.show_item()

    def selected_item(self):
        row=self.items.currentItem()
        return BY_ID[tuple(row.data(Qt.UserRole))] if row else None

    def show_item(self,*args):
        item=self.selected_item()
        if not item:return
        category,key=item['category'],item['item_id'];owned=self.owned(item)
        detail=item.get('description','')
        if category=='plant':
            plant=plant_definition(key)
            detail=f'성장 {plant.growth_seconds/3600:g}시간 · 씨앗 {plant.seed_price}G · 기본 판매 {plant.sale_price}G\n씨앗 보유 {self.garden.seed_count(key)}개'
            self.equip.setText(f'씨앗 구매 · {plant.seed_price}G');self.equip.setEnabled(owned and item['board_eligible'] and self.garden.coins>=plant.seed_price)
        else:
            detail+='\n'+('정원 전체 적용' if category=='garden' else f'{self.garden.selected+1}번 재배 화분에 장착')+' · 새 재배 첫 물주기부터 효과 적용'
            self.equip.setText('정원에 적용' if category=='garden' else '선택 화분에 장착');self.equip.setEnabled(owned)
        self.detail.setText(f"{item['grade']} · {item['name']}\n{detail}")
        price=board.EXCHANGE[item['grade']];self.exchange.setText(f'꽃잎 {price}개로 해금')
        self.exchange.setEnabled(item['board_eligible'] and not owned and self.garden.progression['petals']>=price)

    def select_slot(self,index):
        if index>=0:self.owner.act(lambda:self.garden.select(index));self.sync()

    def apply_item(self):
        item=self.selected_item()
        if not item:return
        category,key=item['category'],item['item_id']
        action=self.garden.buy_seed if category=='plant' else self.garden.equip_theme if category=='garden' else self.garden.equip_skin
        self.owner.act(lambda:action(key));self.sync();self.populate()

    def exchange_item(self):
        item=self.selected_item()
        if item:self.owner.act(lambda:self.garden.exchange_item(item['category'],item['item_id']));self.sync();self.populate()

    def closeEvent(self,event):
        self.timer.stop();super().closeEvent(event)
