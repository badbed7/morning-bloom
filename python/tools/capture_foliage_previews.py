"""Capture the real shared game renderer; does not read or write player saves.

QT_QPA_PLATFORM=offscreen PYTHONPATH=python python python/tools/capture_foliage_previews.py --output docs/images/foliage-reference.png
"""
import argparse
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter
from PySide6.QtWidgets import QApplication

from morning_bloom.flower_art import paint_collection_flower
from morning_bloom.plant_catalog import PLANTS, CATALOG_GACHA_PLANTS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stages', action='store_true')
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    font_path = Path(__file__).resolve().parents[2] / 'assets/fonts/NotoSansKR-Subset.otf'
    font_id = QFontDatabase.addApplicationFont(str(font_path))
    family = QFontDatabase.applicationFontFamilies(font_id)[0]
    image = QImage(1400, 1600 if args.stages else 940, QImage.Format_ARGB32_Premultiplied)
    image.fill(QColor('#f8f4e9'))
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor('#40563d'))
    p.setFont(QFont(family, 25, QFont.Bold))
    p.drawText(40, 54, 'Morning Bloom · 관엽식물 8종' + (' 성장 단계' if args.stages else ''))
    p.setPen(QColor('#726a60'))
    p.setFont(QFont(family, 12))
    p.drawText(40, 88, '실제 게임 공통 렌더러 · 기본 토분 · 화분 꾸미기 설정과 독립')
    if args.stages:
        for stage, label in enumerate(('씨앗', '새싹', '성장', '성숙 전', '완성')):
            p.drawText(QRectF(270 + stage * 220, 102, 150, 28), Qt.AlignCenter, label)
    for i, key in enumerate(CATALOG_GACHA_PLANTS):
        definition = PLANTS[key]
        if args.stages:
            p.setPen(QColor('#40563d'))
            p.setFont(QFont(family, 13))
            p.drawText(25, 165 + i * 178, definition.name)
            for stage in range(5):
                paint_collection_flower(p, QRectF(270 + stage * 220, 130 + i * 178, 150, 150), definition, stage=stage)
        else:
            x, y = 35 + (i % 4) * 345, 120 + (i // 4) * 395
            p.setPen(QColor('#e4d9c6'))
            p.setBrush(QColor('#fffcf4'))
            p.drawRoundedRect(QRectF(x, y, 315, 375), 18, 18)
            paint_collection_flower(p, QRectF(x + 20, y + 5, 275, 310), definition)
            p.setPen(QColor('#40563d'))
            p.setFont(QFont(family, 14, QFont.Bold))
            p.drawText(QRectF(x, y + 320, 315, 28), Qt.AlignCenter, definition.name)
            p.setFont(QFont(family, 10))
            p.drawText(QRectF(x, y + 349, 315, 22), Qt.AlignCenter, key)
    p.end()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(args.output)):
        raise RuntimeError(f'Could not save {args.output}')


if __name__ == '__main__':
    main()
