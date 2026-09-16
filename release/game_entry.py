import sys
import argparse
import contextlib
import tempfile
import time
import traceback
from pathlib import Path


def smoke_test():
    print('Loading game UI', flush=True)
    from PySide6.QtWidgets import QApplication
    from morning_bloom.app import Window
    from morning_bloom.model import Garden
    from morning_bloom.storage import Store
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
        window.close()
    print('Startup check passed', flush=True)
    return 0


def checked_smoke_test(log_path):
    with Path(log_path).open('a', encoding='utf-8') as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                return smoke_test()
            except Exception:
                traceback.print_exc()
                return 1


if __name__ == '__main__':
    if '--smoke-test' in sys.argv:
        parser = argparse.ArgumentParser()
        parser.add_argument('--smoke-test', action='store_true')
        parser.add_argument('--startup-log', type=Path)
        args = parser.parse_args()
        raise SystemExit(checked_smoke_test(args.startup_log) if args.startup_log else smoke_test())
    from morning_bloom.app import main
    raise SystemExit(main())
