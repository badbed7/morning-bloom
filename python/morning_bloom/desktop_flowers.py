"""Interactive always-on-top flower overlays sharing the garden ledger."""
import hashlib
import math
import random
import time

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QRegion
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from .desktop_host import DesktopUnavailable, WindowsDesktopHost
from .flower_art import paint_collection_flower
from .model import growth_stage
from .plant_catalog import plant_definition


def sun_positions(tokens, radius=88, existing=None):
    """Area-uniform points in an invisible disk; stable across refresh/restart.

    A token-local PRNG never consumes the random-seed purchase RNG. Rejection
    sampling separates hit targets; a bounded best-distance fallback handles
    pathological clusters without moving previously placed suns.
    """
    valid_ids = {token['id'] for token in tokens}
    positions = {key: value for key, value in (existing or {}).items() if key in valid_ids}
    for token in sorted(tokens, key=lambda item: (item['created_at'], item['id'])):
        if token['id'] in positions:
            continue
        rng = random.Random(int.from_bytes(hashlib.sha256(token['id'].encode()).digest()[:8], 'big'))
        candidates = []
        for _ in range(120):
            angle, distance = rng.random() * math.tau, radius * math.sqrt(rng.random())
            point = QPointF(math.cos(angle) * distance, math.sin(angle) * distance)
            separation = min((math.hypot(point.x() - p.x(), point.y() - p.y())
                              for p in positions.values()), default=1000)
            candidates.append((separation, point))
            if separation >= 30:
                break
        positions[token['id']] = max(candidates, key=lambda pair: pair[0])[1]
    return positions


class DesktopFlower(QWidget):
    def __init__(self, owner, item_id, host):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.owner, self.item_id, self.host = owner, item_id, host
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_QuitOnClose, False)
        self.setFixedSize(256, 256)
        self.phase = 0.0
        self.suns = {}
        self.drag_start = None
        self.pressed_sun = None
        self.moved = False
        self.timer = QTimer(self)
        self.timer.setInterval(60)
        self.timer.timeout.connect(self.animate)
        self.timer.start()
        self.sync()

    def sync(self):
        garden = self.owner.garden
        self.item = garden.desktop_source(self.item_id)
        self.growing = self.item is not None and 'plant_id' in self.item
        self.setToolTip('드래그로 이동 · 우클릭으로 화분에 돌려놓기' if self.growing else
                       '드래그로 이동 · 햇빛 클릭 수집 · 우클릭으로 정원에 돌려놓기')
        tokens = [token for token in garden.sun_tokens if token['source_flower_id'] == self.item_id]
        # Keep existing positions after collection so neighboring suns do not jump.
        existing = {key: point - QPointF(128, 128) for key, point in self.suns.items()}
        generated = sun_positions(tokens, existing=existing)
        self.suns = {key: point + QPointF(128, 128) for key, point in generated.items()}
        self.setWindowOpacity(garden.desktop_opacity)
        # Do not intercept the whole transparent square of the desktop.
        region = QRegion(QRect(74, 36, 108, 173))
        for point in self.suns.values():
            region |= QRegion(QRect(round(point.x() - 15), round(point.y() - 15), 30, 30), QRegion.Ellipse)
        self.setMask(region)
        self.update()

    def animate(self):
        if not self.owner.garden.vacation:
            self.phase += .08
        self.update()

    def paintEvent(self, event):
        if not self.item:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        paint_collection_flower(painter, QRectF(68, 32, 120, 182), plant_definition(self.item['species']),
                                self.phase, self.owner.garden.equipped_skin,
                                stage=growth_stage(self.item) if self.growing else 4)
        for point in self.suns.values():
            painter.setPen(QPen(QColor('#e4b448'), 2))
            for index in range(8):
                angle = index * math.pi / 4
                painter.drawLine(point + QPointF(math.cos(angle) * 11, math.sin(angle) * 11),
                                 point + QPointF(math.cos(angle) * 14, math.sin(angle) * 14))
            painter.setBrush(QColor('#ffdb67'))
            painter.drawEllipse(point, 8, 8)
        painter.end()

    def sun_at(self, position):
        return next((key for key, point in self.suns.items()
                     if math.hypot(position.x() - point.x(), position.y() - point.y()) <= 15), None)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.pressed_sun = self.sun_at(event.position())
            self.drag_start = self.host.cursor_position()
            self.original_position = self.host.position(int(self.winId()))
            self.moved = False
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_start and event.buttons() & Qt.LeftButton and not self.pressed_sun:
            x, y = self.host.cursor_position()
            dx, dy = x - self.drag_start[0], y - self.drag_start[1]
            if abs(dx) + abs(dy) >= QApplication.startDragDistance():
                self.moved = True
            if self.moved:
                try:
                    self.host.move(self, self.original_position[0] + dx, self.original_position[1] + dy)
                except DesktopUnavailable:
                    self.drag_start = None

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self.drag_start:
            return
        if self.pressed_sun and self.sun_at(event.position()) == self.pressed_sun:
            self.owner.collect_sun(self.pressed_sun)
        elif self.moved:
            x, y = self.host.position(int(self.winId()))
            if not self.owner.act(lambda: self.owner.garden.place_desktop(self.item_id, x, y)):
                self.host.move(self, *self.original_position)
        self.drag_start = None
        self.pressed_sun = None

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        action = menu.addAction('화분으로 돌려놓기' if self.growing else '정원으로 돌려놓기')
        if menu.exec(event.globalPos()) is action:
            self.owner.act(lambda: self.owner.garden.return_desktop(self.item_id))

    def dispose(self):
        self.timer.stop()
        self.host.detach(self)
        self.close()
        self.deleteLater()


class DesktopFlowers:
    def __init__(self, owner, host_factory=WindowsDesktopHost):
        self.owner, self.host_factory = owner, host_factory
        self.host = None
        self.windows = {}
        self.error = ''
        self.retry_after = 0

    def ensure_host(self):
        if self.host is None or not self.host.valid():
            self.host = self.host_factory()
        return self.host

    def create(self, item_id, x, y):
        host = self.ensure_host()
        widget = DesktopFlower(self.owner, item_id, host)
        try:
            host.attach(widget, x, y)
            widget.show()
            # Qt can recreate a native handle while showing. Verify and reapply
            # the topmost position after the window becomes visible.
            if not host.valid(int(widget.winId())):
                raise DesktopUnavailable('플로팅 꽃 창을 확인하지 못했어요.')
            host.move(widget, x, y)
        except Exception:
            widget.dispose()
            raise
        self.windows[item_id] = widget
        return widget

    def place(self, item_id):
        """Backward-compatible toggle used by the existing garden view."""
        if item_id in self.owner.garden.desktop_flowers:
            return self.return_to_garden(item_id)
        return self.ensure_floating(item_id)

    def ensure_floating(self, item_id):
        if self.owner.garden.desktop_source(item_id) is None:
            self.owner.notify('띄울 식물을 찾지 못했어요.', important=True)
            return False
        if item_id in self.owner.garden.desktop_flowers:
            position = self.owner.garden.desktop_flowers[item_id]
            try:
                widget = self.windows.get(item_id)
                if widget is not None and not widget.host.valid(int(widget.winId())):
                    self.remove(item_id)
                    widget = None
                if widget is None:
                    self.create(item_id, position['x'], position['y'])
                self.windows[item_id].sync()
                self.owner.notify('화면 맨 위에 꽃을 표시하고 있어요.', important=True)
                return True
            except (DesktopUnavailable, OSError) as exc:
                self.owner.notify(str(exc), important=True)
                return False
        try:
            self.retry_after = 0
            host = self.ensure_host()
            x, y = host.cursor_position()
            widget = self.create(item_id, x - 128, y - 128)
            x, y = host.position(int(widget.winId()))
        except (DesktopUnavailable, OSError) as exc:
            self.owner.notify(str(exc), important=True)
            return False
        if not self.owner.act(lambda: self.owner.garden.place_desktop(item_id, x, y)):
            # act() synchronizes and may already have disposed the tentative widget.
            self.remove(item_id)
            return False
        self.owner.notify('화면 맨 위에 식물을 배치했어요. 우클릭하면 되돌릴 수 있어요.', important=True)
        return True

    def return_to_garden(self, item_id):
        if item_id not in self.owner.garden.desktop_flowers:
            self.remove(item_id)
            return True
        return self.owner.act(lambda: self.owner.garden.return_desktop(item_id))

    def remove(self, item_id):
        widget = self.windows.pop(item_id, None)
        if widget:
            widget.dispose()

    def sync(self):
        for key in list(self.windows):
            if key not in self.owner.garden.desktop_flowers:
                self.remove(key)
        for key, position in self.owner.garden.desktop_flowers.items():
            if key not in self.windows and time.monotonic() < self.retry_after:
                continue
            try:
                widget = self.windows.get(key)
                if widget and not widget.host.valid(int(widget.winId())):
                    self.remove(key)
                    widget = None
                if widget is None:
                    widget = self.create(key, position['x'], position['y'])
                widget.sync()
            except (DesktopUnavailable, OSError) as exc:
                if self.error != str(exc):
                    self.owner.notify(str(exc), important=True)
                self.error = str(exc)
                self.retry_after = time.monotonic() + 5
                break

    def close(self):
        for key in list(self.windows):
            self.remove(key)
        self.host = None
        self.retry_after = 0
