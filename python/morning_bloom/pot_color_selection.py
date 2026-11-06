"""Categorized swatches and custom RGB, staged until the pot dialog is applied."""
from functools import lru_cache
import re

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QColorDialog, QComboBox, QDialog,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from .cosmetics import colored_pot_skin
from .plant_catalog import plant_definition
from .pot_colors import (LEGACY_POT_COLORS, POT_COLOR_GROUPS, RECOMMENDED_COLORS,
                         normalize_pot_color, pot_color_hex, pot_color_name, valid_pot_color)
from .pot_preview import PotPreview


@lru_cache(maxsize=256)
def swatch_icon(rgb):
    pixmap = QPixmap(24, 18)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor('#9b8e7a'), 1))
    painter.setBrush(QColor(rgb))
    painter.drawRoundedRect(QRectF(1, 1, 22, 16), 3, 3)
    painter.end()
    return QIcon(pixmap)


class ColorSwatch(QAbstractButton):
    def __init__(self, key, base_color, parent=None):
        super().__init__(parent)
        self.key = key
        self.rgb = pot_color_hex(key) or base_color
        self.name = pot_color_name(key)
        self.setCheckable(True)
        self.setMinimumWidth(0)
        self.setFixedHeight(64)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip(f'{self.name} · {self.rgb.upper()}' + (' · 화분 원래 색상' if key == 'original' else ''))
        self.setAccessibleName(self.toolTip())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor('#edf0e3' if self.isChecked() else '#fffaf1'))
        painter.setPen(QPen(QColor('#4d6b4b' if self.isChecked() or self.hasFocus() else '#d9cbb7'), 2 if self.isChecked() else 1))
        painter.drawRoundedRect(QRectF(1, 1, self.width()-2, self.height()-2), 5, 5)
        painter.setBrush(QColor(self.rgb))
        painter.setPen(QPen(QColor('#9b8e7a'), .7))
        painter.drawRoundedRect(QRectF(7, 6, self.width()-14, 22), 3, 3)
        if self.isChecked():
            painter.setPen(QPen(QColor('#fffaf2' if QColor(self.rgb).lightnessF() < .55 else '#354832'), 2))
            center = self.width()/2
            painter.drawLine(round(center-5), 16, round(center-1), 20)
            painter.drawLine(round(center-1), 20, round(center+6), 12)
        font = painter.font()
        font.setPixelSize(11)
        painter.setFont(font)
        painter.setPen(QColor('#514638'))
        painter.drawText(QRectF(3, 30, self.width()-6, 31), Qt.AlignCenter | Qt.TextWordWrap, self.name)
        painter.end()


class PotColorSelection(QDialog):
    def __init__(self, parent, color, species, skin, planted, stage):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle('화분 색상 고르기')
        self.setWindowModality(Qt.WindowModal)
        self.resize(parent.width(), max(400, parent.height()))
        self.setMinimumSize(300, 300)
        self.selected_color = normalize_pot_color(color)
        self.species, self.skin, self.planted, self.stage = species, skin, planted, stage
        self.base_color = colored_pot_skin(skin).body or plant_definition(species).pot_color
        self.valid = True
        self._picker = None
        self.swatches = {}
        outer = QVBoxLayout(self)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(4, 4, 4, 4)
        body.setSpacing(5)
        preview_content = QWidget()
        preview_content.setFixedHeight(76)
        preview_row = QHBoxLayout(preview_content)
        preview_row.setContentsMargins(0, 0, 0, 0)
        self.preview = PotPreview()
        preview_row.addWidget(self.preview)
        self.color_label = QLabel()
        self.color_label.setWordWrap(True)
        self.color_label.setMinimumWidth(0)
        self.color_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        preview_row.addWidget(self.color_label, 1)
        body.addWidget(preview_content)
        self.groups = {'추천': RECOMMENDED_COLORS, **POT_COLOR_GROUPS, '이전 색상': tuple(LEGACY_POT_COLORS)}
        self.category = QComboBox()
        self.category.addItems(self.groups)
        self.category.setAccessibleName('화분 색상 카테고리')
        self.category.setToolTip('추천 · 뉴트럴 · 어스톤 · 파스텔 · 딥 · 이전 색상')
        group = next((group for group, keys in POT_COLOR_GROUPS.items() if color in keys),
                     '이전 색상' if color in LEGACY_POT_COLORS and color != 'original' else '추천')
        self.category.setCurrentText(group)
        body.addWidget(self.category)
        self.swatch_content = QWidget()
        self.swatch_grid = QGridLayout(self.swatch_content)
        self.swatch_grid.setContentsMargins(0, 0, 0, 0)
        self.swatch_grid.setSpacing(4)
        body.addWidget(self.swatch_content)
        custom_row = QHBoxLayout()
        self.hex_input = QLineEdit()
        self.hex_input.setPlaceholderText('#RRGGBB')
        self.hex_input.setMaxLength(64)
        self.hex_input.setMinimumWidth(0)
        self.hex_input.setAccessibleName('화분 사용자 지정 HEX 색상')
        self.hex_input.setToolTip('6자리 RGB 색상 · 예: #A3AA91 · # 생략 가능')
        custom_row.addWidget(self.hex_input, 1)
        self.picker_button = QPushButton('컬러 피커')
        self.picker_button.clicked.connect(self.open_picker)
        custom_row.addWidget(self.picker_button)
        body.addLayout(custom_row)
        self.error = QLabel()
        self.error.setObjectName('small')
        self.error.setFixedHeight(18)
        self.error.setStyleSheet('color:#9a4e42;font-size:11px;')
        body.addWidget(self.error)
        body.addStretch()
        self.scroll.setWidget(content)
        outer.addWidget(self.scroll, 1)
        footer = QHBoxLayout()
        self.use_button = QPushButton('이 색상 사용')
        self.use_button.clicked.connect(self.accept)
        cancel = QPushButton('취소')
        cancel.clicked.connect(self.reject)
        footer.addWidget(self.use_button)
        footer.addWidget(cancel)
        outer.addLayout(footer)
        self.category.currentTextChanged.connect(self.build_swatches)
        self.hex_input.textChanged.connect(self.edit_hex)
        self.hex_input.returnPressed.connect(lambda: self.accept() if self.valid else None)
        self.build_swatches()
        self.select_color(self.selected_color)

    def build_swatches(self):
        for button in self.swatches.values():
            self.swatch_grid.removeWidget(button)
            button.hide()
            button.deleteLater()
        self.swatches.clear()
        for index, key in enumerate(self.groups[self.category.currentText()]):
            button = ColorSwatch(key, self.base_color)
            button.clicked.connect(lambda checked=False, choice=key: self.select_color(choice))
            self.swatch_grid.addWidget(button, index // 4, index % 4)
            self.swatches[key] = button
            button.setChecked(key == self.selected_color)
        rows = (len(self.swatches)+3)//4
        self.swatch_content.setFixedHeight(rows*64 + max(0, rows-1)*4)

    def select_color(self, color, *, update_input=True):
        if not valid_pot_color(color):
            return False
        self.selected_color = normalize_pot_color(color)
        self.valid = True
        self.error.clear()
        self.use_button.setEnabled(True)
        rgb = pot_color_hex(self.selected_color)
        if update_input:
            self.hex_input.blockSignals(True)
            self.hex_input.setText(rgb.upper() if rgb else '')
            self.hex_input.blockSignals(False)
        self.color_label.setText(pot_color_name(self.selected_color) + '\n' +
                                 (rgb.upper() if rgb else '화분 원래 색상'))
        for key, button in self.swatches.items():
            button.setChecked(key == self.selected_color)
        self.preview.show_choice(self.species, self.skin, self.selected_color, self.planted,
                                 animate=True, stage=self.stage)
        return True

    def edit_hex(self, text):
        candidate = text.strip()
        if re.fullmatch(r'[0-9a-fA-F]{6}', candidate):
            candidate = '#' + candidate
        if re.fullmatch(r'#[0-9a-fA-F]{6}', candidate):
            self.select_color(candidate, update_input=False)
        else:
            self.valid = False
            self.use_button.setEnabled(False)
            self.error.setText('HEX는 #RRGGBB 형식으로 입력하세요.')

    def open_picker(self):
        if self._picker is not None:
            self._picker.raise_()
            return
        picker = QColorDialog(QColor(pot_color_hex(self.selected_color) or self.base_color), self)
        self._picker = picker
        picker.setAttribute(Qt.WA_DeleteOnClose)
        picker.setWindowModality(Qt.WindowModal)
        picker.setOption(QColorDialog.DontUseNativeDialog, True)
        picker.setWindowTitle('화분 사용자 색상')
        picker.colorSelected.connect(lambda color: self.select_color(color.name()) if color.isValid() else None)
        picker.finished.connect(lambda _: setattr(self, '_picker', None))
        picker.open()

    def accept(self):
        if self.valid and valid_pot_color(self.selected_color):
            super().accept()

    def done(self, result):
        if self._picker is not None:
            self._picker.reject()
        super().done(result)
