import io
import json
import os
import shutil
import tempfile
import zipfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from ide.models.files import SourceFile
from ide.models.project import Project
from ide.utils.sdk.manifest import generate_v3_manifest_dict


class TestExportDevTooling(TestCase):
    """ Exported manifests must let a TypeScript project build locally.

    Hosted builds run the image-pinned toolchain, so the assembled (build-time)
    manifest omits it; the exported manifest instead carries the toolchain as a
    devDependency plus a build script, because outside CloudPebble that is the
    only way the project can build at all. """

    def setUp(self):
        self.user = User.objects.create_user('exporter', 'e@test.test', 'testpass')
        self.project = Project.objects.create(
            owner=self.user, name='tsface', project_type='alloy',
            app_short_name='tsface', app_long_name='TS Face', app_company_name='test',
        )
        self.toolchain_root = tempfile.mkdtemp()
        pkg_dir = os.path.join(self.toolchain_root, 'node_modules', 'pebble-signals')
        os.makedirs(pkg_dir)
        with open(os.path.join(pkg_dir, 'package.json'), 'w') as handle:
            json.dump({'name': 'pebble-signals', 'version': '1.2.3'}, handle)
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

    def _add_tsx_source(self):
        SourceFile.objects.create(project=self.project, file_name='main.tsx', target='tsx')

    def test_export_manifest_carries_toolchain_for_tsx_project(self):
        self._add_tsx_source()
        with override_settings(TS_TOOLCHAIN=self.toolchain):
            manifest = generate_v3_manifest_dict(self.project, [], for_export=True)
        self.assertEqual(manifest['devDependencies'], {'pebble-signals': '^1.2.3'})
        self.assertEqual(
            manifest['scripts']['build'],
            'node node_modules/pebble-signals/dist/build.mjs --app main',
        )

    def test_build_manifest_omits_toolchain(self):
        # The hosted build must not npm-install a toolchain it never runs.
        self._add_tsx_source()
        with override_settings(TS_TOOLCHAIN=self.toolchain):
            manifest = generate_v3_manifest_dict(self.project, [])
        self.assertNotIn('devDependencies', manifest)
        self.assertNotIn('scripts', manifest)

    def test_export_manifest_untouched_without_tsx_sources(self):
        SourceFile.objects.create(project=self.project, file_name='main.js', target='embeddedjs')
        with override_settings(TS_TOOLCHAIN=self.toolchain):
            manifest = generate_v3_manifest_dict(self.project, [], for_export=True)
        self.assertNotIn('devDependencies', manifest)
        self.assertNotIn('scripts', manifest)

    def test_export_manifest_untouched_without_installed_toolchain(self):
        self._add_tsx_source()
        toolchain = dict(self.toolchain, root='')
        with override_settings(TS_TOOLCHAIN=toolchain):
            manifest = generate_v3_manifest_dict(self.project, [], for_export=True)
        self.assertNotIn('devDependencies', manifest)
        self.assertNotIn('scripts', manifest)

    def test_exported_archive_carries_the_tooling(self):
        """ The wiring, not the helper: deleting for_export=True from
        add_project_to_archive leaves the tests above green but ships a zip
        nobody can build. """
        # Local import: ide.tasks.archive pulls in celery at module scope.
        from ide.tasks.archive import add_project_to_archive

        source = SourceFile.objects.create(project=self.project, file_name='main.tsx', target='tsx')
        source.save_text('export default 1;\n')

        buf = io.BytesIO()
        with override_settings(TS_TOOLCHAIN=self.toolchain), zipfile.ZipFile(buf, 'w') as archive:
            add_project_to_archive(archive, self.project)

        with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as archive:
            names = {name.split('/', 1)[1] for name in archive.namelist()}
            manifest = json.loads(archive.read(
                [n for n in archive.namelist() if n.endswith('package.json')][0]))

        self.assertIn('src/tsx/main.tsx', names)
        self.assertIn('tsconfig.json', names)
        self.assertEqual(manifest['devDependencies'], {'pebble-signals': '^1.2.3'})
        # The exported script is the toolchain's full pipeline. --generate-only
        # belongs to the hosted build, where the SDK finishes the job.
        self.assertNotIn('--generate-only', manifest['scripts']['build'])

    def test_export_omits_tooling_when_the_version_cannot_be_read(self):
        """ '^0.0.0' is a dependency npm cannot resolve: a manifest that names
        no toolchain fails honestly, one that names an impossible version
        fails at install time with nothing to act on. """
        self._add_tsx_source()
        os.unlink(os.path.join(self.toolchain_root, 'node_modules',
                               'pebble-signals', 'package.json'))
        with override_settings(TS_TOOLCHAIN=self.toolchain):
            manifest = generate_v3_manifest_dict(self.project, [], for_export=True)
        self.assertNotIn('devDependencies', manifest)
        self.assertNotIn('scripts', manifest)
