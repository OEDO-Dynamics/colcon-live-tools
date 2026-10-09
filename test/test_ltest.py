# Copyright 2026 OEDO Dynamics Inc.
# Licensed under the Apache License, Version 2.0

"""The ltest verb around a fake colcon TestVerb.main (no ROS needed)."""

import argparse
import json
import os
import types

import pytest

from colcon_core.event.job import JobEnded
from colcon_core.event.job import JobStarted
from colcon_core.event.test import TestFailure as _TestFailure

from colcon_live_tools import _ci
from colcon_live_tools.event_handler import run_recorder
from colcon_live_tools.event_handler.run_recorder import RunRecorderEventHandler
from colcon_live_tools.verb import ltest

PASSING = """<?xml version="1.0"?>
<testsuites><testsuite name="s" tests="1">
  <testcase classname="C" name="ok"/>
</testsuite></testsuites>
"""

FAILING = """<?xml version="1.0"?>
<testsuites><testsuite name="s" tests="2">
  <testcase classname="C" name="ok"/>
  <testcase classname="C" name="bad" file="test/c.cpp" line="7">
    <failure message="expected 1 got 2">details</failure>
  </testcase>
</testsuite></testsuites>
"""

SKIPPING = """<?xml version="1.0"?>
<testsuites><testsuite name="s" tests="1">
  <testcase classname="C" name="hw"><skipped message="needs hardware"/></testcase>
</testsuite></testsuites>
"""

ENV_KEYS = ('ROS_DOMAIN_ID', 'ROS_AUTOMATIC_DISCOVERY_RANGE', 'PYTHONNOUSERSITE')


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ENV_KEYS + ('CI', 'GITHUB_ACTIONS', 'GITHUB_STEP_SUMMARY'):
        monkeypatch.delenv(key, raising=False)
    # the handler entry points are not installed in the test environment;
    # "unknown" lets CI mode proceed. The registered-or-fallback rule itself
    # is covered in test_ci.py
    monkeypatch.setattr(_ci, 'registered_handler_names', lambda: None)
    run_recorder.reset()
    yield
    run_recorder.reset()


def _verb(argv, build_base):
    verb = ltest.LiveTestVerb()
    parser = argparse.ArgumentParser(prog='colcon ltest')
    verb.add_arguments(parser=parser)
    # --packages-select comes from colcon's package-selection extension; add
    # it only when that extension is not installed (it would conflict)
    try:
        parser.add_argument('--packages-select', nargs='*', default=None)
    except argparse.ArgumentError:
        pass
    args = parser.parse_args(['--build-base', str(build_base)] + argv)
    return verb, types.SimpleNamespace(args=args, command_name='colcon')


def _fake_tests(calls, results, *, rc=0):
    """
    A stand-in for TestVerb.main.

    `results` is a list of (package, junit text or None, job rc, test failure).
    It records the environment and selection it was called with, writes the
    JUnit files where colcon would, and reports the jobs through the recorder.
    """
    def main(*, context):
        calls.append({
            'env': {k: os.environ.get(k) for k in ENV_KEYS},
            'packages_select': context.args.packages_select,
        })
        recorder = RunRecorderEventHandler()
        for name, junit, job_rc, failed in results:
            job = object()
            recorder((JobStarted(name), job))
            if junit is not None:
                directory = os.path.join(context.args.build_base, name)
                os.makedirs(directory, exist_ok=True)
                with open(os.path.join(directory, name + '.xml'), 'w',
                          encoding='utf-8') as handle:
                    handle.write(junit)
            if failed:
                recorder((_TestFailure(name),))
            recorder((JobEnded(name, job_rc), job))
        return rc
    return main


def test_defaults_isolate_the_domain_and_fail_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(_ci, 'pick_free_domain_id', lambda **kw: 42)
    verb, context = _verb([], tmp_path / 'build')
    calls = []
    verb._test_verb.main = _fake_tests(calls, [('pkg_a', PASSING, 0, False)])

    assert context.args.isolated_domain is True
    assert context.args.return_code_on_test_failure is False  # set in main()
    rc = verb.main(context=context)

    assert rc == 0
    assert calls[0]['env'] == {
        'ROS_DOMAIN_ID': '42',
        'ROS_AUTOMATIC_DISCOVERY_RANGE': 'LOCALHOST',
        'PYTHONNOUSERSITE': None}
    # the environment is restored after the run
    assert all(os.environ.get(k) is None for k in ENV_KEYS)
    assert context.args.return_code_on_test_failure is True


def test_no_isolated_domain_and_no_user_site(tmp_path, monkeypatch):
    def not_called():
        raise AssertionError('no domain should be picked')
    monkeypatch.setattr(_ci, 'pick_free_domain_id', not_called)
    monkeypatch.setenv('ROS_DOMAIN_ID', '5')
    verb, context = _verb(
        ['--no-isolated-domain', '--no-user-site'], tmp_path / 'build')
    calls = []
    verb._test_verb.main = _fake_tests(calls, [('pkg_a', PASSING, 0, False)])
    verb.main(context=context)
    assert calls[0]['env'] == {
        'ROS_DOMAIN_ID': '5', 'ROS_AUTOMATIC_DISCOVERY_RANGE': None,
        'PYTHONNOUSERSITE': '1'}
    assert os.environ['ROS_DOMAIN_ID'] == '5'
    assert 'PYTHONNOUSERSITE' not in os.environ


def test_failing_testcase_gives_nonzero_and_a_readable_summary(
        tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(_ci, 'pick_free_domain_id', lambda **kw: 3)
    verb, context = _verb([], tmp_path / 'build')
    calls = []
    # colcon itself reports 0 here: the JUnit failure must still fail the run
    verb._test_verb.main = _fake_tests(calls, [('pkg_a', FAILING, 0, False)])
    rc = verb.main(context=context)
    out = capsys.readouterr().out

    assert rc == 1
    assert 'pkg_a' in out and 'FAIL' in out
    assert 'FAILED  C.bad' in out
    assert 'expected 1 got 2' in out
    assert 'at test/c.cpp:7' in out
    assert 'JUnit results' in out
    assert '1 package(s) failed: pkg_a' in out


def test_nonzero_colcon_rc_is_passed_through(tmp_path, monkeypatch):
    monkeypatch.setattr(_ci, 'pick_free_domain_id', lambda **kw: 3)
    verb, context = _verb([], tmp_path / 'build')
    verb._test_verb.main = _fake_tests([], [('pkg_a', None, 2, False)], rc=2)
    assert verb.main(context=context) == 2


def test_fail_on_skip_turns_a_matching_skip_into_a_failure(
        tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(_ci, 'pick_free_domain_id', lambda **kw: 3)
    verb, context = _verb(['--fail-on-skip', 'hardware'], tmp_path / 'build')
    verb._test_verb.main = _fake_tests([], [('pkg_a', SKIPPING, 0, False)])
    assert verb.main(context=context) == 1
    out = capsys.readouterr().out
    assert 'SKIP-FAILED' in out and 'matched /hardware/' in out


def test_fail_on_skip_pattern_must_be_a_valid_regex(tmp_path):
    verb = ltest.LiveTestVerb()
    parser = argparse.ArgumentParser()
    verb.add_arguments(parser=parser)
    with pytest.raises(SystemExit):
        parser.parse_args(['--fail-on-skip', '('])


def test_ci_mode_prints_annotations_and_writes_the_step_summary(
        tmp_path, capsys, monkeypatch):
    summary = tmp_path / 'summary.md'
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setenv('GITHUB_STEP_SUMMARY', str(summary))
    monkeypatch.setattr(_ci, 'pick_free_domain_id', lambda **kw: 3)
    verb, context = _verb([], tmp_path / 'build')
    verb._test_verb.main = _fake_tests([], [('pkg_a', FAILING, 0, False)])
    verb.main(context=context)
    out = capsys.readouterr().out

    assert '::error file=test/c.cpp,line=7,title=pkg_a::C.bad: expected 1 got 2' in out
    text = summary.read_text(encoding='utf-8')
    assert '### Test results' in text
    assert '| pkg_a | FAIL | 2 | 1 | 0 | 0 |' in text
    assert '#### Failed test cases' in text


def test_no_workflow_commands_outside_github_actions(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(_ci, 'pick_free_domain_id', lambda **kw: 3)
    verb, context = _verb([], tmp_path / 'build')
    verb._test_verb.main = _fake_tests([], [('pkg_a', FAILING, 0, False)])
    verb.main(context=context)
    assert '::' not in capsys.readouterr().out


def test_retest_failed_runs_only_the_recorded_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(_ci, 'pick_free_domain_id', lambda **kw: 3)
    build = tmp_path / 'build'
    build.mkdir()
    (build / ltest.LAST_FAILED_FILE).write_text(
        json.dumps({'failed': ['pkg_a', 'pkg_b']}), encoding='utf-8')
    verb, context = _verb(['--retest-failed'], build)
    calls = []
    verb._test_verb.main = _fake_tests(calls, [('pkg_a', PASSING, 0, False)])
    assert verb.main(context=context) == 0

    assert calls[0]['packages_select'] == ['pkg_a', 'pkg_b']
    # pkg_a passed now, pkg_b was not run and stays on the list
    assert ltest.read_last_failed(build) == ['pkg_b']


def test_retest_failed_intersects_with_packages_select(tmp_path, monkeypatch):
    monkeypatch.setattr(_ci, 'pick_free_domain_id', lambda **kw: 3)
    build = tmp_path / 'build'
    build.mkdir()
    (build / ltest.LAST_FAILED_FILE).write_text(
        json.dumps({'failed': ['pkg_a']}), encoding='utf-8')
    verb, context = _verb(
        ['--retest-failed', '--packages-select', 'pkg_b'], build)
    calls = []
    verb._test_verb.main = _fake_tests(calls, [])
    assert verb.main(context=context) == 0
    assert calls == []  # nothing selected was failing: nothing ran


def test_retest_failed_without_a_record_runs_everything(
        tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(_ci, 'pick_free_domain_id', lambda **kw: 3)
    verb, context = _verb(['--retest-failed'], tmp_path / 'build')
    calls = []
    verb._test_verb.main = _fake_tests(calls, [('pkg_a', PASSING, 0, False)])
    verb.main(context=context)
    assert calls[0]['packages_select'] is None
    assert 'no record' in capsys.readouterr().out


def test_last_failed_keeps_packages_that_were_not_run(tmp_path):
    build = tmp_path / 'build'
    build.mkdir()
    ltest.write_last_failed(build, {'a'}, ['a'])
    ltest.write_last_failed(build, {'b'}, ['b'])
    assert ltest.read_last_failed(build) == ['a', 'b']
    ltest.write_last_failed(build, {'a'}, [])
    assert ltest.read_last_failed(build) == ['b']


def test_verb_registers_both_names_and_defaults():
    verb = ltest.LiveTestVerb()
    parser = argparse.ArgumentParser()
    verb.add_arguments(parser=parser)
    args = parser.parse_args([])
    assert 'live_tools_test_recorder+' in args.event_handlers
    assert args.isolated_domain is True
    assert ltest.LiveTestVerbShort.__mro__[1] is ltest.LiveTestVerb


def test_zero_test_cases_fail_only_in_ci_mode(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(_ci, 'pick_free_domain_id', lambda **kw: 3)
    # a package with no JUnit results and exit code 0: zero test cases run
    verb, context = _verb(['--packages-select', 'pkg_a'], tmp_path / 'build')
    verb._test_verb.main = _fake_tests([], [('pkg_a', None, 0, False)])
    assert verb.main(context=context) == 0  # terminal: a warning only
    assert 'no test case was run' in capsys.readouterr().out

    monkeypatch.setenv('CI', '1')
    verb, context = _verb(['--packages-select', 'pkg_a'], tmp_path / 'build')
    verb._test_verb.main = _fake_tests([], [('pkg_a', None, 0, False)])
    assert verb.main(context=context) == 1  # CI: the empty run is an error


def test_allow_no_tests_lets_an_empty_ci_run_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(_ci, 'pick_free_domain_id', lambda **kw: 3)
    monkeypatch.setenv('CI', '1')
    verb, context = _verb(['--allow-no-tests'], tmp_path / 'build')
    verb._test_verb.main = _fake_tests([], [('pkg_a', None, 0, False)])
    assert verb.main(context=context) == 0


def test_selected_package_without_results_is_reported(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(_ci, 'pick_free_domain_id', lambda **kw: 3)
    verb, context = _verb(['--packages-select', 'typo_pkg'], tmp_path / 'build')
    verb._test_verb.main = _fake_tests([], [('pkg_a', PASSING, 0, False)])
    verb.main(context=context)
    out = capsys.readouterr().out
    assert 'produced no test results: typo_pkg' in out


def test_isolated_domain_excludes_the_current_domain(tmp_path, monkeypatch):
    monkeypatch.setenv('ROS_DOMAIN_ID', '7')
    seen = {}

    def fake_pick(exclude=()):
        seen['exclude'] = tuple(exclude)
        return 9
    monkeypatch.setattr(_ci, 'pick_free_domain_id', fake_pick)
    verb, context = _verb([], tmp_path / 'build')
    verb._test_verb.main = _fake_tests([], [('pkg_a', PASSING, 0, False)])
    verb.main(context=context)
    assert seen['exclude'] == (7,)
