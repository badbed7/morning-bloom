"""A grassy collection of floating pots, with a local-only sale drop target."""
import math

from PySide6.QtCore import QEvent, QMimeData, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QMenu, QScrollArea, QToolTip, QVBoxLayout, QWidget

from .flower_art import paint_collection_flower
from .cosmetics import garden_theme
from .model import SUN_PENDING_CAP
from .plant_catalog import plant_definition

FLOWER_MIME = 'application/x-morning-bloom-flower'


def sale_price(item):
    return item['base_sale_g'] + item['bonus_g']


class Meadow(QWidget):
    dragChanged = Signal(object)
    desktopRequested = Signal(str)
    ROW_HEIGHT = 118

    def __init__(self, garden, collect_callback=None, parent=None):
        super().__init__(parent)
        self.garden = garden
        self.collect_callback = collect_callback
        self.items = []
        self.tokens = []
        self.desktop_ids = set()
        self.bursts = []
        self.phase = 0.0
        self.dragged_id = None
        self._pressed_id = None
        self._pressed_sun_id = None
        self._press_position = QPoint()
        self.setMouseTracking(True)
        self.setAccessibleName('수집한 꽃 정원')
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._animate)
        self.sync()

    @property
    def columns(self):
        return max(2, (self.width() - 16) // 84)

    @property
    def sun_columns(self):
        return max(4, (self.width() - 20) // 38)

    @property
    def sun_height(self):
        return math.ceil(len(self.tokens) / self.sun_columns) * 38 if self.tokens else 0

    def sync(self):
        self.items = list(self.garden.collection)
        self.tokens = [token for token in self.garden.sun_tokens
                       if token['source_flower_id'] not in self.desktop_ids]
        self._update_height()
        self.update()

    def _update_height(self):
        rows = max(1, math.ceil(len(self.items) / self.columns))
        self.setMinimumHeight(18 + self.sun_height + rows * self.ROW_HEIGHT)

    def item_rect(self, index):
        row, column = divmod(index, self.columns)
        cell_width = (self.width() - 16) / self.columns
        return QRectF(8 + column * cell_width, 10 + self.sun_height + row * self.ROW_HEIGHT,
                      cell_width, 106)

    def sun_rect(self, index):
        row, column = divmod(index, self.sun_columns)
        width = (self.width() - 20) / self.sun_columns
        return QRectF(10 + column * width + (width - 30) / 2, 5 + row * 38, 30, 30)

    def sun_token_at(self, position):
        for index, token in enumerate(self.tokens):
            if self.sun_rect(index).contains(position):
                return token
        return None

    def item_at(self, position):
        row = int((position.y() - 10 - self.sun_height) // self.ROW_HEIGHT)
        if row < 0:
            return None
        for index in range(max(0, row * self.columns), min(len(self.items), (row + 1) * self.columns)):
            if self.item_rect(index).adjusted(6, 0, -6, 0).contains(position):
                return self.items[index]
        return None

    def tooltip_for(self, item):
        bonus = f' (분무 +{item["bonus_g"]}G)' if item['misted'] else ''
        desktop = '화면 맨 위에 표시 중 · 우클릭으로 복귀' if item['id'] in self.garden.desktop_flowers else '우클릭으로 화면 맨 위에 띄우기'
        return f'{plant_definition(item["species"]).name} · 판매 {sale_price(item)}G{bonus}\n돈주머니로 드래그하면 판매 · {desktop}'

    def contextMenuEvent(self, event):
        item = self.item_at(event.pos())
        if not item:
            return
        menu = QMenu(self)
        label = '정원으로 돌려놓기' if item['id'] in self.garden.desktop_flowers else '화면 맨 위에 띄우기'
        action = menu.addAction(label)
        if menu.exec(event.globalPos()) is action:
            self.desktopRequested.emit(item['id'])

    def _animate(self):
        if self.items and not self.garden.vacation:
            self.phase += .065
        for burst in self.bursts:
            burst['age'] += .08
        self.bursts = [burst for burst in self.bursts if burst['age'] < 1]
        if self.items or self.tokens or self.bursts:
            self.update()

    def showEvent(self, event):
        self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def resizeEvent(self, event):
        self._update_height()
        super().resizeEvent(event)

    def event(self, event):
        if event.type() == QEvent.ToolTip:
            token = self.sun_token_at(event.pos())
            if token:
                QToolTip.showText(event.globalPos(), '햇빛 +1 · 클릭해서 수집', self)
                return True
            item = self.item_at(event.pos())
            if item:
                QToolTip.showText(event.globalPos(), self.tooltip_for(item), self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = event.rect()
        gradient = QLinearGradient(0, 0, self.width(), max(280, self.height()))
        theme = garden_theme(self.garden.equipped_theme)
        gradient.setColorAt(0, QColor(theme.top))
        gradient.setColorAt(1, QColor(theme.bottom))
        painter.fillRect(bounds, gradient)
        # Deterministic tufts only in the visible rows, even for large collections.
        painter.setPen(QPen(QColor(theme.tuft), 1.3, Qt.SolidLine, Qt.RoundCap))
        for row in range(max(0, bounds.top() // 30), bounds.bottom() // 30 + 1):
            for column in range(self.width() // 38 + 1):
                x = column * 38 + (row % 2) * 15 + 7
                y = row * 30 + (column * 7) % 14
                painter.drawLine(x, y, x - 3, y - 5)
                painter.drawLine(x, y, x + 3, y - 6)
        if not self.items:
            painter.setPen(QColor(theme.text))
            visible = self.visibleRegion().boundingRect()
            painter.drawText(visible.adjusted(14, self.sun_height, -14, 0), Qt.AlignCenter | Qt.TextWordWrap,
                             '아직 모은 꽃이 없어요\n화분에서 핀 꽃을 정원에 보관해 보세요')
        start = max(0, (bounds.top() - 14 - self.sun_height) // self.ROW_HEIGHT) * self.columns
        end = min(len(self.items), ((bounds.bottom() - self.sun_height) // self.ROW_HEIGHT + 1) * self.columns)
        for index in range(start, end):
            item = self.items[index]
            rect = self.item_rect(index)
            phase = 0 if self.garden.vacation else self.phase + index * .8
            bob = math.sin(phase) * 2.5
            painter.save()
            if item['id'] == self.dragged_id:
                painter.setOpacity(.3)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(64, 98, 49, 48))
            painter.drawEllipse(QRectF(rect.center().x() - 23, rect.bottom() - 5, 46, 8))
            paint_collection_flower(painter, rect.adjusted(8, -3 + bob, -8, -9 + bob),
                                    plant_definition(item['species']), phase, skin=self.garden.equipped_skin)
            painter.restore()
            if item['id'] in self.garden.desktop_flowers:
                painter.setPen(QColor(theme.text))
                painter.drawText(rect.adjusted(0, 88, 0, 0), Qt.AlignCenter, '바탕화면')
        for index, token in enumerate(self.tokens):
            rect = self.sun_rect(index)
            pulse = 1 + math.sin(self.phase * 1.4 + index) * .08
            center = rect.center()
            radius = rect.width() * .34 * pulse
            painter.save()
            painter.setPen(QPen(QColor(255, 203, 68, 150), 1.5))
            for ray in range(8):
                angle = ray * math.pi / 4 + self.phase * .08
                inner, outer = radius + 2, radius + 5
                painter.drawLine(
                    QPoint(round(center.x() + math.cos(angle) * inner),
                           round(center.y() + math.sin(angle) * inner)),
                    QPoint(round(center.x() + math.cos(angle) * outer),
                           round(center.y() + math.sin(angle) * outer)),
                )
            painter.setPen(QPen(QColor('#e5a91d'), 1.2))
            painter.setBrush(QColor('#ffd85b'))
            painter.drawEllipse(center, radius, radius)
            painter.setBrush(QColor(255, 248, 185, 210))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPoint(round(center.x() - radius * .28), round(center.y() - radius * .28)),
                                max(1, round(radius * .24)), max(1, round(radius * .24)))
            painter.restore()
        for burst in self.bursts:
            painter.save()
            age, center = burst['age'], burst['center']
            painter.setOpacity(max(0, 1 - age))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor('#ffd34e'))
            for ray in range(8):
                angle = ray * math.pi / 4
                distance = 8 + age * 22
                point = QPoint(round(center.x() + math.cos(angle) * distance),
                               round(center.y() + math.sin(angle) * distance))
                painter.drawEllipse(point, 3, 3)
            painter.setPen(QColor('#a66a00'))
            painter.drawText(QRectF(center.x() - 18, center.y() - 28 - age * 12, 36, 18),
                             Qt.AlignCenter, '+1')
            painter.restore()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            token = self.sun_token_at(event.position())
            self._pressed_sun_id = token['id'] if token else None
            item = self.item_at(event.position())
            self._pressed_id = item['id'] if item and not token else None
            self._press_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        token = self.sun_token_at(event.position())
        self.setCursor(Qt.PointingHandCursor if token else
                       (Qt.OpenHandCursor if self.item_at(event.position()) else Qt.ArrowCursor))
        if (event.buttons() & Qt.LeftButton and self._pressed_sun_id
                and (event.position().toPoint() - self._press_position).manhattanLength()
                >= QApplication.startDragDistance()):
            self._pressed_sun_id = None
        if (event.buttons() & Qt.LeftButton and self._pressed_id
                and (event.position().toPoint() - self._press_position).manhattanLength()
                >= QApplication.startDragDistance()):
            item_id, self._pressed_id = self._pressed_id, None
            self.start_drag(item_id)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        token_id, center = self._pressed_sun_id, event.position()
        token = self.sun_token_at(event.position())
        moved = (event.position().toPoint() - self._press_position).manhattanLength()
        if (
            event.button() == Qt.LeftButton and token_id and token
            and token['id'] == token_id and moved < QApplication.startDragDistance()
            and self.collect_callback and self.collect_callback(token_id)
        ):
            self.bursts.append({'center': center, 'age': 0.0})
            self.update()
        self._pressed_sun_id = None
        self._pressed_id = None
        super().mouseReleaseEvent(event)

    def start_drag(self, item_id):
        item = next((flower for flower in self.garden.collection if flower['id'] == item_id), None)
        if item is None:
            return
        mime = QMimeData()
        mime.setData(FLOWER_MIME, item_id.encode('utf-8'))
        drag = QDrag(self)
        drag.setMimeData(mime)
        scale = self.devicePixelRatioF()
        pixmap = QPixmap(round(84 * scale), round(108 * scale))
        pixmap.setDevicePixelRatio(scale)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        paint_collection_flower(painter, QRectF(0, 0, 84, 108), plant_definition(item['species']),
                                skin=self.garden.equipped_skin)
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(42, 70))
        self.dragged_id = item_id
        self.dragChanged.emit(item)
        self.update()
        try:
            drag.exec(Qt.MoveAction)
        finally:
            self.dragged_id = None
            self.dragChanged.emit(None)
            self.update()
            drag.deleteLater()


class SaleZone(QWidget):
    def __init__(self, meadow, sell_callback, parent=None):
        super().__init__(parent)
        self.meadow, self.sell_callback = meadow, sell_callback
        self.preview = None
        self.highlighted = False
        self.setAcceptDrops(True)
        self.setFixedHeight(52)
        self.setAccessibleName('돈주머니 판매 영역')
        self.setToolTip('정원의 꽃 화분을 여기에 놓으면 표시된 가격으로 즉시 판매합니다.')
        meadow.dragChanged.connect(self.set_preview)

    def set_preview(self, item):
        self.preview = item
        self.highlighted = False
        self.update()

    def _valid_item(self, event):
        if event.source() is not self.meadow or not event.mimeData().hasFormat(FLOWER_MIME):
            return None
        if not event.possibleActions() & Qt.MoveAction:
            return None
        try:
            item_id = bytes(event.mimeData().data(FLOWER_MIME)).decode('utf-8')
        except UnicodeDecodeError:
            return None
        if item_id != self.meadow.dragged_id:
            return None
        return next((item for item in self.meadow.garden.collection if item['id'] == item_id), None)

    def dragEnterEvent(self, event):
        item = self._valid_item(event)
        if item:
            self.preview, self.highlighted = item, True
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()
        self.update()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dragLeaveEvent(self, event):
        self.highlighted = False
        self.update()
        event.accept()

    def dropEvent(self, event):
        item = self._valid_item(event)
        if item and self.sell_callback(item['id']):
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()
        self.preview, self.highlighted = None, False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor('#e5f0cd' if self.highlighted else '#f2ecd9'))
        painter.setPen(QPen(QColor('#799956' if self.highlighted else '#caba8d'), 1.5,
                            Qt.SolidLine if self.highlighted else Qt.DashLine))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 12, 12)
        # Money-bag icon is drawn, not an OS-dependent emoji glyph.
        painter.save()
        painter.translate(12, 7)
        bag = QPainterPath()
        bag.moveTo(12, 10)
        bag.lineTo(9, 2)
        bag.quadTo(17, 5, 25, 2)
        bag.lineTo(22, 10)
        bag.cubicTo(42, 31, 30, 37, 17, 36)
        bag.cubicTo(2, 37, -6, 29, 12, 10)
        painter.setPen(QPen(QColor('#99702e'), 1.4))
        painter.setBrush(QColor('#e7bd67'))
        painter.drawPath(bag)
        painter.drawLine(11, 11, 24, 11)
        painter.drawText(QRectF(7, 15, 22, 20), Qt.AlignCenter, 'G')
        painter.restore()
        painter.setPen(QColor('#4e5638'))
        title = f'놓으면 +{sale_price(self.preview)}G' if self.preview else '꽃 화분을 놓아 판매'
        subtitle = plant_definition(self.preview['species']).name if self.preview else '돈주머니까지 드래그하세요'
        painter.drawText(QRectF(61, 6, self.width() - 69, 20), Qt.AlignVCenter, title)
        painter.setPen(QColor('#7a8167'))
        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        painter.drawText(QRectF(61, 27, self.width() - 69, 16), Qt.AlignVCenter, subtitle)


class CollectionGarden(QWidget):
    def __init__(self, garden, sell_callback, collect_callback=None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.sun_status = QLabel()
        self.sun_status.setObjectName('small')
        self.sun_status.setAccessibleName('정원 햇빛 생산 상태')
        layout.addWidget(self.sun_status)
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet('QScrollArea {background:#bdd69d;border-radius:12px;} '
                                 'QScrollBar:vertical {width:8px;}')
        self.meadow = Meadow(garden, collect_callback)
        self.scroll.setWidget(self.meadow)
        layout.addWidget(self.scroll, 1)
        self.sale_zone = SaleZone(self.meadow, sell_callback)
        layout.addWidget(self.sale_zone)

    def sync(self):
        self.meadow.sync()
        pending = len(self.meadow.garden.sun_tokens)
        if self.meadow.garden.vacation:
            next_text = '휴가 중 생산 정지'
        elif pending >= SUN_PENDING_CAP:
            next_text = '대기 공간 가득 참'
        elif not self.meadow.garden.collection:
            next_text = '꽃을 보관하면 생산 시작'
        else:
            minutes = max(1, math.ceil(self.meadow.garden.seconds_to_sun / 60))
            next_text = f'다음 햇빛 약 {minutes}분'
        self.sun_status.setText(
            f'햇빛 {self.meadow.garden.sunlight} · 대기 {pending}/{SUN_PENDING_CAP} · {next_text}'
        )
