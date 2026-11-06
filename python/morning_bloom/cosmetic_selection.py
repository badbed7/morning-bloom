"""Choose owned pot shapes and independent colors for a specific plant instance."""
from functools import lru_cache

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from .cosmetics import THEMES, POT_SKINS, colored_pot_skin
from .pot_colors import pot_color_name, valid_pot_color, normalize_pot_color
from .pot_preview import PotPreview
from .pot_color_selection import PotColorSelection, swatch_icon
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
        self._color_dialog = None
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
            self.color_button = QPushButton()
            self.color_button.setFixedHeight(30)
            self.color_button.setMinimumWidth(0)
            self.color_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            self.color_button.clicked.connect(self.open_colors)
            preview_row.addWidget(self.color_button, 1)
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
        self.status.setText(name + (' · ' + pot_color_name(self.selected_color) if self.planting else '') +
                            (' · 보유' if valid else ' · 미보유 · 상점 또는 뽑기에서 획득하세요'))
        self.apply_button.setEnabled(valid)
        if self.planting:
            self.color_button.setText('색상 · ' + pot_color_name(self.selected_color))
            style = colored_pot_skin(self.selected, self.selected_color)
            self.color_button.setIcon(swatch_icon(style.body or plant_definition(species).pot_color))
            self.color_button.setToolTip('색상 선택 · ' + pot_color_name(self.selected_color))
            self.hint.setText(self.plant_name() + ' · 화분을 골라 담아 보세요')
            self.preview.show_choice(species, self.selected, self.selected_color, self.target() is not None, stage=self.preview_stage())
        else:
            self.hint.setText('보유한 정원을 골라 적용하세요 · 미보유 항목은 흑백이에요')

    def select(self, key):
        self.selected = key
        self.sync()
        if self.planting:
            self.preview.show_choice(self.species(), self.selected, self.selected_color, self.target() is not None, animate=True, stage=self.preview_stage())

    def open_colors(self):
        if self._color_dialog is not None:
            self._color_dialog.raise_()
            return
        dialog = PotColorSelection(self, self.selected_color, self.species(), self.selected,
                                   self.target() is not None, self.preview_stage())
        self._color_dialog = dialog
        dialog.accepted.connect(lambda: self.select_color(dialog.selected_color))
        dialog.finished.connect(lambda _: setattr(self, '_color_dialog', None))
        dialog.open()

    def select_color(self, color):
        if not valid_pot_color(color):
            return False
        self.selected_color = normalize_pot_color(color)
        self.sync()
        self.preview.show_choice(self.species(), self.selected, self.selected_color,
                                 self.target() is not None, animate=True, stage=self.preview_stage())
        return True

    def done(self, result):
        if self._color_dialog is not None:
            self._color_dialog.reject()
        super().done(result)

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
