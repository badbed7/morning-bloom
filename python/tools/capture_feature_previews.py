"""Render feature previews using isolated state; never opens the user's save."""
import argparse
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter
from PySide6.QtWidgets import QApplication

from morning_bloom.app import SHOP_PAGE, Window
from morning_bloom.desktop_flowers import DesktopFlower
from morning_bloom.model import Garden
from morning_bloom.storage import Store
from morning_bloom.flower_art import paint_collection_flower
from morning_bloom.plant_catalog import PLANTS, DAY, HOUR


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    font = Path(__file__).resolve().parents[2] / 'assets/fonts/NotoSansKR-Subset.otf'
    if font.exists():
        font_id = QFontDatabase.addApplicationFont(str(font))
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    with tempfile.TemporaryDirectory() as tmp:
        now = time.time()
        garden = Garden(now, tutorial_used=True, tutorial_reward_claimed=True, coins=400)
        garden.plant(now)
        garden.care('water', now)
        garden.growth = garden.duration * .75
        owner = Window(Store(Path(tmp) / 'preview.json'), garden)
        owner.setFixedSize(384, 384)
        owner.show()
        owner.pages.setCurrentIndex(SHOP_PAGE)
        owner.shop_picker.buttons['random'].click()
        app.processEvents()
        owner.grab().save(str(args.output / 'random-seed-shop.png'))
        owner.open_mist_game()
        game = owner._mist_game
        game.canvas.spraying = True
        game.canvas.frame = 7
        app.processEvents()
        game.grab().save(str(args.output / 'mist-minigame.png'))
        game.reject()
        owner.open_fertilizer_game()
        game = owner._fertilizer_game
        game.start()
        app.processEvents()
        game.grab().save(str(args.output / 'fertilizer-minigame.png'))
        game.reject()
        garden.growth = garden.duration
        garden.harvest(now)
        flower_id = garden.collection[0]['id']
        garden.collection[0]['species'] = 'ancient'
        garden.sun_tokens = [{'id': f'preview-sun-{n}', 'source_flower_id': flower_id, 'created_at': now + n}
                             for n in range(6)]
        # Rendering only: real attachment is covered by test_desktop_native.
        widget = DesktopFlower(owner, flower_id, None)
        widget.show()
        app.processEvents()
        widget.grab().save(str(args.output / 'desktop-flower-preview.png'))
        widget.timer.stop()
        widget.close()
        owner.shop_picker.buttons['lavender'].click()
        app.processEvents()
        owner.grab().save(str(args.output / 'vacation-flower-shop.png'))
        owner.shop_picker.buttons['freesia'].click()
        app.processEvents()
        owner.grab().save(str(args.output / 'weekend-flower-shop.png'))
        owner.open_wind_game()
        game = owner._wind_game
        app.processEvents()
        game.start()
        game.timer.stop()
        for _ in range(25 * 60):
            state = game.state
            target = next((gate['y'] for gate in state.gates if not gate['checked']), .5)
            state.step(1 / 60, state.y + state.velocity * .65 > target)
        game.update_controls()
        app.processEvents()
        game.grab().save(str(args.output / 'wind-minigame.png'))
        game.reject()
        owner.close()
        app.processEvents()
    image = QImage(960, 810, QImage.Format_ARGB32_Premultiplied)
    image.fill(QColor('#f7f1e5'))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    flowers = ('rose', 'lily_of_the_valley', 'clover', 'daisy', 'tulip', 'sunflower', 'lavender', 'forget_me_not',
               'pansy', 'cosmos', 'freesia')
    for index, key in enumerate(flowers):
        x, y = index % 4 * 240, index // 4 * 270
        definition = PLANTS[key]
        paint_collection_flower(painter, QRectF(x + 40, y + 18, 160, 210), definition)
        painter.setPen(QColor('#5b5142'))
        painter.drawText(QRectF(x, y + 224, 240, 22), Qt.AlignCenter, definition.name)
        duration = (f'{definition.growth_seconds // DAY}일' if definition.growth_seconds >= DAY else
                    f'{definition.growth_seconds // HOUR}시간')
        painter.drawText(QRectF(x, y + 248, 240, 20), Qt.AlignCenter, duration)
    painter.end()
    image.save(str(args.output / 'reference-flowers.png'))
    image.copy(0, 540, 720, 270).save(str(args.output / 'weekend-flowers.png'))
    print(args.output.resolve())


if __name__ == '__main__':
    main()
