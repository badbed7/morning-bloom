"""Choose owned pot shapes and independent colors for a specific plant instance."""
from functools import lru_cache

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget)

from .cosmetics import POT_COLORS, THEMES, POT_SKINS
from .flower_art import paint_collection_flower, paint_potted_flower
from .locked_catalog import COLLECTIONS, preview_image
from .plant_catalog import PLANTS, plant_definition
from .model import growth_stage


@lru_cache(maxsize=1024)
def choice_image(category, key, color, species, owned):
    if category == '화분':
        image = QImage(88, 62, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(.65, .65)
        painter.translate(-122, -88)
        paint_potted_flower(painter, plant_definition(species), planted=False, skin=key, pot_color=color)
        painter.end()
    else:
        item = next(item for item in COLLECTIONS[category] if item.key == key)
        image = preview_image(item).scaled(QSize(88, 62), Qt.KeepAspectRatio, Qt.SmoothTransformation)
    if not owned:
        image = image.convertToFormat(QImage.Format_ARGB32)
        for y in range(image.height()):
            for x in range(image.width()):
                pixel = image.pixelColor(x, y)
                gray = (pixel.red()*11 + pixel.green()*16 + pixel.blue()*5) // 32
                image.setPixelColor(x, y, QColor(gray, gray, gray, pixel.alpha()))
    return image


class PotPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(110, 76)
        self.choice = None
        self.progress = 1.0
        self.effect = QVariantAnimation(self)
        self.effect.setDuration(240)
        self.effect.setEasingCurve(QEasingCurve.OutCubic)
        self.effect.valueChanged.connect(self.animate)

    def animate(self, value):
        self.progress = float(value)
        self.update()

    def show_choice(self, species, skin, color, planted, animate=False, stage=4):
        self.choice = species, skin, color, planted, stage
        if animate:
            self.effect.stop()
            self.effect.setStartValue(0.0)
            self.effect.setEndValue(1.0)
            self.effect.start()
        else:
            self.update()

    def paintEvent(self, event):
        if self.choice is None:
            return
        species, skin, color, planted, stage = self.choice
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(0, -(1-self.progress)*7)
        if planted:
            paint_collection_flower(painter, QRectF(0, 0, self.width(), self.height()), plant_definition(species),
                                    skin=skin, pot_color=color, stage=stage)
        else:
            scale = .75
            painter.translate(self.width()/2 - 190*scale, -62)
            painter.scale(scale, scale)
            paint_potted_flower(painter, plant_definition(species), planted=False, skin=skin, pot_color=color)
        painter.end()


class CosmeticSelection(QDialog):
    def __init__(self, owner, category, *, planting=False, item_id=None):
        super().__init__(owner)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.owner, self.category, self.planting = owner, category, planting
        self.slot, self.item_id = owner.garden.selected, item_id
        self.setWindowTitle('식물 화분 꾸미기' if planting else '정원 고르기')
        self.setWindowModality(Qt.WindowModal)
        self.resize(owner.width(), max(320, owner.height()))
        self.setMinimumSize(300, 300)
        current = self.current_style()
        self.selected = current['skin'] if planting else owner.garden.equipped_theme
        self.selected_color = current['color']
        layout = QVBoxLayout(self)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.grid = QGridLayout(self.content)
        if planting:
            self.scroll_body = QWidget()
            body = QVBoxLayout(self.scroll_body)
            body.setContentsMargins(0, 0, 0, 0)
            preview_row = QHBoxLayout()
            self.preview = PotPreview()
            preview_row.addWidget(self.preview)
            self.color_picker = QComboBox()
            for key, (name, value) in POT_COLORS.items():
                self.color_picker.addItem('색상 · ' + name, key)
            self.color_picker.setCurrentIndex(self.color_picker.findData(self.selected_color))
            self.color_picker.setAccessibleName('이 식물의 화분 색상')
            preview_row.addWidget(self.color_picker, 1)
            body.addLayout(preview_row)
            body.addWidget(self.content)
            self.scroll.setWidget(self.scroll_body)
        else:
            self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.apply_button = QPushButton('이 화분에 담기' if planting else '정원 적용')
        self.apply_button.clicked.connect(self.apply)
        cancel = QPushButton('취소')
        cancel.clicked.connect(self.reject)
        row.addWidget(self.apply_button)
        row.addWidget(cancel)
        layout.addLayout(row)
        self.buttons = {}
        self._signature = None
        if planting:
            self.color_picker.currentIndexChanged.connect(self.change_color)
        self.sync()

    def target(self):
        return self.owner.garden.desktop_source(self.item_id) if self.item_id is not None else None

    def target_exists(self):
        return self.target() is not None if self.item_id is not None else self.slot < len(self.owner.garden.pots)

    def current_style(self):
        garden = self.owner.garden
        if self.item_id is not None:
            return garden.source_pot(self.item_id)
        return {'skin': garden.pot_skins[self.slot], 'color': garden.pot_colors[self.slot]}

    def species(self):
        item = self.target()
        if item is not None:
            return item['species']
        garden = self.owner.garden
        if self.slot >= len(garden.pots):
            return 'daisy'
        selected = garden.pots[self.slot]['species'] or self.owner.species_picker.selected
        return selected if selected in PLANTS else 'daisy'

    def preview_stage(self):
        item = self.target()
        return growth_stage(item) if item is not None and 'plant_id' in item else 4

    def plant_name(self):
        item = self.target()
        if item is None:
            return '빈 화분'
        garden = self.owner.garden
        if self.item_id in garden.mystery_plants and item['growth'] < item['duration']:
            return '랜덤 씨앗'
        name = plant_definition(item['species']).name
        twins = [flower['id'] for flower in garden.collection if flower['species'] == item['species']]
        if self.item_id in twins:
            return f'{name} {twins.index(self.item_id)+1}' if len(twins) > 1 else name
        return f'화분 {self.slot+1} · {name}'

    def sync(self):
        garden = self.owner.garden
        owned = garden.owned_skins if self.planting else garden.owned_themes
        equipped = self.current_style()['skin'] if self.planting else garden.equipped_theme
        items = COLLECTIONS[self.category]
        self.ordered_keys = [item.key for item in sorted(items, key=lambda item: item.key not in owned)]
        columns = 2 if self.width() < 440 else 3
        species = self.species() if self.planting else 'daisy'
        signature = (tuple(owned), equipped, columns, self.selected_color, species)
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
                image = choice_image(self.category, key, self.selected_color, species, key in owned)
                button = QToolButton()
                button.setCheckable(True)
                button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                button.setIcon(QIcon(QPixmap.fromImage(image)))
                button.setIconSize(QSize(88, 62))
                button.setMinimumHeight(112)
                button.setMinimumWidth(0)
                state = '사용 중' if key == equipped else '보유' if key in owned else '미보유'
                button.setText(f'{item.name}\n{state}')
                button.setToolTip(f'{item.name} · {state}')
                button.setAccessibleName(button.toolTip())
                button.clicked.connect(lambda checked=False, choice=key: self.select(choice))
                self.buttons[key] = button
                self.grid.addWidget(button, index // columns, index % columns)
            rows = (len(self.ordered_keys) + columns - 1) // columns
            margins = self.grid.contentsMargins()
            height = rows*112 + max(0, rows-1)*self.grid.verticalSpacing() + margins.top()+margins.bottom()
            self.content.setMinimumHeight(height)
            if self.planting:
                self.scroll_body.setMinimumHeight(height + 82)
            self.grid.activate()
        for key, button in self.buttons.items():
            button.setChecked(key == self.selected)
        catalog = POT_SKINS if self.planting else THEMES
        valid = self.selected in owned and (not self.planting or self.target_exists())
        name = catalog[self.selected].name if self.selected in catalog else ''
        self.status.setText(name + (' · ' + POT_COLORS[self.selected_color][0] if self.planting else '') +
                            (' · 보유' if valid else ' · 미보유 · 상점 또는 뽑기에서 획득하세요'))
        self.apply_button.setEnabled(valid)
        if self.planting:
            self.hint.setText(self.plant_name() + ' · 화분을 골라 담아 보세요')
            self.preview.show_choice(species, self.selected, self.selected_color, self.target() is not None, stage=self.preview_stage())
        else:
            self.hint.setText('보유한 정원을 골라 적용하세요 · 미보유 항목은 흑백이에요')

    def select(self, key):
        self.selected = key
        self.sync()
        if self.planting:
            self.preview.show_choice(self.species(), self.selected, self.selected_color, self.target() is not None, animate=True, stage=self.preview_stage())

    def change_color(self):
        self.selected_color = self.color_picker.currentData()
        self.sync()
        self.preview.show_choice(self.species(), self.selected, self.selected_color, self.target() is not None, animate=True, stage=self.preview_stage())

    def apply(self):
        garden = self.owner.garden
        if self.planting:
            if not self.target_exists():
                self.owner.notify('이 식물은 더 이상 정원에 없어요.', important=True)
                self.reject()
                return
            action = (lambda: garden.set_plant_pot(self.item_id, self.selected, self.selected_color)) if self.item_id is not None else (
                lambda: garden.set_slot_pot(self.slot, self.selected, self.selected_color))
            if self.owner.act(action):
                self.owner.notify(self.plant_name() + ' · 화분을 바꿨어요')
                self.accept()
        elif self.owner.act(lambda: garden.equip_theme(self.selected)):
            self.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'buttons'):
            self.sync()
