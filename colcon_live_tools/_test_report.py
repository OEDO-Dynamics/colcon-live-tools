# Copyright 2026 OEDO Dynamics Inc.
# Licensed under the Apache License, Version 2.0

"""
Turn per-package test summaries into the human-readable report `ltest` prints,
the Markdown table for ``$GITHUB_STEP_SUMMARY``, and GitHub annotations.

Pure functions: no colcon, no terminal state. Colour is applied by the caller
through the `paint` argument (see `colcon_live_tools.event_handler.live_status`).
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional

from . import _ci
from ._junit import SKIP_FAILED

PASS = 'PASS'
FAIL = 'FAIL'
SKIP = 'SKIP'
NO_JUNIT = 'NO JUNIT'

#: how many lines of a failure message are shown
MESSAGE_HEAD_LINES = 5
_MESSAGE_LINE_WIDTH = 200


@dataclass
class PackageRow:
    """One package's line in the report."""

    name: str
    status: str
    tests: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    duration: float = 0.0
    files: List[str] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)
    failed_cases: list = field(default_factory=list)
    exit_code: Optional[int] = None

    @property
    def failed(self):
        return self.status == FAIL


def build_rows(summaries, records):
    """
    Combine the JUnit summaries with the job records into report rows.

    `summaries` maps package name to `PackageSummary`; `records` maps package
    name to the dict kept by `run_recorder`. Rows follow `records` order.
    """
    rows = []
    for name, record in records.items():
        summary = summaries.get(name)
        row = PackageRow(name=name, status=PASS,
                         duration=record.get('duration', 0.0),
                         exit_code=record.get('rc'))
        if summary is not None:
            row.tests = summary.tests
            row.failures = summary.failures
            row.errors = summary.errors
            row.skipped = summary.skipped
            row.files = list(summary.files)
            row.problems = list(summary.problems)
            row.failed_cases = list(summary.failed_cases)

        if record.get('skipped'):
            row.status = SKIP
        elif (record.get('rc') != 0 or record.get('test_failure')
              or row.failures or row.errors or row.problems):
            row.status = FAIL
        elif not row.files:
            row.status = NO_JUNIT
        rows.append(row)
    return rows


def _seconds(value):
    return '{0:.1f}s'.format(value)


def _message_head(message):
    lines = [line.rstrip() for line in (message or '').splitlines() if line.strip()]
    head = [line[:_MESSAGE_LINE_WIDTH] for line in lines[:MESSAGE_HEAD_LINES]]
    if len(lines) > MESSAGE_HEAD_LINES:
        head.append('... ({0} more lines)'.format(len(lines) - MESSAGE_HEAD_LINES))
    return head


def _case_location(case):
    if case.file and case.line:
        return '{0}:{1}'.format(case.file, case.line)
    return case.file or ''


def render_text(rows, *, title, wall_time, context='', paint=None):
    """
    The terminal report: a per-package table, then the failing test cases.

    `paint` is an object with ``bold``, ``red``, ``bold_red``, ``bold_green``,
    ``dim``, ``yellow`` methods; None means plain text.
    """
    def style(method, text):
        return getattr(paint, method)(text) if paint is not None else text

    lines = []
    header = '{0}  (wall time {1}{2})'.format(
        title, _seconds(wall_time), ', ' + context if context else '')
    lines.append(style('bold', header))
    name_width = max([len(r.name) for r in rows] + [len('Package')])
    lines.append('  {0:<{w}} {1:>6} {2:>9} {3:>7} {4:>8}  {5}'.format(
        'Package', 'Tests', 'Failures', 'Errors', 'Skipped', 'Result', w=name_width))
    for row in rows:
        colour = 'bold_red' if row.failed else (
            'dim' if row.status in (SKIP, NO_JUNIT) else 'bold_green')
        result = style(colour, row.status)
        lines.append('  {0:<{w}} {1:>6} {2:>9} {3:>7} {4:>8}  {5}'.format(
            row.name, row.tests, row.failures, row.errors, row.skipped,
            result, w=name_width).rstrip())
    total = [sum(getattr(r, attr) for r in rows)
             for attr in ('tests', 'failures', 'errors', 'skipped')]
    lines.append('  {0:<{w}} {1:>6} {2:>9} {3:>7} {4:>8}'.format(
        'total', *total, w=name_width))

    failed = [r for r in rows if r.failed]
    lines.append('')
    if failed:
        lines.append(style('bold_red', '{0} package(s) failed: {1}'.format(
            len(failed), ', '.join(r.name for r in failed))))
    else:
        lines.append(style('bold_green', 'all packages passed'))

    for row in failed:
        lines.append('')
        lines.append(style('bold_red', '----- {0}: failures -----'.format(row.name)))
        for problem in row.problems:
            lines.append('  could not read JUnit: ' + problem)
        if not row.failed_cases and row.exit_code not in (0, None):
            lines.append('  test job exited with code {0} and no failed test case '
                         'was reported (see the output above)'.format(row.exit_code))
        for case in row.failed_cases:
            tag = 'SKIP-FAILED' if case.status == SKIP_FAILED else case.status.upper()
            lines.append('  {0}  {1}'.format(style('red', tag), case.full_name))
            if case.status == SKIP_FAILED:
                lines.append('      skip reason matched /{0}/'.format(case.matched_skip))
            for head in _message_head(case.message):
                lines.append('      ' + head)
            location = _case_location(case)
            if location:
                lines.append('      at ' + location)
            lines.append('      junit: ' + case.junit)

    if any(r.files for r in rows):
        lines.append('')
        lines.append(style('bold', 'JUnit results:'))
        for row in rows:
            if row.files:
                lines.append('  {0}: {1} file(s) in {2}'.format(
                    row.name, len(row.files), _dirs_of(row.files)))
                if row.failed:
                    for path in row.files:
                        lines.append('      ' + path)
    return lines


def _dirs_of(paths):
    dirs = sorted({os.path.dirname(p) for p in paths})
    return dirs[0] if len(dirs) == 1 else '{0} directories'.format(len(dirs))


def render_markdown(rows, *, title, wall_time):
    """The ``$GITHUB_STEP_SUMMARY`` section for a test run."""
    parts = ['### {0}'.format(title),
             'Wall time: {0}'.format(_seconds(wall_time)),
             _ci.md_table(
                 ['Package', 'Result', 'Tests', 'Failures', 'Errors', 'Skipped',
                  'Time'],
                 [(r.name, r.status, r.tests, r.failures, r.errors, r.skipped,
                   _seconds(r.duration)) for r in rows])]
    failed_rows = [
        (r.name, case.status, case.full_name,
         (_message_head(case.message) or [''])[0],
         _case_location(case))
        for r in rows for case in r.failed_cases]
    if failed_rows:
        parts.append('#### Failed test cases')
        parts.append(_ci.md_table(
            ['Package', 'Status', 'Test case', 'Message', 'Location'],
            failed_rows))
    return '\n\n'.join(parts)


def render_annotations(rows, *, environ=None):
    """GitHub ``::error`` annotations for failed packages and test cases."""
    lines = []
    for row in rows:
        if not row.failed:
            continue
        for problem in row.problems:
            lines.append(_ci.annotation(
                'error', '{0}: could not read JUnit: {1}'.format(row.name, problem),
                title=row.name))
        for case in row.failed_cases:
            heads = _message_head(case.message)
            message = '{0}: {1}'.format(
                case.full_name or row.name, heads[0] if heads else case.status)
            lines.append(_ci.annotation(
                'error', message,
                file=_ci.annotation_path(case.file, environ) if case.file else None,
                line=case.line, title=row.name))
        if not row.failed_cases and not row.problems:
            lines.append(_ci.annotation(
                'error', '{0} failed (exit code {1})'.format(
                    row.name, row.exit_code), title=row.name))
    return lines
