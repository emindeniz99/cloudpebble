import json
import os
import shutil
import tempfile

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
