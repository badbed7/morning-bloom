"""Paged cosmetic choices: legacy shop offers plus items the player acquired."""
from PySide6.QtWidgets import QPushButton
from .icon_picker import IconPicker
from .navigation import chevron_icon


class CosmeticPicker(IconPicker):
    def __init__(self,choices):
        super().__init__(choices)
        self.page=0
        self.previous=QPushButton(self);self.next=QPushButton(self)
        for button,direction,name in ((self.previous,-1,'이전 꾸미기'),(self.next,1,'다음 꾸미기')):
            button.setFixedWidth(22);button.setStyleSheet('padding:0;')
            button.setIcon(chevron_icon(direction));button.setAccessibleName(name)
            button.clicked.connect(lambda checked=False,step=direction:self.change_page(step))
        self.layout().insertWidget(0,self.previous);self.layout().addWidget(self.next)
        self.layout().setSpacing(4)
        self.selectionChanged.connect(self.reveal_selected)
        self.show_page()

    @property
    def page_size(self):return 4 if len(self.buttons)<=4 else 3

    def show_page(self):
        pages=(len(self.buttons)+self.page_size-1)//self.page_size
        self.page=min(self.page,pages-1)
        for index,button in enumerate(self.buttons.values()):button.setVisible(index//self.page_size==self.page)
        for button in (self.previous,self.next):
            button.setVisible(pages>1);button.setToolTip(f'꾸미기 {self.page+1} / {pages}쪽')
        self.previous.setEnabled(self.page>0);self.next.setEnabled(self.page<pages-1)

    def reveal_selected(self):
        self.page=list(self.buttons).index(self.selected)//self.page_size
        self.show_page()

    def change_page(self,step):
        target=self.page+step
        if 0<=target<=(len(self.buttons)-1)//self.page_size:
            list(self.buttons.values())[target*self.page_size].setChecked(True)
            self.reveal_selected();self.selectionChanged.emit()

    def replace_choices(self,choices,preferred):
        for button in self.buttons.values():
            self.group.removeButton(button);self.layout().removeWidget(button)
            button.hide();button.deleteLater()
        self.buttons={}
        for key,label,icon in choices:self.add_choice(key,label,icon,self.layout().indexOf(self.next))
        self.buttons[preferred].setChecked(True);self.reveal_selected()
