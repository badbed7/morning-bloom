"""Build a self-contained BAT updater; its TLS dependency is needed before game pip setup."""
import importlib.metadata
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def copy_bat_updater(target):
    import truststore
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    for name in ('launcher.py', 'update_core.py', 'update_tls.py', 'live_update.py', 'release_config.py'):
        shutil.copyfile(ROOT / 'release' / name, target / name)
    package = Path(truststore.__file__).parent
    shutil.copytree(package, target / 'truststore',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'), dirs_exist_ok=True)
    distribution = importlib.metadata.distribution('truststore')
    for item in distribution.files or ():
        if str(item).endswith('/LICENSE'):
            shutil.copyfile(distribution.locate_file(item), target / 'truststore/LICENSE')
            break
    else:
        raise RuntimeError('truststore license is missing from the build environment')
