import unittest

from build_msix import NS, manifest, store_version, validate_identity


class StorePackage(unittest.TestCase):
    def test_store_version(self):
        self.assertEqual(store_version('0.4.0'), '1.4.0.0')
        self.assertEqual(store_version('1.0.2'), '2.0.2.0')
        for value in ('0.4', 'v0.4.0', '65535.0.0', '0.65536.0'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                store_version(value)

    def test_manifest_uses_store_identity_and_full_trust(self):
        root = manifest('MorningBloom.Test', 'CN=badbed7', 'badbed7', '0.4.0').getroot()
        identity = root.find(f'{{{NS[""]}}}Identity')
        self.assertEqual(identity.attrib, {
            'Name': 'MorningBloom.Test', 'Publisher': 'CN=badbed7',
            'Version': '1.4.0.0', 'ProcessorArchitecture': 'x64',
        })
        capability = root.find(f'.//{{{NS["rescap"]}}}Capability')
        self.assertEqual(capability.get('Name'), 'runFullTrust')
        application = root.find(f'.//{{{NS[""]}}}Application')
        self.assertEqual(application.get('Executable'), 'MorningBloomGame.exe')
        self.assertEqual(application.get(f'{{{NS["uap10"]}}}RuntimeBehavior'), 'packagedClassicApp')
        self.assertEqual(application.get(f'{{{NS["uap10"]}}}TrustLevel'), 'mediumIL')
        visual = root.find(f'.//{{{NS["uap"]}}}VisualElements')
        self.assertEqual(visual.get('Square44x44Logo'), r'Assets\Square44x44Logo.png')

    def test_invalid_identity_is_rejected(self):
        for name in ('x', 'bad name', 'CON.App', 'ends.'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_identity(name, 'CN=badbed7', 'badbed7')


if __name__ == '__main__':
    unittest.main()
