import json
import io
import os
import shutil
import tempfile
import zipfile
import mock

from django.test import TestCase, override_settings

from ide.utils.alloy_templates import list_alloy_templates, build_template_archive


class TestAlloyTemplates(TestCase):
    def setUp(self):
        self.examples_root = tempfile.mkdtemp()
        self.tutorial_root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.examples_root)
        shutil.rmtree(self.tutorial_root)

    def _write_template(self, relpath, project_type='moddable'):
        template_root = os.path.join(self.examples_root, relpath)
        os.makedirs(os.path.join(template_root, 'src', 'embeddedjs', 'emery'))
        with open(os.path.join(template_root, 'src', 'embeddedjs', 'main.js'), 'w') as handle:
            handle.write('trace("ok");\n')
        with open(os.path.join(template_root, 'src', 'embeddedjs', 'hours.pdc'), 'wb') as handle:
            handle.write(b'PDC')
        with open(os.path.join(template_root, 'src', 'embeddedjs', 'emery', 'dial.png'), 'wb') as handle:
            handle.write(b'\x89PNG\r\n')
        with open(os.path.join(template_root, 'package.json'), 'w') as handle:
            json.dump({'name': relpath, 'pebble': {'projectType': project_type}}, handle)

    def _write_tutorial_part(self, part):
        self._write_template(os.path.join('tutorial', part))
        src = os.path.join(self.examples_root, 'tutorial', part)
        dst = os.path.join(self.tutorial_root, part)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copytree(src, dst)

    @override_settings(TS_TOOLCHAIN={'root': ''})
    def test_list_alloy_templates_returns_empty_when_missing(self):
        with mock.patch('ide.utils.alloy_templates._examples_root', return_value='/tmp/unused'), \
             mock.patch('ide.utils.alloy_templates._watchface_tutorial_root', return_value='/tmp/unused'):
            self.assertEqual(list_alloy_templates(), [])

    @override_settings(TS_TOOLCHAIN={'root': ''})
    def test_list_alloy_templates_applies_requested_order(self):
        self._write_template('zzzapp')
        self._write_template('hellofetch')
        self._write_template('hellopebble')
        self._write_template('hellowatchface')
        self._write_template('piu/watchfaces/cupertino')
        self._write_template('piu/watchfaces/redmond')
        self._write_template('piu/watchfaces/london')
        self._write_template('piu/apps/words')
        self._write_template('piu/apps/gravity')
        self._write_template('another')
        self._write_template('nonmoddable', project_type='native')
        for part in ['part1', 'part2', 'part3', 'part4', 'part5', 'part6']:
            self._write_tutorial_part(part)

        with mock.patch('ide.utils.alloy_templates._examples_root', return_value=self.examples_root), \
             mock.patch('ide.utils.alloy_templates._watchface_tutorial_root', return_value=self.tutorial_root):
            templates = list_alloy_templates()

        ids = [template['id'] for template in templates]
        self.assertEqual(
            ids[:6],
            [
                'watchface-tutorial/part1',
                'watchface-tutorial/part2',
                'watchface-tutorial/part3',
                'watchface-tutorial/part4',
                'watchface-tutorial/part5',
                'watchface-tutorial/part6',
            ]
        )
        self.assertEqual(ids[6], 'piu/watchfaces/cupertino')
        self.assertEqual(ids[7:9], ['piu/watchfaces/london', 'piu/watchfaces/redmond'])
        self.assertEqual(ids[9:11], ['piu/apps/gravity', 'piu/apps/words'])
        self.assertGreater(ids.index('hellopebble'), ids.index('piu/apps/words'))
        self.assertGreater(ids.index('hellowatchface'), ids.index('piu/apps/words'))
        self.assertGreater(ids.index('hellofetch'), ids.index('piu/apps/words'))
        self.assertIn('another', ids)
        self.assertIn('zzzapp', ids)
        self.assertNotIn('nonmoddable', ids)
        labels = {t['id']: t['label'] for t in templates}
        self.assertEqual(labels['watchface-tutorial/part1'], 'Your First Watchface')
        self.assertEqual(labels['watchface-tutorial/part2'], 'Customizing Your Watchface')
        self.assertEqual(labels['watchface-tutorial/part3'], 'Adding Battery and Bluetooth')
        self.assertEqual(labels['watchface-tutorial/part4'], 'Adding Weather')
        self.assertEqual(labels['watchface-tutorial/part5'], 'Timeline Peek')
        self.assertEqual(labels['watchface-tutorial/part6'], 'Adding User Settings')
        groups = {t['id']: t['group'] for t in templates}
        self.assertEqual(groups['watchface-tutorial/part1'], 'watchface-tutorial/')
        dirs = {t['id']: t['dir'] for t in templates}
        self.assertEqual(dirs['watchface-tutorial/part1'], 'watchface-tutorial/')

        watchface_labels = [t['label'] for t in templates if t['group'] == 'watchfaces/']
        app_labels = [t['label'] for t in templates if t['group'] == 'apps/']
        self.assertEqual(watchface_labels, ['cupertino', 'london', 'redmond'])
        self.assertEqual(app_labels, ['gravity', 'words'])

    def test_build_template_archive_contains_project_files(self):
        self._write_template('hellopebble')
        with mock.patch('ide.utils.alloy_templates._examples_root', return_value=self.examples_root), \
             mock.patch('ide.utils.alloy_templates._watchface_tutorial_root', return_value=self.tutorial_root):
            archive_bytes = build_template_archive('hellopebble')

        with zipfile.ZipFile(io.BytesIO(archive_bytes), 'r') as zf:
            names = set(zf.namelist())

        self.assertIn('package.json', names)
        self.assertIn('src/embeddedjs/main.js', names)
        self.assertIn('src/embeddedjs/hours.pdc', names)
        self.assertIn('src/embeddedjs/emery/dial.png', names)

    def test_build_template_archive_rejects_traversal(self):
        self._write_template('hellopebble')
        with mock.patch('ide.utils.alloy_templates._examples_root', return_value=self.examples_root), \
             mock.patch('ide.utils.alloy_templates._watchface_tutorial_root', return_value=self.tutorial_root):
            with self.assertRaises(ValueError):
                build_template_archive('../outside')

    def test_build_template_archive_supports_watchface_tutorial_path(self):
        self._write_tutorial_part('part1')
        with mock.patch('ide.utils.alloy_templates._examples_root', return_value=self.examples_root), \
             mock.patch('ide.utils.alloy_templates._watchface_tutorial_root', return_value=self.tutorial_root):
            archive_bytes = build_template_archive('watchface-tutorial/part1')

        with zipfile.ZipFile(io.BytesIO(archive_bytes), 'r') as zf:
            names = set(zf.namelist())
        self.assertIn('package.json', names)
        self.assertIn('src/embeddedjs/main.js', names)


class TestToolchainStarterTemplate(TestCase):
    """ The starter is read from the installed toolchain, not checked in here.

    That is what keeps the scaffold and the compiler that builds it in step, so
    the tests describe an install on disk rather than a fixture in the repo. """

    def setUp(self):
        self.toolchain_root = tempfile.mkdtemp()
        self.template_dir = os.path.join(
            self.toolchain_root, 'node_modules', 'pebble-signals', 'templates', 'app')
        os.makedirs(os.path.join(self.template_dir, 'src', 'tsx'))
        with open(os.path.join(self.toolchain_root, 'node_modules', 'pebble-signals',
                               'package.json'), 'w') as handle:
            json.dump({'name': 'pebble-signals', 'version': '9.9.9'}, handle)
        with open(os.path.join(self.template_dir, 'package.json.tmpl'), 'w') as handle:
            handle.write('{"name": "__PKG_NAME__", "devDependencies": '
                         '{"pebble-signals": "^__PKG_VERSION__"}}')
        with open(os.path.join(self.template_dir, 'src', 'tsx', 'main.tsx'), 'w') as handle:
            handle.write('export default 1;\n')
        with open(os.path.join(self.template_dir, 'gitignore'), 'w') as handle:
            handle.write('node_modules\n')
        self.toolchain = {
            'root': self.toolchain_root,
            'package': 'pebble-signals',
            'build': ['dist/build.mjs', '--app', 'main'],
            'generate_args': ['--generate-only'],
            'typings': 'src/embeddedjs/runtime-types',
            'types_as': 'runtime/',
            'template': 'templates/app',
        }

    def tearDown(self):
        shutil.rmtree(self.toolchain_root)

    def _patched_roots(self):
        return mock.patch('ide.utils.alloy_templates._examples_root', return_value='/tmp/unused'), \
            mock.patch('ide.utils.alloy_templates._watchface_tutorial_root', return_value='/tmp/unused')

    def test_starter_is_offered_first_when_a_toolchain_is_installed(self):
        # It leads the list because it is the only entry that starts a project
        # in TypeScript; burying it under the JavaScript examples is what the
        # feature looked like before this existed.
        examples, tutorial = self._patched_roots()
        with examples, tutorial, override_settings(TS_TOOLCHAIN=self.toolchain):
            templates = list_alloy_templates()
        self.assertEqual([t['id'] for t in templates], ['typescript/starter'])

    def test_starter_is_absent_when_no_toolchain_is_installed(self):
        # A deployment that installs no toolchain cannot build TypeScript, so
        # offering the scaffold would hand the developer a broken project.
        examples, tutorial = self._patched_roots()
        with examples, tutorial, override_settings(TS_TOOLCHAIN=dict(self.toolchain, root='')):
            self.assertEqual(list_alloy_templates(), [])

    def test_starter_archive_is_substituted_and_renamed(self):
        examples, tutorial = self._patched_roots()
        with examples, tutorial, override_settings(TS_TOOLCHAIN=self.toolchain):
            archive_bytes = build_template_archive('typescript/starter')

        with zipfile.ZipFile(io.BytesIO(archive_bytes), 'r') as zf:
            names = set(zf.namelist())
            manifest = json.loads(zf.read('package.json'))
        # .tmpl is stripped, because the importer needs a real manifest to
        # recognise the archive as a project at all.
        self.assertIn('package.json', names)
        self.assertNotIn('package.json.tmpl', names)
        self.assertIn('src/tsx/main.tsx', names)
        self.assertNotIn('__PKG_VERSION__', json.dumps(manifest))
        # The scaffold pins the version actually installed, so an exported
        # project builds with the same compiler the hosted build used.
        self.assertEqual(manifest['devDependencies']['pebble-signals'], '^9.9.9')
