# Copyright 2026 OEDO Dynamics Inc.
# Licensed under the Apache License, Version 2.0

"""The CI log handler: per-package blocks, GitHub groups, annotations, summary."""

from colcon_core.event.job import JobEnded
from colcon_core.event.job import JobSkipped
from colcon_core.event.job import JobStarted
from colcon_core.event.output import StderrLine
from colcon_core.event.output import StdoutLine
from colcon_core.event_reactor import EventReactorShutdown

from colcon_live_tools.event_handler.ci_status import CiStatusEventHandler
from colcon_live_tools.event_handler.ci_status import CiTestStatusEventHandler
from colcon_live_tools.event_handler.run_recorder import RunRecorderEventHandler
from colcon_live_tools.event_handler import run_recorder


def _drive(handler, tmp_path):
    job_a, job_b, job_c = object(), object(), object()
    handler((JobStarted('pkg_a'), job_a))
    handler((JobStarted('pkg_b'), job_b))
    handler((StdoutLine(b'compiling a\n'), job_a))
    handler((StdoutLine(b'still a\n'), job_a))
    diag = (str(tmp_path / 'src' / 'x.cpp') + ':12:5: error: boom').encode()
    handler((StderrLine(b'\x1b[31m' + diag + b'\x1b[0m\n'), job_b))
    handler((JobSkipped('pkg_c'), job_c))
    handler((JobEnded('pkg_a', 0), job_a))
    handler((JobEnded('pkg_b', 2), job_b))
    handler((EventReactorShutdown(),))


def test_github_mode_groups_each_package_and_annotates_failures(
        monkeypatch, tmp_path, capsys):
    summary = tmp_path / 'summary.md'
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setenv('GITHUB_WORKSPACE', str(tmp_path))
    monkeypatch.setenv('GITHUB_STEP_SUMMARY', str(summary))

    _drive(CiStatusEventHandler(), tmp_path)
    lines = capsys.readouterr().out.splitlines()

    group_a = [i for i, l in enumerate(lines)
               if l.startswith('::group::pkg_a: OK')][0]
    end_a = lines.index('::endgroup::', group_a)
    block_a = lines[group_a + 1:end_a]
    # pkg_a's lines are contiguous: no pkg_b output interleaved
    assert block_a == ['compiling a', 'still a']
    assert lines[end_a + 1].startswith('Finished <<< pkg_a [')

    assert any(l.startswith('::group::pkg_b: FAILED') for l in lines)
    annotation = [l for l in lines if l.startswith('::error')]
    assert annotation == [
        '::error file=src/x.cpp,line=12,title=pkg_b::pkg_b: boom']
    assert 'Skipped <<< pkg_c' in lines

    text = summary.read_text(encoding='utf-8')
    assert '### Build time summary' in text
    assert '| pkg_a | OK |' in text and '| pkg_b | FAILED |' in text
    assert '| pkg_c | SKIPPED |' in text


def test_plain_mode_has_no_workflow_commands(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    monkeypatch.delenv('GITHUB_STEP_SUMMARY', raising=False)
    _drive(CiStatusEventHandler(), tmp_path)
    out = capsys.readouterr().out
    assert '::' not in out
    assert '===== pkg_a: OK' in out and '===== pkg_a output end =====' in out
    assert 'Starting >>> pkg_a' in out
    assert 'Failed <<< pkg_b' in out
    assert 'Build time summary' in out


def test_ltest_handler_leaves_the_table_to_the_verb(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    monkeypatch.delenv('GITHUB_STEP_SUMMARY', raising=False)
    _drive(CiTestStatusEventHandler(), tmp_path)
    out = capsys.readouterr().out
    assert 'Finished <<< pkg_a' in out
    assert 'Test time summary' not in out


def test_run_recorder_records_rc_skip_and_test_failure():
    run_recorder.reset()
    recorder = RunRecorderEventHandler()
    job = object()
    recorder((JobStarted('pkg_a'), job))
    recorder((JobEnded('pkg_a', 1), job))
    recorder((JobSkipped('pkg_b'),))
    from colcon_core.event.test import TestFailure
    recorder((TestFailure('pkg_a'),))
    snap = run_recorder.snapshot()
    assert snap['pkg_a']['rc'] == 1 and snap['pkg_a']['test_failure'] is True
    assert snap['pkg_b']['skipped'] is True and snap['pkg_b']['rc'] is None
    run_recorder.reset()
    assert run_recorder.snapshot() == {}
