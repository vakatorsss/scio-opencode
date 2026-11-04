import hashlib, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import branded_ui

class BrandedCacheTests(unittest.TestCase):
    def test_current_build_is_reused_but_old_build_fetches_update(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory = root / 'bin' / 'scio-code'
            directory.mkdir(parents=True)
            exe = directory / 'scio-code.exe'
            exe.write_bytes(b'test executable')
            (directory / 'scio-code.sha256').write_text(hashlib.sha256(exe.read_bytes()).hexdigest())
            info = directory / 'build-info.json'
            info.write_text(json.dumps({'version': branded_ui.VERSION}))
            with patch.object(branded_ui.scio, 'DATA_DIR', root), patch('branded_ui.urlopen', side_effect=RuntimeError('download requested')) as download:
                self.assertEqual(branded_ui.binary(), str(exe))
                download.assert_not_called()
                info.write_text(json.dumps({'version': '1.19.3-scio.1'}))
                with self.assertRaisesRegex(RuntimeError, 'download requested'):
                    branded_ui.binary()
                self.assertIn(branded_ui.RELEASE, download.call_args.args[0].full_url)

if __name__ == '__main__':
    unittest.main()
