from django.test import TestCase

from ide.models.files import SourceFile


class TestAlloyTsxRouting(TestCase):
    """ An imported path decides which build step owns the file.

    This is the whole trigger for TypeScript lowering: nothing inspects file
    extensions to decide whether to run the toolchain, it asks whether the
    project has a source file whose target is 'tsx'. If a path stops routing
    to that target, TypeScript projects silently build as if they had no
    TypeScript in them. """

    def _details(self, path):
        return SourceFile.get_details_for_path('alloy', path)

    def test_tsx_directory_owns_ts_and_tsx(self):
        self.assertEqual(self._details('src/tsx/main.tsx'), ('main.tsx', 'tsx'))
        self.assertEqual(self._details('src/tsx/lib/util.ts'), ('lib/util.ts', 'tsx'))

    def test_tsx_is_matched_before_the_bare_src_prefix(self):
        # 'app' maps to ['src/c', 'src'], so a plain dict or a reordered
        # OrderedDict would route src/tsx/main.tsx to the C compiler instead.
        self.assertEqual(self._details('src/tsx/main.tsx')[1], 'tsx')
        self.assertEqual(self._details('src/main.c')[1], 'app')

    def test_tsx_rejects_other_extensions(self):
        # Anything the compiler cannot read must fail at import rather than
        # land in src/tsx and break the build later.
        with self.assertRaises(ValueError):
            self._details('src/tsx/readme.md')

    def test_assets_accept_any_extension(self):
        # Assets are whatever the embedded-JS manifest points at, including
        # binaries with no meaningful extension.
        self.assertEqual(self._details('assets/dial.png'), ('dial.png', 'assets'))
        self.assertEqual(self._details('assets/fonts/tiny.ttf'), ('fonts/tiny.ttf', 'assets'))

    def test_existing_alloy_targets_are_unchanged(self):
        self.assertEqual(self._details('src/pkjs/index.js'), ('index.js', 'pkjs'))
        self.assertEqual(self._details('src/embeddedjs/main.js'), ('main.js', 'embeddedjs'))

    def test_typescript_sources_are_text(self):
        # Binary detection decides whether the IDE opens a file in the editor
        # or treats it as a resource blob.
        self.assertIn('.ts', SourceFile.TEXT_EXTENSIONS)
        self.assertIn('.tsx', SourceFile.TEXT_EXTENSIONS)
