import io
import json
import os
import uuid
import zipfile

from django.conf import settings

EXAMPLES_ROOT = '/opt/pebble-examples'
# The TypeScript starter is not an example on disk: it is the scaffold the
# installed toolchain ships, so it always matches the compiler that will
# build it.
TOOLCHAIN_TEMPLATE_ID = 'typescript/starter'
WATCHFACE_TUTORIAL_ROOT = '/opt/watchface-tutorial'
WATCHFACE_TUTORIAL_PREFIX = 'watchface-tutorial'
WATCHFACE_TUTORIAL_PARTS = [
    ('part1', 'Your First Watchface'),
    ('part2', 'Customizing Your Watchface'),
    ('part3', 'Adding Battery and Bluetooth'),
    ('part4', 'Adding Weather'),
    ('part5', 'Timeline Peek'),
    ('part6', 'Adding User Settings'),
]


def _examples_root():
    return EXAMPLES_ROOT


def _watchface_tutorial_root():
    return WATCHFACE_TUTORIAL_ROOT


def _template_display_name(path):
    if path.startswith(WATCHFACE_TUTORIAL_PREFIX + '/'):
        slug = path.split('/')[-1]
        label_map = dict(WATCHFACE_TUTORIAL_PARTS)
        if slug in label_map:
            return label_map[slug]
    if path.startswith('piu/watchfaces/'):
        return path.split('/')[-1]
    if path.startswith('piu/apps/'):
        return path.split('/')[-1]
    return path


def _template_group(path):
    if path.startswith(WATCHFACE_TUTORIAL_PREFIX + '/'):
        return 'watchface-tutorial/'
    if path.startswith('piu/watchfaces/'):
        return 'watchfaces/'
    if path.startswith('piu/apps/'):
        return 'apps/'
    return None


def _ordered_paths(paths):
    unique_paths = []
    seen = set()
    for item in paths:
        if item not in seen:
            seen.add(item)
            unique_paths.append(item)

    def _remainder_key(value):
        return value.lower()

    tutorial = [p for p in unique_paths if p.startswith(WATCHFACE_TUTORIAL_PREFIX + '/')]
    tutorial_order = [WATCHFACE_TUTORIAL_PREFIX + '/' + slug for slug, _ in WATCHFACE_TUTORIAL_PARTS]
    tutorial_rank = {path: idx for idx, path in enumerate(tutorial_order)}
    tutorial = sorted(tutorial, key=lambda p: tutorial_rank.get(p, 9999))

    watchfaces = sorted([p for p in unique_paths if p.startswith('piu/watchfaces/')], key=_remainder_key)
    apps = sorted([p for p in unique_paths if p.startswith('piu/apps/')], key=_remainder_key)

    consumed = set(tutorial + watchfaces + apps)
    remainder = sorted([p for p in unique_paths if p not in consumed], key=_remainder_key)
    return tutorial + watchfaces + apps + remainder


def _toolchain_template_dir():
    """ templates/app inside the pinned toolchain, or None. """
    toolchain = getattr(settings, 'TS_TOOLCHAIN', {})
    if not toolchain.get('root'):
        return None
    path = os.path.join(toolchain['root'], 'node_modules',
                        toolchain['package'], toolchain['template'])
    return path if os.path.isdir(path) else None


def _render_toolchain_template(target_dir):
    """ Zip templates/app, filling in the scaffold's placeholders.

    The template ships package.json.tmpl rather than package.json — the
    scaffold CLI substitutes a name, author and uuid. The importer needs a
    real manifest to recognise a project, so do the same here; CloudPebble
    overwrites the metadata from the project settings immediately afterwards.
    """
    values = {
        '__PKG_NAME__': 'pebble-app',
        '__APP_NAME__': 'Pebble App',
        '__AUTHOR__': 'CloudPebble',
        '__UUID__': str(uuid.uuid4()),
        '__PKG_VERSION__': toolchain_version(),
    }
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for dirpath, dirnames, filenames in os.walk(target_dir):
            dirnames[:] = [d for d in dirnames if not d.startswith('.') and d != '.git']
            for filename in filenames:
                if filename.startswith('.') or filename == 'gitignore':
                    continue
                full_path = os.path.join(dirpath, filename)
                arcname = os.path.relpath(full_path, target_dir)
                if filename.endswith('.tmpl'):
                    with open(full_path, 'r') as handle:
                        content = handle.read()
                    for placeholder, value in values.items():
                        content = content.replace(placeholder, value)
                    archive.writestr(arcname[:-len('.tmpl')], content)
                else:
                    archive.write(full_path, arcname=arcname)
    return bundle.getvalue()


def toolchain_version():
    toolchain = getattr(settings, 'TS_TOOLCHAIN', {})
    try:
        with open(os.path.join(toolchain['root'], 'node_modules',
                               toolchain['package'], 'package.json')) as handle:
            return json.load(handle)['version']
    except (OSError, ValueError, KeyError):
        return '0.0.0'


def _is_moddable_project(project_dir):
    package_json = os.path.join(project_dir, 'package.json')
    src_embeddedjs = os.path.join(project_dir, 'src', 'embeddedjs')
    if not os.path.isfile(package_json) or not os.path.isdir(src_embeddedjs):
        return False

    try:
        with open(package_json, 'r') as handle:
            package_data = json.load(handle)
    except (ValueError, OSError):
        return False

    return package_data.get('pebble', {}).get('projectType') == 'moddable'


def list_alloy_templates():
    paths = []
    examples_root = _examples_root()
    if os.path.isdir(examples_root):
        for dirpath, dirnames, _ in os.walk(examples_root):
            dirnames[:] = [d for d in dirnames if not d.startswith('.') and d != '.git']
            if _is_moddable_project(dirpath):
                relpath = os.path.relpath(dirpath, examples_root).replace('\\', '/')
                paths.append(relpath)
                dirnames[:] = []

    tutorial_root = _watchface_tutorial_root()
    if os.path.isdir(tutorial_root):
        for slug, _ in WATCHFACE_TUTORIAL_PARTS:
            part_dir = os.path.join(tutorial_root, slug)
            if os.path.isdir(part_dir) and _is_moddable_project(part_dir):
                paths.append('%s/%s' % (WATCHFACE_TUTORIAL_PREFIX, slug))

    templates = []
    # The toolchain's own scaffold, when one is installed. Listed first: it is
    # the only entry here that starts you in TypeScript.
    if _toolchain_template_dir():
        templates.append({
            'id': TOOLCHAIN_TEMPLATE_ID,
            'path': TOOLCHAIN_TEMPLATE_ID,
            'label': 'TypeScript starter',
            'dir': 'typescript',
            'group': 'typescript',
        })

    if not paths:
        return templates

    for path in _ordered_paths(paths):
        template_dir = _template_group(path)
        templates.append({
            'id': path,
            'path': path,
            'label': _template_display_name(path),
            'dir': template_dir,
            'group': template_dir,
        })
    return templates


def _resolve_template_directory(template_path):
    if template_path.startswith(WATCHFACE_TUTORIAL_PREFIX + '/'):
        slug = template_path.split('/', 1)[1]
        root = _watchface_tutorial_root()
        return os.path.normpath(os.path.join(root, slug)), os.path.normpath(root)
    root = _examples_root()
    return os.path.normpath(os.path.join(root, template_path)), os.path.normpath(root)


def build_template_archive(template_path):
    if template_path == TOOLCHAIN_TEMPLATE_ID:
        target_dir = _toolchain_template_dir()
        if not target_dir:
            raise ValueError('No TypeScript toolchain is installed')
        return _render_toolchain_template(target_dir)

    target_dir, root = _resolve_template_directory(template_path)
    if not target_dir.startswith(root + os.sep):
        raise ValueError('Invalid template path')
    if not os.path.isdir(target_dir):
        raise ValueError('Template path does not exist')

    if not _is_moddable_project(target_dir):
        raise ValueError('Template is not a valid JavaScript SDK project')

    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for dirpath, dirnames, filenames in os.walk(target_dir):
            dirnames[:] = [d for d in dirnames if not d.startswith('.') and d != '.git']
            for filename in filenames:
                if filename.startswith('.'):
                    continue
                full_path = os.path.join(dirpath, filename)
                arcname = os.path.relpath(full_path, target_dir)
                archive.write(full_path, arcname=arcname)

    return bundle.getvalue()
