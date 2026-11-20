"""Validate browser registration generation without modifying the Windows registry."""
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt', 'The native host installer targets Windows.')
class InstallerTests(unittest.TestCase):
    """Exercise installer output in an isolated copy of the configuration files."""

    def setUp(self):
        """Create a temporary installation directory, including a space in its path."""
        self.tmp = tempfile.TemporaryDirectory(prefix='ytdl installer ')
        self.root = Path(self.tmp.name)
        (self.root / 'extension').mkdir()
        for name in ('install.ps1', 'uninstall.ps1', 'installer_support.ps1', 'browsers.json'):
            shutil.copy2(PROJECT / name, self.root / name)
        shutil.copy2(PROJECT / 'extension/manifest.json', self.root / 'extension/manifest.json')

    def tearDown(self):
        """Remove generated test manifests and launchers."""
        self.tmp.cleanup()

    def prepare(self, *options):
        """Run only manifest generation, with dependencies and registry writes disabled."""
        return subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                               '-File', str(self.root / 'install.ps1'), '-PrepareOnly',
                               '-SkipDependencies', *options], capture_output=True, text=True, timeout=30)

    def test_browser_registrations_and_stable_identity(self):
        """Generate all supported vendor locations and the expected extension origin."""
        result = self.prepare('-AdditionalBrowserRegistryPaths', r'ExampleVendor\Browser')
        self.assertEqual(result.returncode, 0, result.stderr)
        runtime = self.root / '.runtime'
        manifest = json.loads((runtime / 'com.ytdl.vivaldi.json').read_text())
        self.assertEqual(manifest['allowed_origins'],
                         ['chrome-extension://folnohikggmdphdpningknpkkbmnimpo/'])
        self.assertEqual(Path(manifest['path']), runtime / 'host.cmd')
        plan = json.loads((runtime / 'registration-plan.json').read_text())
        for prefix in (r'Google\Chrome', r'Microsoft\Edge', r'BraveSoftware\Brave-Browser',
                       'Vivaldi', 'Chromium', r'ExampleVendor\Browser'):
            self.assertIn(fr'Software\{prefix}\NativeMessagingHosts\com.ytdl.vivaldi', plan)
        self.assertIn('no registry entries were changed', result.stdout)
        repeated = self.prepare()
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        updated = json.loads((runtime / 'registration-plan.json').read_text())
        self.assertIn(r'Software\ExampleVendor\Browser\NativeMessagingHosts\com.ytdl.vivaldi', updated)

    def test_invalid_registry_prefix_is_rejected(self):
        """Reject path traversal instead of creating an unexpected registration plan."""
        result = self.prepare('-AdditionalBrowserRegistryPaths', r'..\Other')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / '.runtime').exists())

    def test_uninstall_preview_preserves_sources_and_generated_files(self):
        """Preview full cleanup without deleting local files or modifying registration."""
        self.assertEqual(self.prepare().returncode, 0)
        environment = self.root / '.venv'
        environment.mkdir()
        (environment / 'marker.txt').write_text('keep during dry run')
        result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                 '-File', str(self.root / 'uninstall.ps1'), '-CleanGenerated', '-DryRun'],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('No registry keys or files were changed', result.stdout)
        self.assertTrue((environment / 'marker.txt').exists())
        self.assertTrue((self.root / '.runtime/com.ytdl.vivaldi.json').exists())
        self.assertTrue((self.root / 'extension/manifest.json').exists())


class SourceDocumentationTests(unittest.TestCase):
    """Keep concise function summaries present throughout Python source and tests."""

    def test_python_functions_have_summaries(self):
        """Require docstrings on every Python function and class owned by the project."""
        for folder in ('backend', 'tests'):
            for source in (PROJECT / folder).glob('*.py'):
                tree = ast.parse(source.read_text(encoding='utf-8'))
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        self.assertTrue(ast.get_docstring(node), f'{source.name}:{node.lineno} {node.name}')


if __name__ == '__main__':
    unittest.main()
