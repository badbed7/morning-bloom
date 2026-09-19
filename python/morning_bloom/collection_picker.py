"""Compact collection picker opened from the growing-pot page."""
from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
)

from .flower_art import paint_collection_flower
from .plant_catalog import plant_definition


class FlowerList(QListWidget):
    menuRequested = Signal(str, QPoint)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos()) or self.currentItem()
        if item is None:
            return
        self.setCurrentItem(item)
        position = event.globalPos()
        if event.reason() == QContextMenuEvent.Keyboard:
            position = self.viewport().mapToGlobal(self.visualItemRect(item).center())
        self.menuRequested.emit(item.data(Qt.UserRole), position)
        event.accept()


class CollectionPicker(QDialog):
    """A read-only view of collected flowers with explicit floating actions."""

    def __init__(self, parent, garden, request_callback, live_ids_callback):
        super().__init__(parent, Qt.Tool)
        self.garden = garden
        self.request_callback = request_callback
        self.live_ids_callback = live_ids_callback
        self._signature = None
        self.setWindowTitle('보관한 꽃')
        self.setMinimumSize(280, 220)
        self.resize(300, 260)
        self.setModal(False)

        layout = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setObjectName('section')
        layout.addWidget(self.summary)
        self.empty = QLabel('아직 보관한 꽃이 없어요.\n핀 꽃을 정원에 보관해 보세요.')
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty, 1)
        self.list = FlowerList()
        self.list.setViewMode(QListView.IconMode)
        self.list.setMovement(QListView.Static)
        self.list.setResizeMode(QListView.Adjust)
        self.list.setWrapping(True)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setIconSize(QSize(72, 82))
        self.list.setGridSize(QSize(90, 116))
        self.list.setSpacing(2)
        self.list.menuRequested.connect(self.show_item_menu)
        layout.addWidget(self.list, 1)
        close = QPushButton('닫기')
        close.clicked.connect(self.hide)
        layout.addWidget(close)
        self.sync(force=True)

    def _icon(self, item):
        ratio = self.devicePixelRatioF()
        pixmap = QPixmap(round(72 * ratio), round(82 * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        paint_collection_flower(
            painter,
            QRectF(0, 0, 72, 82),
            plant_definition(item['species']),
            skin=self.garden.equipped_skin,
        )
        painter.end()
        return QIcon(pixmap)

    def sync(self, force=False):
        requested = set(self.garden.desktop_flowers)
        floating = set(self.live_ids_callback())
        signature = (
            tuple((item['id'], item['species']) for item in self.garden.collection),
            tuple(sorted(requested)),
            tuple(sorted(floating)),
            self.garden.equipped_skin,
        )
        if not force and signature == self._signature:
            return
        selected = self.list.currentItem()
        selected_id = selected.data(Qt.UserRole) if selected else None
        self._signature = signature
        self.list.clear()
        for item in self.garden.collection:
            definition = plant_definition(item['species'])
            list_item = QListWidgetItem(self._icon(item), definition.name)
            list_item.setData(Qt.UserRole, item['id'])
            state = ('바탕화면 표시 중' if item['id'] in floating else
                     '표시 복원 대기' if item['id'] in requested else '정원 보관 중')
            price = item['base_sale_g'] + item['bonus_g']
            list_item.setToolTip(f'{definition.name} · 판매 {price}G · {state}\n우클릭해 표시 위치를 바꿉니다.')
            list_item.setData(Qt.AccessibleTextRole, f'{definition.name} · {state}')
            self.list.addItem(list_item)
            if item['id'] == selected_id:
                self.list.setCurrentItem(list_item)
        count = len(self.garden.collection)
        self.summary.setText(f'보관한 꽃 · {count}개')
        self.empty.setVisible(count == 0)
        self.list.setVisible(count > 0)

    def show_item_menu(self, item_id, global_position):
        if not any(item['id'] == item_id for item in self.garden.collection):
            self.sync(force=True)
            return
        requested = item_id in self.garden.desktop_flowers
        floating = item_id in self.live_ids_callback()
        menu = QMenu(self)
        if requested and not floating:
            retry = menu.addAction('다시 띄우기')
            return_action = menu.addAction('정원으로 돌려놓기')
            selected = menu.exec(global_position)
            if selected is retry:
                self.apply_action(item_id, True)
            elif selected is return_action:
                self.apply_action(item_id, False)
            return
        action = menu.addAction('정원으로 돌려놓기' if requested else '바탕화면에 띄우기')
        if menu.exec(global_position) is action:
            self.apply_action(item_id, not requested)

    def apply_action(self, item_id, floating):
        if not any(item['id'] == item_id for item in self.garden.collection):
            self.sync(force=True)
            return False
        result = self.request_callback(item_id, floating)
        self.sync(force=True)
        return result
