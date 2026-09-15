"""Small slide transitions; page widgets always keep their real layout."""
from PySide6.QtCore import QEasingCurve, QPoint, QParallelAnimationGroup, QPropertyAnimation
from PySide6.QtWidgets import QLabel, QStackedWidget


class SlideStack(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._animation = None
        self._overlays = []

    def slide_to(self, index, direction=1):
        if not 0 <= index < self.count():
            return
        self.finish_transition()
        if index == self.currentIndex():
            return
        if not self.isVisible():
            self.setCurrentIndex(index)
            return
        previous = self.currentWidget().grab()
        self.setCurrentIndex(index)
        self.currentWidget().layout().activate()
        incoming = self.currentWidget().grab()
        distance = self.width() * (1 if direction >= 0 else -1)
        group = QParallelAnimationGroup(self)
        for pixmap, start, end in (
            (previous, QPoint(0, 0), QPoint(-distance, 0)),
            (incoming, QPoint(distance, 0), QPoint(0, 0)),
        ):
            overlay = QLabel(self)
            overlay.setPixmap(pixmap)
            overlay.setFixedSize(self.size())
            overlay.move(start)
            overlay.show()
            overlay.raise_()
            self._overlays.append(overlay)
            animation = QPropertyAnimation(overlay, b'pos', group)
            animation.setDuration(180)
            animation.setStartValue(start)
            animation.setEndValue(end)
            animation.setEasingCurve(QEasingCurve.OutCubic)
            group.addAnimation(animation)
        self._animation = group
        group.finished.connect(self.finish_transition)
        group.start()

    def finish_transition(self):
        if self._animation is not None:
            self._animation.stop()
            self._animation.deleteLater()
            self._animation = None
        for overlay in self._overlays:
            overlay.hide()
            overlay.deleteLater()
        self._overlays.clear()

    def resizeEvent(self, event):
        self.finish_transition()
        super().resizeEvent(event)

    def hideEvent(self, event):
        self.finish_transition()
        super().hideEvent(event)
