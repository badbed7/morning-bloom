import sys
import argparse
import contextlib
import tempfile
import time
import traceback
from pathlib import Path

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))


def smoke_test():
    print('Loading game UI', flush=True)
    from PySide6.QtWidgets import QApplication
    from morning_bloom.app import Window
    from morning_bloom.model import Garden
    from morning_bloom.storage import Store
    from morning_bloom.locked_catalog import COLLECTIONS, preview_image
    print('Creating Qt application', flush=True)
    app = QApplication([])
    app.setApplicationName('MorningBloomBuildCheck')
    with tempfile.TemporaryDirectory() as temp:
        print('Creating isolated test garden', flush=True)
        window = Window(Store(Path(temp) / 'test.json'), Garden(time.time()), True)
        window.show()
        app.processEvents()
        window.plant_button.click()
        window.water_button.click()
        window.offset = 61
        window.refresh()
        window.harvest_button.click()
        assert len(window.garden.collection) == 1
        assert not window.grab().isNull()
        for items in COLLECTIONS.values():
            assert not preview_image(items[0]).isNull(), 'Missing catalog artwork'
        window.open_gacha_board()
        board = window._gacha_board_window
        board.category.setCurrentIndex(2)
        board.draw(10)
        board.finish_animation()
        assert window.garden.unlocked_plants, 'Plant draw did not unlock a plant'
        assert window.store.load(window.garden.last_update).unlocked_plants
        board.done(0)
        window.close()
    print('Startup check passed', flush=True)
    return 0


def live_update_smoke():
    """Packaged game subprocess exercising the real settings/apply/close path."""
    import os
    from PySide6.QtCore import QTimer, QLockFile
    from PySide6.QtWidgets import QApplication
    from morning_bloom.app import Window
    from morning_bloom.storage import Store
    root = Path(os.environ['MORNING_BLOOM_UPDATE_SMOKE_ROOT'])
    if not root.is_dir():
        raise ValueError('Missing isolated update smoke directory')
    app = QApplication([])
    app.setApplicationName('MorningBloomUpdateBuildCheck')
    lock = QLockFile(str(root / 'garden.lock'))
    if not lock.tryLock(0):
        raise ValueError('Old game still holds the garden lock')
    store = Store(root / 'garden.json')
    garden = store.load(time.time())
    first = not store.path.exists()
    if first:
        garden.coins = 321
    if garden.coins != 321:
        raise ValueError('Update did not preserve the saved garden')
    window = Window(store, garden, False, save_lock=lock)
    window.show()
    expected = os.environ['MORNING_BLOOM_UPDATE_SMOKE_TARGET']
    successful = [False]
    def changed(state):
        if window.update_client.version == expected:
            successful[0] = True
            window.close()
        elif state.get('ready') and not window._update_busy:
            successful[0] = True
            window.apply_live_update()
    window.update_client.changed.connect(changed)
    QTimer.singleShot(100, lambda: window.update_client.command('check'))
    QTimer.singleShot(25000, lambda: app.exit(3))
    result = app.exec()
    if not successful[0]:
        return 4
    return result


def checked_smoke_test(log_path):
    with Path(log_path).open('a', encoding='utf-8') as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                return smoke_test()
            except Exception:
                traceback.print_exc()
                return 1


if __name__ == '__main__':
    if '--live-update-smoke' in sys.argv:
        raise SystemExit(live_update_smoke())
    if '--smoke-test' in sys.argv:
        parser = argparse.ArgumentParser()
        parser.add_argument('--smoke-test', action='store_true')
        parser.add_argument('--startup-log', type=Path)
        args = parser.parse_args()
        raise SystemExit(checked_smoke_test(args.startup_log) if args.startup_log else smoke_test())
    from morning_bloom.app import main
    raise SystemExit(main())
