"""Render feature previews using isolated state; never opens the user's save."""
import argparse
import tempfile
import time
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from morning_bloom.app import SHOP_PAGE, Window
from morning_bloom.desktop_flowers import DesktopFlower
from morning_bloom.model import Garden
from morning_bloom.storage import Store


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
        owner.close()
        app.processEvents()
    print(args.output.resolve())


if __name__ == '__main__':
    main()
