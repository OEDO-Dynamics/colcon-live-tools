# Copyright 2026 OEDO Dynamics Inc.
# Licensed under the Apache License, Version 2.0

"""
`colcon lbuild` (alias: `colcon lb`) -- `colcon build` with opinionated,
catkin_tools-like defaults, so you do not have to type a wall of flags
every time.

It accepts every argument `colcon build` does (it literally reuses
`BuildVerb.add_arguments`), then changes three defaults:

- ``--event-handlers``: disables every installed handler that would
  otherwise clutter the terminal alongside (or duplicate what is already
  shown by) `colcon-live-tools`'s own live board -- `status`/`summary`
  (colcon-notification/colcon-output), `console_start_end`,
  `console_stderr`, `console_cohesion`, `console_direct`,
  `console_package_list` -- and enables ``live_status+``. Nothing is lost
  by turning those off: `live_status` sees every stdout/stderr line
  regardless of which other handlers are enabled, and reports warnings,
  errors and full failure output itself.
- ``--continue-on-error``: on by default. An unrelated package failing does
  not abort every other in-flight package; only packages that (recursively)
  depend on the failed one are skipped. Pass ``--no-continue-on-error`` to
  restore colcon's own default (abort everything on the first failure).
- ``--parallel-workers``: defaults to ``0`` (no limit) instead of colcon's
  default of ``2``. ``-j``/``--jobs`` is a short alias for the same option,
  for when you *do* want to cap it, e.g. ``colcon lbuild -j 4``.

Passing any of these explicitly (``--event-handlers ...``,
``--continue-on-error``, ``--no-continue-on-error``, ``-j``/``--jobs``/
``--parallel-workers``) overrides the corresponding default; everything
else behaves exactly like `colcon build`.

This verb's own description and the help text for the arguments it adds or
overrides are shown in Japanese, (Brazilian) Portuguese or English,
guessed from the environment's locale (``LC_ALL``/``LC_MESSAGES``/``LANG``/
``LANGUAGE``) -- see `colcon_live_tools._i18n`. Arguments inherited
unchanged from `colcon build` (``--cmake-args``, ``--merge-install``, ...)
keep their own, English-only help text, since translating those would mean
patching `colcon-core` itself.
"""

from colcon_core.event_handler import get_event_handler_extensions
from colcon_core.plugin_system import satisfies_version
from colcon_core.verb import VerbExtensionPoint
from colcon_core.verb.build import BuildVerb

from .._i18n import detect_language

_DEFAULT_PARALLEL_WORKERS = 0

#: handlers worth turning off by default -- only ones that are actually
#: installed get disabled, to avoid the KeyError described in
#: `_default_event_handlers`
_HANDLERS_TO_DISABLE = (
    'status', 'summary', 'console_start_end', 'console_stderr',
    'console_cohesion', 'console_direct', 'console_package_list',
)

_TEXT = {
    'en': {
        'description': (
            "colcon build with catkin_tools-like defaults: live status "
            'board, colors and per-package warning counts on; parallel '
            "builds continue past an unrelated package's failure; no "
            'worker-count cap. Every colcon build argument still works -- '
            'pass any flag below to override one of these defaults'
        ),
        'event_handlers_help': (
            "Enable (+) or disable (-) event handlers (default for "
            "'colcon lbuild'/'colcon lb': {defaults})"
        ),
        'no_continue_on_error_help': (
            "Undo this verb's default and restore colcon build's own "
            'default: abort every in-progress package as soon as one '
            'fails, instead of only skipping packages that '
            '(recursively) depend on it'
        ),
        'jobs_help': (
            "Alias for --parallel-workers. Default: %(default)s "
            "('colcon build' itself defaults to 2)"
        ),
        'parallel_workers_help': (
            'The maximum number of packages to process in parallel, '
            "or '0' for no limit (default for 'colcon lbuild'/"
            "'colcon lb': {default}; same option as -j/--jobs)"
        ),
    },
    'ja': {
        'description': (
            'catkin_tools 風のデフォルトを持つ colcon build: ライブ状況表示・色付け・'
            'パッケージ別の警告数表示が有効。無関係なパッケージが失敗しても並列ビルドは'
            '続行し、並列数の上限もない。colcon build の引数はすべてそのまま使え、'
            '以下のフラグでそれぞれのデフォルトを上書きできる'
        ),
        'event_handlers_help': (
            'イベントハンドラの有効化(+)/無効化(-) '
            "('colcon lbuild'/'colcon lb' のデフォルト: {defaults})"
        ),
        'no_continue_on_error_help': (
            'このverbのデフォルトを取り消し、colcon build本来のデフォルトに戻す: '
            '1パッケージが失敗した時点で(依存する側だけを再帰的にスキップするのでは'
            'なく)進行中の全パッケージを中断する'
        ),
        'jobs_help': (
            '--parallel-workers の別名。デフォルト: %(default)s '
            "('colcon build' 自体のデフォルトは2)"
        ),
        'parallel_workers_help': (
            "並列処理するパッケージ数の上限。'0' は無制限 "
            "('colcon lbuild'/'colcon lb' のデフォルト: {default}。"
            '-j/--jobs と同じオプション)'
        ),
    },
    'pt': {
        'description': (
            'colcon build com padrões no estilo catkin_tools: painel de '
            'status em tempo real, cores e contagem de warnings por '
            'pacote ativados; builds paralelos continuam mesmo com falha '
            'em um pacote não relacionado; sem limite de workers. Todos '
            'os argumentos do colcon build continuam funcionando -- use '
            'qualquer flag abaixo para sobrepor um desses padrões'
        ),
        'event_handlers_help': (
            'Habilita (+) ou desabilita (-) manipuladores de evento '
            "(padrão para 'colcon lbuild'/'colcon lb': {defaults})"
        ),
        'no_continue_on_error_help': (
            'Desfaz o padrão deste verbo e volta ao padrão do próprio '
            'colcon build: aborta todos os pacotes em andamento assim '
            'que um falha, em vez de pular apenas os pacotes que '
            'dependem (recursivamente) dele'
        ),
        'jobs_help': (
            'Atalho para --parallel-workers. Padrão: %(default)s '
            "(o próprio 'colcon build' usa 2 por padrão)"
        ),
        'parallel_workers_help': (
            'Número máximo de pacotes processados em paralelo, ou '
            "'0' para sem limite (padrão para 'colcon lbuild'/'colcon lb': "
            '{default}; mesma opção que -j/--jobs)'
        ),
    },
}


def _text():
    return _TEXT[detect_language()]


def _find_action(parser, dest):
    """Look up an already-added action on `parser` by its `dest`."""
    for action in parser._actions:  # noqa: SLF001 (no public lookup-by-dest API)
        if action.dest == dest:
            return action
    return None


def _default_event_handlers():
    """
    Build the ``--event-handlers`` default for this verb.

    Several of these handlers ship in separate packages (``colcon-core``,
    ``colcon-notification``, ``colcon-output``), not all of which are
    necessarily installed, and referring to a handler name that is not
    actually registered makes ``colcon build`` crash with a bare
    ``KeyError`` (see ``apply_event_handler_arguments`` in
    ``colcon_core.event_handler``), so only disable the ones that exist.
    ``live_status`` is always included since installing this package is
    what is registering it in the first place.
    """
    try:
        installed = get_event_handler_extensions(context=None)
    except Exception:  # noqa: BLE001 -- never let discovery break the verb
        installed = {}
    handlers = [
        f'{name}-' for name in _HANDLERS_TO_DISABLE if name in installed]
    handlers.append('live_status+')
    return handlers


class LiveBuildVerb(VerbExtensionPoint):
    """Build packages, with the live status board on and sane parallel defaults."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(VerbExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')
        # a single BuildVerb instance is shared between add_arguments() and
        # main(): BuildVerb.add_arguments() stashes
        # `task_argument_destinations` on `self`, which main() then reads
        self._build_verb = BuildVerb()
        # colcon_core.plugin_system.get_first_line_doc() reads
        # `extension.__doc__`, which -- set on the *instance* like this,
        # rather than only on the class -- takes precedence over the class
        # docstring above; this is what lets `colcon --help`'s one-line
        # verb list and `colcon lbuild --help`'s description be localized
        self.__doc__ = _text()['description']

    def add_arguments(self, *, parser):  # noqa: D102
        text = _text()

        # every argument `colcon build` has, unchanged
        self._build_verb.add_arguments(parser=parser)

        # opinionated defaults -- each is still overridable on the CLI
        default_event_handlers = _default_event_handlers()
        parser.set_defaults(
            event_handlers=default_event_handlers,
            continue_on_error=True,
        )

        # colcon build's own --event-handlers help text bakes in *its*
        # natural default as a literal string at add_argument() time, so
        # it would otherwise keep advertising the wrong default here
        event_handlers_action = _find_action(parser, 'event_handlers')
        if event_handlers_action is not None:
            event_handlers_action.help = text['event_handlers_help'].format(
                defaults=' '.join(default_event_handlers))

        parser.add_argument(
            '--no-continue-on-error', dest='continue_on_error',
            action='store_false',
            help=text['no_continue_on_error_help'])
        parser.add_argument(
            '-j', '--jobs', dest='parallel_workers', metavar='NUMBER',
            type=int,
            help=text['jobs_help'])
        # the '-j'/'--jobs' action above shares a dest with the
        # '--parallel-workers' action that add_executor_arguments() already
        # added inside self._build_verb.add_arguments(); since that action
        # was added first, its default -- set here -- is what actually
        # populates the namespace unless the user passes -j/--jobs/
        # --parallel-workers explicitly.
        parser.set_defaults(parallel_workers=_DEFAULT_PARALLEL_WORKERS)
        parallel_workers_action = _find_action(parser, 'parallel_workers')
        if parallel_workers_action is not None:
            parallel_workers_action.help = text[
                'parallel_workers_help'].format(
                    default=_DEFAULT_PARALLEL_WORKERS)

    def main(self, *, context):  # noqa: D102
        return self._build_verb.main(context=context)


class LiveBuildVerbShort(LiveBuildVerb):
    """Alias for `colcon lbuild` -- identical behavior, shorter to type.

    Registered as its own subclass (rather than reusing `LiveBuildVerb`
    under a second entry point name) because colcon-core caches one
    instance per extension *class*: two entry points resolving to the
    same class would silently share a single instance, and the verb name
    that instance's `add_arguments()`/`main()` are dispatched under would
    depend on iteration order instead of being stable.
    """
