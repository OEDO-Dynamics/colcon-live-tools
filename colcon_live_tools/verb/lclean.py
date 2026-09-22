# Copyright 2026 OEDO Dynamics Inc.
# Licensed under the Apache License, Version 2.0

"""
`colcon lclean` (alias: `colcon lc`) -- a `catkin clean`-equivalent for
colcon workspaces.

`colcon build` has no built-in "clean" verb; the usual advice is to just
`rm -rf build install log` yourself. This verb does exactly that (nothing
more -- no per-package granularity, no build profiles), but: it only
removes directories that actually exist, it always says what it is about
to remove before removing it, and it asks for confirmation unless `-y`/
`--yes` is passed (matching `catkin clean`'s own default of asking first).

Usage::

    colcon lclean        # or: colcon lc
    colcon lclean -y      # skip the confirmation prompt
"""

import shutil
import sys
from pathlib import Path

from colcon_core.plugin_system import satisfies_version
from colcon_core.verb import VerbExtensionPoint

from .._i18n import detect_language

_TEXT = {
    'en': {
        'description': (
            "Remove a colcon workspace's build/install/log directories "
            "(a 'catkin clean' equivalent) -- asks for confirmation "
            'unless -y/--yes is passed'
        ),
        'build_base_help': "Same meaning as 'colcon build --build-base'",
        'install_base_help': "Same meaning as 'colcon build --install-base'",
        'log_base_help': "Same meaning as colcon's top-level --log-base",
        'yes_help': "Don't ask for confirmation before removing anything",
        'nothing': 'Nothing to clean: {paths} do not exist',
        'about_to_remove': 'About to remove:',
        'confirm_prompt': 'Remove these? [y/N] ',
        'aborted': 'Aborted, nothing was removed',
        'removed': 'Removed {path}',
        'done': 'Done',
    },
    'ja': {
        'description': (
            'colcon ワークスペースの build/install/log ディレクトリを削除する '
            "('catkin clean' 相当) -- -y/--yes を渡さない限り確認を求める"
        ),
        'build_base_help': "'colcon build --build-base' と同じ意味",
        'install_base_help': "'colcon build --install-base' と同じ意味",
        'log_base_help': 'colcon のトップレベル --log-base と同じ意味',
        'yes_help': '削除前の確認をスキップする',
        'nothing': '削除対象なし: {paths} は存在しません',
        'about_to_remove': '以下を削除します:',
        'confirm_prompt': '削除しますか？ [y/N] ',
        'aborted': '中止しました。何も削除していません',
        'removed': '{path} を削除しました',
        'done': '完了',
    },
    'pt': {
        'description': (
            'Remove os diretórios build/install/log de um workspace colcon '
            "(equivalente a 'catkin clean') -- pede confirmação a menos "
            'que -y/--yes seja usado'
        ),
        'build_base_help': "Mesmo significado de 'colcon build --build-base'",
        'install_base_help': (
            "Mesmo significado de 'colcon build --install-base'"),
        'log_base_help': (
            'Mesmo significado do --log-base de nível superior do colcon'),
        'yes_help': 'Não pede confirmação antes de remover nada',
        'nothing': 'Nada para limpar: {paths} não existem',
        'about_to_remove': 'Removendo:',
        'confirm_prompt': 'Remover isso? [y/N] ',
        'aborted': 'Abortado, nada foi removido',
        'removed': '{path} removido',
        'done': 'Concluído',
    },
}


def _text():
    return _TEXT[detect_language()]


class LiveCleanVerb(VerbExtensionPoint):
    """Remove a workspace's build/install/log directories, with confirmation."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(VerbExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')
        self.__doc__ = _text()['description']

    def add_arguments(self, *, parser):  # noqa: D102
        text = _text()
        parser.add_argument(
            '--build-base', default='build', metavar='PATH',
            help=text['build_base_help'])
        parser.add_argument(
            '--install-base', default='install', metavar='PATH',
            help=text['install_base_help'])
        parser.add_argument(
            '--log-base', default='log', metavar='PATH',
            help=text['log_base_help'])
        parser.add_argument(
            '-y', '--yes', action='store_true',
            help=text['yes_help'])

    def main(self, *, context):  # noqa: D102
        text = _text()
        args = context.args
        candidates = [
            Path(args.build_base), Path(args.install_base),
            Path(args.log_base),
        ]
        existing = [p for p in candidates if p.exists()]

        if not existing:
            print(text['nothing'].format(
                paths=', '.join(str(p) for p in candidates)))
            return 0

        print(text['about_to_remove'])
        for path in existing:
            print('  ' + str(path.resolve()))

        if not args.yes:
            try:
                answer = input(text['confirm_prompt'])
            except (EOFError, KeyboardInterrupt):
                print()
                answer = ''
            if answer.strip().lower() not in ('y', 'yes'):
                print(text['aborted'])
                return 1

        for path in existing:
            shutil.rmtree(path, ignore_errors=False)
            print(text['removed'].format(path=path))
            sys.stdout.flush()

        print(text['done'])
        return 0


class LiveCleanVerbShort(LiveCleanVerb):
    """Alias for `colcon lclean` -- identical behavior, shorter to type.

    A separate subclass for the same reason `LiveBuildVerbShort` is: two
    entry points resolving to the same class would share one cached
    instance in colcon-core's plugin system, making the registered verb
    name depend on entry point iteration order instead of being stable.
    """
