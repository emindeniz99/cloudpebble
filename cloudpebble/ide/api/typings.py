""" Typings for the IDE's TypeScript language service.

The static alloy-typings.json covers the platform APIs. TypeScript-authored
projects also need the toolchain's own declarations, and those have to match
the toolchain the build actually runs — so they are read from the pinned
install rather than checked in, and go stale only when the image does.
"""
import json
import logging
import os

from django.conf import settings
from django.views.decorators.http import require_safe

from utils.jsonview import json_view

__author__ = 'emindeniz99'
logger = logging.getLogger(__name__)

_cache = None


def _toolchain_typings():
    """ {'<types_as><name>.d.ts': <declaration source>} for the pinned toolchain. """
    global _cache
    if _cache is not None:
        return _cache
    toolchain = settings.TS_TOOLCHAIN
    bundle = {}
    if toolchain.get('root'):
        types_dir = os.path.join(toolchain['root'], 'node_modules',
                                 toolchain['package'], toolchain['typings'])
        if os.path.isdir(types_dir):
            for name in sorted(os.listdir(types_dir)):
                if not name.endswith('.d.ts'):
                    continue
                try:
                    with open(os.path.join(types_dir, name), 'r') as f:
                        bundle['%s%s' % (toolchain['types_as'], name)] = f.read()
                except OSError:
                    logger.exception("Could not read toolchain typing %s", name)
    _cache = bundle
    return bundle


@require_safe
@json_view(include_success=False)
def toolchain_typings(request):
    return _toolchain_typings()
