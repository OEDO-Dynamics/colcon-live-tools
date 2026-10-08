# Copyright 2026 OEDO Dynamics Inc.
# Licensed under the Apache License, Version 2.0

"""
`colcon ltest` (alias: `colcon lt`) -- `colcon test` with a readable result.

It accepts every argument `colcon test` does (it reuses `TestVerb`), and:

- shows the same live per-package board as `lbuild` while tests run;
- always exits non-zero when a test fails (`--return-code-on-test-failure`
  is on by default here);
- prints a summary when the run ends: tests / failures / errors / skipped per
  package, the names and first lines of the messages of failing test cases,
  and where the JUnit files are;
- picks an unused ``ROS_DOMAIN_ID`` for the run (``--isolated-domain``,
  default on) so tests started from another terminal cannot reach them, and
  the test traffic stays on loopback (``ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST``);
- can skip the user site-packages for test processes (``--no-user-site``),
  can turn skip reasons into failures (``--fail-on-skip``), and can rerun only
  what failed last time (``--retest-failed``);
- switches to the CI log (see `colcon_live_tools._ci`) when that is the right
  output, and writes the summary to ``$GITHUB_STEP_SUMMARY`` when it is set.

Usage::

    colcon ltest --packages-select my_pkg
    colcon lt --retest-failed
    colcon lt --fail-on-skip 'requires hardware' --no-isolated-domain
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from colcon_core.plugin_system import satisfies_version
from colcon_core.verb import VerbExtensionPoint
from colcon_core.verb.test import TestVerb

from .. import _ci
from .._i18n import detect_language
from .._junit import summarize_package
from .._test_report import build_rows
from .._test_report import render_annotations
from .._test_report import render_markdown
from .._test_report import render_text
from ..event_handler import run_recorder
from ..event_handler.live_status import _Paint
from .lbuild import _default_event_handlers
from .lbuild import _find_action

#: file (inside the build base) that remembers which packages failed last
LAST_FAILED_FILE = '.ltest-last-failed.json'
#: JUnit files modified this much before the run started still count
_CLOCK_SLACK_SECONDS = 1.0

_TEXT = {
    'en': {
        'description': (
            'colcon test with a live per-package board, a readable result '
            'summary (failing test cases with messages, JUnit locations), a '
            'non-zero exit code on any failure, an isolated ROS_DOMAIN_ID, and '
            'CI-friendly output. Every colcon test argument still works'
        ),
        'ci_help': (
            'CI mode: no live board; a stable per-package log (GitHub Actions '
            'groups and annotations, and a step summary when '
            '$GITHUB_STEP_SUMMARY is set). Also on automatically when stdout '
            'is not a TTY or CI/GITHUB_ACTIONS is set'
        ),
        'isolated_help': (
            'Run with a free, random ROS_DOMAIN_ID and '
            'ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST, so tests cannot see '
            'nodes of other sessions or the LAN (default: on)'
        ),
        'no_isolated_help': 'Keep the ROS_DOMAIN_ID and discovery range as set',
        'no_user_site_help': (
            'Set PYTHONNOUSERSITE=1 for the test processes (the colcon process '
            'itself is not affected), so ~/.local packages cannot shadow the '
            'workspace'
        ),
        'fail_on_skip_help': (
            'Count a skipped test case as a failure when its skip reason matches '
            'this regular expression (repeatable)'
        ),
        'retest_failed_help': (
            'Only test the packages that failed in the last ltest run (in '
            'build/.ltest-last-failed.json); combined with --packages-select'
        ),
        'no_record': 'no record of a previous failure; testing all selected packages',
        'retest_selected': 'retesting {0} previously failed package(s): {1}',
        'nothing_to_retest': 'nothing to retest: no selected package failed last time',
        'isolated_notice': 'ROS_DOMAIN_ID={0} (isolated, ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST)',
        'no_packages': 'no test results were produced',
        'title': 'Test time summary',
        'step_title': 'Test results',
    },
    'ja': {
        'description': (
            'colcon test をパッケージごとのライブ表示付きで実行し、見やすい結果要約'
            '（失敗したテストケースとメッセージ、junit の場所）を出す。失敗があれば'
            '非0で終了し、ROS_DOMAIN_ID を分離し、CI 向けの出力にもなる。colcon test '
            'の引数はすべてそのまま使える'
        ),
        'ci_help': (
            'CI モード: ライブ表示をやめ、パッケージごとの安定したログを出す'
            '（GitHub Actions ではグループと注記、$GITHUB_STEP_SUMMARY が設定されて'
            'いれば要約も書く）。標準出力が端末でない場合や CI/GITHUB_ACTIONS 環境変数'
            'が設定されている場合も自動で有効'
        ),
        'isolated_help': (
            '空いている乱数の ROS_DOMAIN_ID と ROS_AUTOMATIC_DISCOVERY_RANGE='
            'LOCALHOST で実行し、別セッションや LAN 上のノードと混線させない'
            '（既定: 有効）'
        ),
        'no_isolated_help': 'ROS_DOMAIN_ID と検出範囲を現在の環境のまま使う',
        'no_user_site_help': (
            'テストのプロセスに PYTHONNOUSERSITE=1 を渡し、~/.local のパッケージが'
            'ワークスペースを隠さないようにする（colcon 本体には影響しない）'
        ),
        'fail_on_skip_help': (
            'スキップ理由がこの正規表現に一致したテストケースを失敗扱いにする'
            '（複数指定可）'
        ),
        'retest_failed_help': (
            '前回の ltest で失敗したパッケージだけを回す（build/.ltest-last-failed.json'
            'に記録）。--packages-select と併用すると両方で絞り込む'
        ),
        'no_record': '前回の失敗の記録がないため、選択された全パッケージを回します',
        'retest_selected': '前回失敗した {0} パッケージを再試験します: {1}',
        'nothing_to_retest': '再試験するものはありません（選択されたパッケージは前回失敗していません）',
        'isolated_notice': 'ROS_DOMAIN_ID={0}（分離、ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST）',
        'no_packages': 'テスト結果は生成されませんでした',
        'title': 'テスト結果の要約',
        'step_title': 'テスト結果',
    },
    'pt': {
        'description': (
            'colcon test com painel ao vivo por pacote, resumo legível dos '
            'resultados (casos com falha e mensagens, locais dos JUnit), código '
            'de saída não zero em qualquer falha, ROS_DOMAIN_ID isolado e saída '
            'amigável para CI. Todos os argumentos do colcon test continuam válidos'
        ),
        'ci_help': (
            'Modo CI: sem painel ao vivo; um log estável por pacote (grupos e '
            'anotações do GitHub Actions, e um resumo em $GITHUB_STEP_SUMMARY '
            'quando definido). Também ativado quando a saída não é um TTY ou '
            'CI/GITHUB_ACTIONS está definido'
        ),
        'isolated_help': (
            'Executa com um ROS_DOMAIN_ID aleatório livre e '
            'ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST (padrão: ativado)'
        ),
        'no_isolated_help': 'Mantém o ROS_DOMAIN_ID e o alcance de descoberta atuais',
        'no_user_site_help': (
            'Define PYTHONNOUSERSITE=1 nos processos de teste (o próprio colcon '
            'não é afetado)'
        ),
        'fail_on_skip_help': (
            'Conta um teste pulado como falha quando o motivo casa com esta '
            'expressão regular (pode repetir)'
        ),
        'retest_failed_help': (
            'Testa apenas os pacotes que falharam na última execução do ltest '
            '(registrados em build/.ltest-last-failed.json)'
        ),
        'no_record': 'nenhum registro de falha anterior; testando todos os pacotes selecionados',
        'retest_selected': 'retestando {0} pacote(s) que falharam antes: {1}',
        'nothing_to_retest': 'nada a retestar: nenhum pacote selecionado falhou na última vez',
        'isolated_notice': 'ROS_DOMAIN_ID={0} (isolado, ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST)',
        'no_packages': 'nenhum resultado de teste foi gerado',
        'title': 'Resumo dos testes',
        'step_title': 'Resultados dos testes',
    },
}


def _text():
    return _TEXT[detect_language()]


def _regex_arg(value):
    try:
        re.compile(value)
    except re.error as exc:
        raise argparse.ArgumentTypeError(
            'invalid regular expression {0!r}: {1}'.format(value, exc))
    return value


def _last_failed_path(build_base):
    return Path(build_base) / LAST_FAILED_FILE


def read_last_failed(build_base):
    """Package names that failed in the last ltest run, or None if unknown."""
    path = _last_failed_path(build_base)
    try:
        with open(path, encoding='utf-8') as handle:
            return list(json.load(handle)['failed'])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def write_last_failed(build_base, ran, failed):
    """
    Remember the failures for the next --retest-failed.

    Packages that were run in this invocation take their new result; the
    others keep whatever was recorded before. Nothing is written if the build
    base does not exist (nothing was built or tested there).
    """
    base = Path(build_base)
    if not base.is_dir():
        return
    previous = read_last_failed(base) or []
    kept = [name for name in previous if name not in ran]
    merged = kept + [name for name in failed if name not in kept]
    with open(_last_failed_path(base), 'w', encoding='utf-8') as handle:
        json.dump({'failed': merged}, handle, indent=2)
        handle.write('\n')


class LiveTestVerb(VerbExtensionPoint):
    """Run tests with a live board and a readable, CI-friendly summary."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(VerbExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')
        # the test logic is colcon's own; this verb only wraps it
        self._test_verb = TestVerb()
        self.__doc__ = _text()['description']

    def add_arguments(self, *, parser):  # noqa: D102
        text = _text()
        self._test_verb.add_arguments(parser=parser)

        handlers = _default_event_handlers(live_handler='live_test_status')
        handlers.append('ltest_recorder+')
        parser.set_defaults(event_handlers=handlers, isolated_domain=True)
        event_handlers_action = _find_action(parser, 'event_handlers')
        if event_handlers_action is not None:
            event_handlers_action.help = (
                'Enable (+) or disable (-) event handlers (default for '
                "'colcon ltest'/'colcon lt': {0})".format(' '.join(handlers)))

        parser.add_argument('--ci', action='store_true', help=text['ci_help'])
        parser.add_argument(
            '--isolated-domain', dest='isolated_domain', action='store_true',
            help=text['isolated_help'])
        parser.add_argument(
            '--no-isolated-domain', dest='isolated_domain', action='store_false',
            help=text['no_isolated_help'])
        parser.add_argument(
            '--no-user-site', action='store_true', help=text['no_user_site_help'])
        parser.add_argument(
            '--fail-on-skip', dest='fail_on_skip', action='append',
            metavar='PATTERN', type=_regex_arg, default=None,
            help=text['fail_on_skip_help'])
        parser.add_argument(
            '--retest-failed', action='store_true', help=text['retest_failed_help'])

    def main(self, *, context):  # noqa: D102
        args = context.args
        text = _text()
        started = time.time()

        # a test run that produced failures must say so in its exit code
        args.return_code_on_test_failure = True
        ci_on = _ci.apply_output_mode(
            args, live='live_test_status', ci_handler='ci_test_status')
        registered = _ci.registered_handler_names()
        if ('ltest_recorder+' not in args.event_handlers
                and (registered is None or 'ltest_recorder' in registered)):
            args.event_handlers = list(args.event_handlers) + ['ltest_recorder+']

        build_base = Path(args.build_base)
        test_result_base = Path(args.test_result_base or args.build_base)

        previous_failed = None
        if args.retest_failed:
            previous_failed = read_last_failed(build_base)
            if previous_failed is None:
                print(text['no_record'])
            else:
                selected = previous_failed
                if args.packages_select:
                    selected = [p for p in args.packages_select if p in previous_failed]
                if not selected:
                    print(text['nothing_to_retest'])
                    return 0
                print(text['retest_selected'].format(len(selected), ' '.join(selected)))
                args.packages_select = selected

        env = {}
        if args.isolated_domain:
            domain_id = _ci.pick_free_domain_id()
            env = _ci.isolated_test_env(domain_id)
            print(text['isolated_notice'].format(domain_id))
        if args.no_user_site:
            env['PYTHONNOUSERSITE'] = '1'

        run_recorder.reset()
        with _ci.scoped_environ(env):
            rc = self._test_verb.main(context=context)
        wall_time = time.time() - started

        records = run_recorder.snapshot()
        summaries = {
            name: summarize_package(
                name, test_result_base / name,
                since=started - _CLOCK_SLACK_SECONDS,
                fail_on_skip=args.fail_on_skip or ())
            for name in records}
        rows = build_rows(summaries, records)
        failed = [row.name for row in rows if row.failed]

        if not rows:
            print(text['no_packages'])
        else:
            paint = _Paint(
                sys.stdout.isatty() and not ci_on
                and os.environ.get('NO_COLOR') is None)
            context_text = ', '.join(
                '{0}={1}'.format(k, v) for k, v in sorted(env.items()))
            for line in render_text(
                    rows, title=text['title'], wall_time=wall_time,
                    context=context_text, paint=paint):
                print(line)

        if ci_on and _ci.is_github_actions():
            for line in render_annotations(rows):
                print(line)
        if rows:
            _ci.append_step_summary(render_markdown(
                rows, title=text['step_title'], wall_time=wall_time))

        if args.retest_failed or rows:
            write_last_failed(build_base, set(records), failed)

        if rc:
            return rc
        return 1 if failed else 0


class LiveTestVerbShort(LiveTestVerb):
    """Alias for `colcon ltest` -- identical behavior, shorter to type.

    A separate subclass for the same reason `LiveBuildVerbShort` is: two
    entry points resolving to the same class would share one cached
    instance in colcon-core's plugin system.
    """
