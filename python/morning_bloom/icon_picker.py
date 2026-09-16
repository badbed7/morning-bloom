"""Exclusive icon choices with the same keyboard and focus behavior throughout the shop."""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QSizePolicy, QToolButton, QWidget


class IconPicker(QWidget):
    selectionChanged = Signal()

    def __init__(self, choices):
        super().__init__()
        self.buttons = {}
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.setFixedHeight(76)
        self.setMinimumWidth(0)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for key, label, icon in choices:
            button = QToolButton()
            button.setObjectName('iconChoice')
            button.setProperty('choice', key)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setText(label)
            button.setIcon(icon)
            button.setIconSize(QSize(36, 40))
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            button.setMinimumWidth(0)
            self.group.addButton(button)
            self.buttons[key] = button
            layout.addWidget(button, 1)
        next(iter(self.buttons.values())).setChecked(True)
        self.group.buttonClicked.connect(lambda _: self.selectionChanged.emit())

    @property
    def selected(self):
        return self.group.checkedButton().property('choice')
