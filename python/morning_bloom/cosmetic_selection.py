"""Owned-first cosmetic selection shared by the garden and planting screens."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QToolButton, QVBoxLayout, QWidget)

from .cosmetics import THEMES, POT_SKINS
from .locked_catalog import COLLECTIONS, preview_image


class CosmeticSelection(QDialog):
    def __init__(self, owner, category, *, planting=False):
        super().__init__(owner)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.owner, self.category, self.planting = owner, category, planting
        self.slot = owner.garden.selected
        self.setWindowTitle('심을 화분 고르기' if planting else '정원 고르기')
        self.setWindowModality(Qt.WindowModal)
        self.resize(owner.width(), max(320, owner.height()))
        self.setMinimumSize(300, 300)
        self.selected = (owner._plant_skin_choices.get(self.slot, owner.garden.current_skin)
                         if planting else owner.garden.equipped_theme)
        layout = QVBoxLayout(self)
        self.hint = QLabel('보유한 항목을 선택하세요 · 미보유 항목은 흑백으로 표시해요')
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.grid = QGridLayout(self.content)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.apply_button = QPushButton('이 화분 선택' if planting else '정원 적용')
        self.apply_button.clicked.connect(self.apply)
        cancel = QPushButton('취소')
        cancel.clicked.connect(self.reject)
        row.addWidget(self.apply_button)
        row.addWidget(cancel)
        layout.addLayout(row)
        self.buttons = {}
        self._signature = None
        self.sync()

    def sync(self):
        garden = self.owner.garden
        owned = garden.owned_skins if self.planting else garden.owned_themes
        equipped = (self.owner._plant_skin_choices.get(self.slot, garden.pot_skins[self.slot])
                    if self.planting else garden.equipped_theme)
        items = COLLECTIONS[self.category]
        self.ordered_keys = [item.key for item in sorted(items, key=lambda item: item.key not in owned)]
        columns = 2 if self.width() < 440 else 3
        signature = (tuple(owned), equipped, columns)
        if signature != self._signature:
            self._signature = signature
            for button in self.buttons.values():
                self.grid.removeWidget(button)
                button.hide()
                button.deleteLater()
            self.buttons.clear()
            by_key = {item.key: item for item in items}
            for index, key in enumerate(self.ordered_keys):
                item = by_key[key]
                image = preview_image(item).scaled(QSize(88, 62), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                if key not in owned:
                    image = image.convertToFormat(QImage.Format_ARGB32)
                    for y in range(image.height()):
                        for x in range(image.width()):
                            color = image.pixelColor(x, y)
                            gray = (color.red()*11 + color.green()*16 + color.blue()*5) // 32
                            image.setPixelColor(x, y, QColor(gray, gray, gray, color.alpha()))
                button = QToolButton()
                button.setCheckable(True)
                button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                button.setIcon(QIcon(QPixmap.fromImage(image)))
                button.setIconSize(QSize(88, 62))
                button.setMinimumHeight(112)
                button.setMinimumWidth(0)
                state = '선택 중' if key == equipped else '보유' if key in owned else '미보유'
                button.setText(f'{item.name}\n{state}')
                button.setToolTip(f'{item.name} · {state}')
                button.setAccessibleName(button.toolTip())
                button.clicked.connect(lambda checked=False, choice=key: self.select(choice))
                self.buttons[key] = button
                self.grid.addWidget(button, index // columns, index % columns)
            rows = (len(self.ordered_keys) + columns - 1) // columns
            margins = self.grid.contentsMargins()
            self.content.setMinimumHeight(rows * 112 + max(0, rows-1) * self.grid.verticalSpacing()
                                          + margins.top() + margins.bottom())
            self.grid.activate()
        for key, button in self.buttons.items():
            button.setChecked(key == self.selected)
        catalog = POT_SKINS if self.planting else THEMES
        valid = self.selected in owned
        name = catalog[self.selected].name if self.selected in catalog else ''
        self.status.setText(name + (' · 보유' if valid else ' · 미보유 · 상점 또는 뽑기에서 획득하세요'))
        self.apply_button.setEnabled(valid)

    def select(self, key):
        self.selected = key
        self.sync()

    def apply(self):
        garden = self.owner.garden
        if self.planting:
            if self.slot != garden.selected or garden.planted or self.selected not in garden.owned_skins:
                return
            self.owner._plant_skin_choices[self.slot] = self.selected
            self.owner.refresh()
            self.accept()
        elif self.owner.act(lambda: garden.equip_theme(self.selected)):
            self.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'buttons'):
            self.sync()
