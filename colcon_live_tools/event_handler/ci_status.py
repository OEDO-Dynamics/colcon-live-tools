# Copyright 2026 OEDO Dynamics Inc.
# Licensed under the Apache License, Version 2.0

"""
Stable, non-interactive build/test log for CI (`lbuild`/`ltest` in CI mode).

Nothing is redrawn with cursor movement, so the output reads the same in a
pipe, a file or a CI log:

- one ``Starting >>> <pkg>`` line when a job starts,
- when a job ends, its whole output is printed as one block (not interleaved
  with other packages), followed by ``Finished <<< <pkg> [time]`` or
  ``Failed <<< ...``,
- on GitHub Actions the block is a ``::group::`` (collapsed in the UI) and a
  failed package gets an ``::error`` annotation (with file and line when a
  compiler diagnostic was seen),
- at the end, a plain summary table, also appended to ``$GITHUB_STEP_SUMMARY``
  when that is set.

Output is buffered per job so parallel packages never mix. This handler is
disabled by default; `apply_output_mode` in `_ci` enables it in CI mode.
"""

from collections import OrderedDict
import re
import time

from colcon_core.event.job import JobEnded
from colcon_core.event.job import JobSkipped
from colcon_core.event.job import JobStarted
from colcon_core.event.output import StderrLine
from colcon_core.event.output import StdoutLine
from colcon_core.event_handler import EventHandlerExtensionPoint
from colcon_core.event_handler import format_duration
from colcon_core.event_reactor import EventReactorShutdown
from colcon_core.plugin_system import satisfies_version
from colcon_core.subprocess import SIGINT_RESULT

from .. import _ci
from .live_status import _classify_line
from .live_status import _strip_ansi

# 'file.cpp:12:5: error: message' / 'file.py:3: error: message'
_DIAG_LOCATION_RE = re.compile(
    r'^(?P<file>[^\s:][^:]*?):(?P<line>\d+)(?::\d+)?:\s*'
    r'(?:fatal\s+)?error:\s*(?P<msg>.*)$')


class _CiJob:
    """Buffered output and outcome of one job."""

    __slots__ = (
        'identifier', 'start', 'end', 'rc', 'lines', 'warnings', 'errors',
        'first_error')

    def __init__(self, identifier):  # noqa: D107
        self.identifier = identifier
        self.start = None
        self.end = None
        self.rc = None
        self.lines = []
        self.warnings = 0
        self.errors = 0
        self.first_error = None

    def duration(self):
        if self.start is None:
            return 0.0
        end = self.end if self.end is not None else time.monotonic()
        return max(0.0, end - self.start)


class CiStatusEventHandler(EventHandlerExtensionPoint):
    """Stable per-package log for CI, with GitHub Actions groups and annotations."""

    PRIORITY = 50
    #: heading of the final table; subclasses for other verbs override it
    SUMMARY_TITLE = 'Build time summary'
    #: whether to print the table at the end (ltest prints its own summary)
    PRINT_SUMMARY = True

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            EventHandlerExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')
        self.enabled = False
        self._github = _ci.is_github_actions()
        self._start = time.monotonic()
        self._jobs = OrderedDict()  # job -> _CiJob
        self._finished = []

    # ------------------------------------------------------------------

    @staticmethod
    def _say(line):
        print(line, flush=True)

    def _state(self, job, identifier):
        state = self._jobs.get(job)
        if state is None:
            state = _CiJob(identifier)
            self._jobs[job] = state
        return state

    def _on_output(self, state, data, stream):
        line = data.line
        if isinstance(line, bytes):
            line = line.decode(errors='replace')
        line = _strip_ansi(line.rstrip('\n'))
        state.lines.append((stream, line))
        kind = _classify_line(line)
        if kind == 'warning':
            state.warnings += 1
        elif kind == 'error':
            state.errors += 1
            if state.first_error is None:
                match = _DIAG_LOCATION_RE.match(line)
                if match:
                    state.first_error = (
                        match.group('file'), match.group('line'),
                        match.group('msg'))

    def _finish(self, state, rc):
        state.end = time.monotonic()
        state.rc = rc
        self._finished.append(state)
        if rc == 0:
            verdict, word = 'OK', 'Finished'
        elif rc == SIGINT_RESULT:
            verdict, word = 'ABORTED', 'Aborted'
        else:
            verdict, word = 'FAILED', 'Failed'
        duration = format_duration(state.duration(), fixed_decimal_points=2)
        title = '{0}: {1} ({2})'.format(state.identifier, verdict, duration)

        if self._github:
            self._say(_ci.group(title))
        else:
            self._say('===== {0} output begin ====='.format(title))
        for stream, line in state.lines:
            self._say('[stderr] ' + line if stream == 'stderr' else line)
        if self._github:
            self._say(_ci.endgroup())
        else:
            self._say('===== {0} output end ====='.format(state.identifier))

        self._say('{0} <<< {1} [{2}]'.format(word, state.identifier, duration))
        if verdict == 'FAILED' and self._github:
            self._annotate_failure(state)

    def _annotate_failure(self, state):
        if state.first_error:
            path, line, message = state.first_error
            self._say(_ci.annotation(
                'error', '{0}: {1}'.format(state.identifier, message),
                file=_ci.annotation_path(path), line=line,
                title=state.identifier))
        else:
            self._say(_ci.annotation(
                'error', '{0} failed (exit code {1})'.format(
                    state.identifier, state.rc),
                title=state.identifier))

    def _print_summary(self):
        if not self.PRINT_SUMMARY:
            return
        total = format_duration(time.monotonic() - self._start)
        rows = []
        for state in sorted(
                self._finished, key=lambda s: s.duration(), reverse=True):
            if state.rc is None:
                result = 'SKIPPED'
            elif state.rc == 0:
                result = 'OK'
            elif state.rc == SIGINT_RESULT:
                result = 'ABORTED'
            else:
                result = 'FAILED'
            rows.append((
                state.identifier, result,
                format_duration(state.duration(), fixed_decimal_points=2),
                state.warnings, state.errors))

        self._say('')
        self._say('{0}  (wall time {1})'.format(self.SUMMARY_TITLE, total))
        width = max([len(r[0]) for r in rows] + [7])
        for name, result, duration, warnings, errors in rows:
            self._say('  {0:<8}  {1:<{w}} {2:>10}  {3}w {4}e'.format(
                result, name, duration, warnings, errors, w=width))

        if _ci.append_step_summary(self._step_summary_markdown(rows, total)):
            self._say('(summary written to $GITHUB_STEP_SUMMARY)')

    def _step_summary_markdown(self, rows, total):
        table = _ci.md_table(
            ['Package', 'Result', 'Time', 'Warnings', 'Errors'],
            [(name, result, duration, warnings, errors)
             for name, result, duration, warnings, errors in rows])
        return '### {0}\n\nWall time: {1}\n\n{2}'.format(
            self.SUMMARY_TITLE, total, table)

    # ------------------------------------------------------------------

    def __call__(self, event):  # noqa: D102
        data = event[0]

        if isinstance(data, JobStarted):
            state = self._state(event[1], data.identifier)
            state.start = time.monotonic()
            self._say('Starting >>> {0}'.format(data.identifier))
            return

        if isinstance(data, (StdoutLine, StderrLine)):
            state = self._jobs.get(event[1])
            if state is not None:
                stream = 'stderr' if isinstance(data, StderrLine) else 'stdout'
                self._on_output(state, data, stream)
            return

        if isinstance(data, JobEnded):
            state = self._state(event[1], data.identifier)
            if state.start is None:
                state.start = time.monotonic()
            self._finish(state, data.rc)
            return

        if isinstance(data, JobSkipped):
            state = self._state(event[1], data.identifier)
            state.start = state.end = time.monotonic()
            self._finished.append(state)
            self._say('Skipped <<< {0}'.format(data.identifier))
            return

        if isinstance(data, EventReactorShutdown):
            self._print_summary()


class CiTestStatusEventHandler(CiStatusEventHandler):
    """CI log for `ltest`: the same per-package output, without a table.

    `ltest` prints the test summary itself (tests, failures, failing cases),
    which is more useful than the per-job table this handler would print.
    """

    SUMMARY_TITLE = 'Test time summary'
    PRINT_SUMMARY = False
