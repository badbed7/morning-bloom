import sys
import tempfile
import time
from pathlib import Path


def smoke_test():
    from PySide6.QtWidgets import QApplication
    from morning_bloom.app import Window
    from morning_bloom.model import Garden
    from morning_bloom.storage import Store
    app = QApplication([])
    app.setApplicationName('MorningBloomBuildCheck')
    with tempfile.TemporaryDirectory() as temp:
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
    return 0

if __name__ == '__main__':
    if '--smoke-test' in sys.argv:
        raise SystemExit(smoke_test())
    from morning_bloom.app import main
    raise SystemExit(main())
