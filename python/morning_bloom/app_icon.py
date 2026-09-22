"""Daisy flower head shared by the running app and Windows executable icons."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap


def daisy_image(size):
    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.translate(size / 2, size / 2)
    painter.scale(size / 100, size / 100)
    painter.setPen(QPen(QColor('#d9cbb2'), 1.2))
    painter.setBrush(QColor('#fff9e9'))
    for angle in range(0, 360, 60):
        painter.save()
        painter.rotate(angle)
        painter.drawEllipse(QRectF(-14, -45, 28, 40))
        painter.restore()
    painter.setPen(QPen(QColor('#e3a838'), 1.5))
    painter.setBrush(QColor('#ffc753'))
    painter.drawEllipse(QRectF(-15, -15, 30, 30))
    painter.end()
    return image


def daisy_icon():
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(daisy_image(size)))
    return icon
