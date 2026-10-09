# Copyright 2026 OEDO Dynamics Inc.
# Licensed under the Apache License, Version 2.0

"""CI-mode detection, workflow commands, step summary, isolated domains."""

import argparse
import os
import random

import pytest

from colcon_live_tools import _ci


def test_ci_mode_from_flags_and_environment_only():
    assert _ci.is_ci_mode(environ={}) is False
    assert _ci.is_ci_mode(environ={}, forced=True) is True
    assert _ci.is_ci_mode(environ={'CI': 'true'}) is True
    assert _ci.is_ci_mode(environ={'GITHUB_ACTIONS': 'true'}) is True
    # explicit "off" values do not turn CI mode on
    assert _ci.is_ci_mode(environ={'CI': '0'}) is False
    assert _ci.is_ci_mode(environ={'CI': 'false'}) is False
    assert _ci.is_github_actions({'GITHUB_ACTIONS': 'true'}) is True
    assert _ci.is_github_actions({}) is False


def test_apply_output_mode_swaps_live_board_for_ci_log():
    args = argparse.Namespace(
        ci=False, event_handlers=['status-', 'live_status+'])
    # no flag and no CI variables: the live board, as in 0.1.1
    assert _ci.apply_output_mode(
        args, live='live_status', ci_handler='live_tools_ci_status',
        environ={}, registered={'live_status', 'live_tools_ci_status'}) is False
    assert args.event_handlers == ['status-', 'live_status+']
    # --ci, or CI / GITHUB_ACTIONS set, switches to the CI log
    args.ci = True
    assert _ci.apply_output_mode(
        args, live='live_status', ci_handler='live_tools_ci_status',
        environ={}, registered={'live_status', 'live_tools_ci_status'}) is True
    assert args.event_handlers == ['status-', 'live_tools_ci_status+']


def test_piped_run_keeps_the_live_board_handlers(tmp_path):
    """A non-TTY stdout alone must not change the handlers (0.1.1 behavior)."""
    args = argparse.Namespace(
        ci=False, event_handlers=['status-', 'summary-', 'live_status+'])
    before = list(args.event_handlers)
    assert _ci.apply_output_mode(
        args, live='live_status', ci_handler='live_tools_ci_status',
        environ={}, registered={'live_status', 'live_tools_ci_status'}) is False
    assert args.event_handlers == before


def test_workflow_command_escapes_data_and_properties():
    line = _ci.annotation(
        'error', '50% done\nsecond line', file='src/a:b,c.cpp', line=12,
        title='pkg')
    assert line == (
        '::error file=src/a%3Ab%2Cc.cpp,line=12,title=pkg::'
        '50%25 done%0Asecond line')
    assert _ci.annotation('error', 'no location') == '::error::no location'
    assert _ci.group('pkg: OK') == '::group::pkg: OK'
    assert _ci.endgroup() == '::endgroup::'


def test_annotation_path_is_relative_to_workspace():
    env = {'GITHUB_WORKSPACE': '/home/runner/work/repo'}
    assert _ci.annotation_path(
        '/home/runner/work/repo/src/x.cpp', env) == 'src/x.cpp'
    assert _ci.annotation_path('/elsewhere/x.cpp', env) == '/elsewhere/x.cpp'
    assert _ci.annotation_path('x.cpp', env) == 'x.cpp'


def test_step_summary_is_appended_only_when_set(tmp_path):
    summary = tmp_path / 'summary.md'
    assert _ci.append_step_summary('# nothing', environ={}) is False
    assert not summary.exists()
    env = {'GITHUB_STEP_SUMMARY': str(summary)}
    assert _ci.append_step_summary('### one', environ=env) is True
    assert _ci.append_step_summary('### two', environ=env) is True
    assert summary.read_text(encoding='utf-8') == '### one\n\n### two\n\n'


def test_md_table_escapes_pipes_and_newlines():
    table = _ci.md_table(['A', 'B'], [('x|y', 'line1\nline2')])
    assert table.splitlines() == [
        '| A | B |', '|---|---|', '| x\\|y | line1 line2 |']


def test_pick_free_domain_id_uses_only_free_domains():
    busy = {3, 4, 5}
    domain = _ci.pick_free_domain_id(
        rng=random.Random(1), is_free=lambda d: d not in busy)
    assert 0 <= domain <= _ci.ROS_DOMAIN_ID_MAX
    assert domain not in busy


def test_pick_free_domain_id_raises_when_none_is_free():
    with pytest.raises(RuntimeError):
        _ci.pick_free_domain_id(
            rng=random.Random(1), is_free=lambda d: False)


def test_domain_ports_follow_the_rtps_formula():
    # PB=7400, DG=250, participant 0 offsets d0,d1,d2,d3 = 0,1,10,11
    assert _ci.domain_ports(0) == [7400, 7401, 7410, 7411]
    assert _ci.domain_ports(2) == [7900, 7901, 7910, 7911]


def test_isolated_test_env_pins_domain_and_loopback():
    assert _ci.isolated_test_env(42) == {
        'ROS_DOMAIN_ID': '42', 'ROS_AUTOMATIC_DISCOVERY_RANGE': 'LOCALHOST'}


def test_scoped_environ_restores_previous_values(monkeypatch):
    monkeypatch.setenv('ROS_DOMAIN_ID', '7')
    monkeypatch.delenv('PYTHONNOUSERSITE', raising=False)
    with _ci.scoped_environ({'ROS_DOMAIN_ID': '99', 'PYTHONNOUSERSITE': '1'}):
        assert os.environ['ROS_DOMAIN_ID'] == '99'
        assert os.environ['PYTHONNOUSERSITE'] == '1'
    assert os.environ['ROS_DOMAIN_ID'] == '7'
    assert 'PYTHONNOUSERSITE' not in os.environ


def test_apply_output_mode_keeps_live_board_when_ci_handler_is_missing():
    args = argparse.Namespace(
        ci=True, event_handlers=['status-', 'live_status+'])
    # e.g. another installation shadows this package's entry points
    assert _ci.apply_output_mode(
        args, live='live_status', ci_handler='live_tools_ci_status',
        environ={}, registered={'live_status'}) is False
    assert args.event_handlers == ['status-', 'live_status+']


def test_pick_free_domain_id_stays_in_1_to_101_and_skips_excluded():
    seen = set()
    for seed in range(50):
        domain = _ci.pick_free_domain_id(
            rng=random.Random(seed), is_free=lambda d: True, exclude=(5,))
        seen.add(domain)
    assert seen <= set(range(1, 102)) - {5}
    assert len(seen) > 10  # actually random, not a fixed value
    # the highest DDS port of domain 101 stays below the ephemeral range
    assert max(_ci.domain_ports(101)) < 32768
