"""Package the PyInstaller game directory as a Microsoft Store MSIX."""
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'release-output'
STAGE = OUTPUT / 'msix-stage'

NS = {
    '': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10',
    'uap': 'http://schemas.microsoft.com/appx/manifest/uap/windows10',
    'uap10': 'http://schemas.microsoft.com/appx/manifest/uap/windows10/10',
    'rescap': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities',
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def qname(tag, prefix=''):
    return f'{{{NS[prefix]}}}{tag}'


def store_version(version):
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', version)
    if not match:
        raise ValueError('Version must use three numbers, for example 0.4.0')
    major, minor, patch = map(int, match.groups())
    if major >= 65535 or minor > 65535 or patch > 65535:
        raise ValueError('Version component exceeds the MSIX limit')
    return f'{major + 1}.{minor}.{patch}.0'


def validate_identity(name, publisher, publisher_display_name):
    if not re.fullmatch(r'[A-Za-z0-9.-]{3,50}', name) or name.endswith('.'):
        raise ValueError('Identity Name must exactly match the Partner Center value')
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
    if any(part.upper() in reserved for part in name.split('.')):
        raise ValueError('Identity Name contains a reserved Windows name')
    if not publisher or len(publisher) > 8192:
        raise ValueError('Publisher must exactly match the Partner Center value')
    if not publisher_display_name or len(publisher_display_name) > 256:
        raise ValueError('Publisher display name is required')


def manifest(identity_name, publisher, publisher_display_name, version):
    validate_identity(identity_name, publisher, publisher_display_name)
    package = ET.Element(qname('Package'), {'IgnorableNamespaces': 'uap uap10 rescap'})
    ET.SubElement(package, qname('Identity'), {
        'Name': identity_name, 'Publisher': publisher, 'Version': store_version(version),
        'ProcessorArchitecture': 'x64',
    })
    properties = ET.SubElement(package, qname('Properties'))
    ET.SubElement(properties, qname('DisplayName')).text = 'Morning Bloom'
    ET.SubElement(properties, qname('PublisherDisplayName')).text = publisher_display_name
    ET.SubElement(properties, qname('Description')).text = '바탕화면 한쪽에서 꽃을 돌보는 코티지 정원 게임'
    ET.SubElement(properties, qname('Logo')).text = r'Assets\StoreLogo.png'
    resources = ET.SubElement(package, qname('Resources'))
    ET.SubElement(resources, qname('Resource'), {'Language': 'ko-kr'})
    dependencies = ET.SubElement(package, qname('Dependencies'))
    ET.SubElement(dependencies, qname('TargetDeviceFamily'), {
        'Name': 'Windows.Desktop', 'MinVersion': '10.0.19041.0',
        'MaxVersionTested': '10.0.26100.0',
    })
    capabilities = ET.SubElement(package, qname('Capabilities'))
    ET.SubElement(capabilities, qname('Capability', 'rescap'), {'Name': 'runFullTrust'})
    applications = ET.SubElement(package, qname('Applications'))
    application = ET.SubElement(applications, qname('Application'), {
        'Id': 'MorningBloom', 'Executable': 'MorningBloomGame.exe',
        qname('RuntimeBehavior', 'uap10'): 'packagedClassicApp',
        qname('TrustLevel', 'uap10'): 'mediumIL',
    })
    ET.SubElement(application, qname('VisualElements', 'uap'), {
        'DisplayName': 'Morning Bloom',
        'Description': '바탕화면 한쪽에서 꽃을 돌보는 코티지 정원 게임',
        'Square150x150Logo': r'Assets\Square150x150Logo.png',
        'Square44x44Logo': r'Assets\Square44x44Logo.png',
        'BackgroundColor': '#F5F0E3',
    })
    return ET.ElementTree(package)


def generate_assets(directory):
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter

    sys.path.insert(0, str(ROOT / 'python'))
    from morning_bloom.flower_art import paint_potted_flower
    from morning_bloom.plant_catalog import plant_definition

    directory.mkdir(parents=True, exist_ok=True)
    sizes = {
        'Square44x44Logo.scale-100.png': 44, 'Square44x44Logo.scale-200.png': 88,
        'Square44x44Logo.scale-400.png': 176, 'Square150x150Logo.scale-100.png': 150,
        'Square150x150Logo.scale-200.png': 300, 'Square150x150Logo.scale-400.png': 600,
        'Square44x44Logo.targetsize-16.png': 16, 'Square44x44Logo.targetsize-24.png': 24,
        'Square44x44Logo.targetsize-32.png': 32, 'Square44x44Logo.targetsize-48.png': 48,
        'Square44x44Logo.targetsize-256.png': 256, 'StoreLogo.scale-100.png': 50,
        'StoreLogo.scale-200.png': 100, 'StoreLogo.scale-400.png': 200,
    }
    for filename, size in sizes.items():
        image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
        image.fill(QColor('#F5F0E3'))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#E6EED8'))
        inset = max(1, size * .06)
        painter.drawRoundedRect(QRectF(inset, inset, size - 2 * inset, size - 2 * inset), size * .18, size * .18)
        scale = size / 190
        painter.translate(size / 2 - 190 * scale, size * .03)
        painter.scale(scale, scale)
        paint_potted_flower(painter, plant_definition('daisy'))
        painter.end()
        if not image.save(str(directory / filename)):
            raise RuntimeError(f'Could not write {filename}')


def find_makeappx():
    configured = os.environ.get('MAKEAPPX')
    if configured and Path(configured).is_file():
        return Path(configured)
    kits = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Windows Kits/10/bin'
    candidates = sorted(kits.glob('*/x64/MakeAppx.exe'), reverse=True)
    if not candidates:
        raise FileNotFoundError('MakeAppx.exe not found; install the Windows 10/11 SDK')
    return candidates[0]


def main():
    if sys.platform != 'win32':
        raise SystemExit('MSIX packaging requires Windows')
    values = [os.environ.get(key, '').strip() for key in
              ('STORE_IDENTITY_NAME', 'STORE_PUBLISHER', 'STORE_PUBLISHER_DISPLAY_NAME')]
    version = (ROOT / 'release/VERSION').read_text(encoding='utf-8').strip()
    try:
        validate_identity(*values)
        package_version = store_version(version)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    game = ROOT / 'dist/MorningBloomGame'
    if not (game / 'MorningBloomGame.exe').is_file():
        raise SystemExit('Run release/build_windows.py first')
    if STAGE.exists():
        shutil.rmtree(STAGE)
    shutil.copytree(game, STAGE)
    generate_assets(STAGE / 'Assets')
    tree = manifest(*values, version)
    ET.indent(tree, space='  ')
    tree.write(STAGE / 'AppxManifest.xml', encoding='utf-8', xml_declaration=True)
    target = OUTPUT / f'MorningBloom-{version}-Store-x64.msix'
    target.unlink(missing_ok=True)
    subprocess.run([str(find_makeappx()), 'pack', '/v', '/h', 'SHA256', '/d', str(STAGE),
                    '/p', str(target), '/o'], cwd=ROOT, check=True)
    print(f'Created {target.name} (MSIX {package_version}); Microsoft Store applies the final signature.')


if __name__ == '__main__':
    main()
