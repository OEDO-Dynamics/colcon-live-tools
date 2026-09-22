# Copyright 2026 OEDO Dynamics Inc.
# Licensed under the Apache License, Version 2.0

"""
A lightweight, terminal-native live status board for `colcon build`.

Modeled after the UX of `catkin_tools` (ROS 1): while the build is running,
every package that is currently building gets its own line showing how long
it has been running; when the build finishes, a build-time table (slowest
package first) and the tail of stderr/stdout for any failed package are
printed.

A few things this adds on top of what `catkin_tools` did:

- Color. On a TTY (and unless ``NO_COLOR`` is set -- see
  https://no-color.org), package/status lines are colorized: a rotating,
  stable-per-run color per package name (so you can visually track a line
  across redraws), green/red/yellow for OK/FAILED/ABORTED, yellow for
  warning counts. `colcon-core` has an ``output_style``/``Style`` extension
  point for this, but as of the `colcon-core` release this was built
  against, no installable extension actually implements it -- every
  `Style.X(...)` call is a silent no-op -- so this handler does its own
  minimal ANSI coloring instead of depending on it.
- Per-package warning/error counts. Every stdout/stderr line is scanned for
  compiler-style (``: warning:`` / ``: error:``) and CMake-style (``CMake
  Warning`` / ``CMake Error``) diagnostics; the counts show up live next to
  the package and again in the final table, the way `catkin_tools` surfaces
  "N warnings" without dumping the full log for a package that still
  succeeded.

Depends only on the Python standard library and `colcon-core` -- no `rich`,
`curses` or `textual` -- so installing it adds effectively no weight to a
ROS 2 workspace's tooling. It does not replace colcon's other console
handlers (`console_start_end`, `console_direct`, `console_stderr`, ...); it
only adds the multi-row live view and the final table, and is careful to
never clobber whatever else those handlers print (see `_ScreenWriter`
below). The `lbuild`/`lb` verb (see `colcon_live_tools.verb.lbuild`) turns
those other handlers off by default, since this handler already captures
everything they would have shown (every stdout/stderr line is seen here
regardless of which other handlers are enabled) -- nothing is lost, the
terminal just stays as quiet as `catkin build`'s was.

Usage::

    colcon lbuild   # or: colcon lb

Without that verb, this handler can still be enabled directly on plain
`colcon build`::

    colcon build --event-handlers status- summary- console_start_end- \\
        console_stderr- console_direct- live_status+ \\
        --continue-on-error --parallel-workers 0

(the exact set of handlers worth disabling depends on which colcon
extensions happen to be installed; see `lbuild.py` for the discovery logic
that picks only the ones that actually exist.)
"""

from collections import deque, OrderedDict
import os
import re
import shutil
import sys
import time

from colcon_core.event.job import JobEnded
from colcon_core.event.job import JobProgress
from colcon_core.event.job import JobQueued
from colcon_core.event.job import JobSkipped
from colcon_core.event.job import JobStarted
from colcon_core.event.output import StderrLine
from colcon_core.event.output import StdoutLine
from colcon_core.event.timer import TimerEvent
from colcon_core.event_handler import EventHandlerExtensionPoint
from colcon_core.event_handler import format_duration
from colcon_core.event_reactor import EventReactorShutdown
from colcon_core.plugin_system import satisfies_version
from colcon_core.subprocess import SIGINT_RESULT

# matches make-style '[ 42%] Building ...' progress lines
_PERCENT_RE = re.compile(r'^\[\s*(\d{1,3})%\]\s')
# matches ninja-style '[3/12] ...' progress lines
_FRACTION_RE = re.compile(r'^\[(\d+)/(\d+)\]\s')

# compiler-style 'file.cpp:12:5: warning: ...' / '...: error: ...'
_COMPILER_DIAG_RE = re.compile(r':\s*(warning|error):', re.IGNORECASE)
# CMake's own 'CMake Warning ...' / 'CMake Error ...'
_CMAKE_DIAG_RE = re.compile(r'^CMake (Warning|Error)\b')
# GCC/Clang auto-colorize their own diagnostics when they think they are
# writing to a TTY (which, under this handler, they often are -- colcon
# runs the build tool with its stdout/stderr inherited from this process).
# Escape codes can land *between* 'file.cpp:12:5:' and 'warning:', which
# would otherwise defeat both the regex above and the progress-percent one,
# so every captured line has ANSI stripped before anything else looks at it.
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def _strip_ansi(text):
    if '\x1b' not in text:
        return text
    return _ANSI_RE.sub('', text)


#: how many concurrently-running packages to show at once before collapsing
#: the rest into an "... and N more" line
DEFAULT_MAX_VISIBLE_ROWS = 12
#: how many trailing output lines to keep per job, for the failure report
DEFAULT_TAIL_LINES = 20
#: max characters of a package name shown in a live row before truncating
_NAME_COL_WIDTH = 32

#: rotating palette for per-package names in the live view (deliberately
#: excludes red/green, which are reserved for failure/success elsewhere)
_PACKAGE_PALETTE = ('34', '35', '36', '33')  # blue, magenta, cyan, yellow


def _package_color_code(name):
    """Pick a stable-for-this-run ANSI color code for a package name."""
    return _PACKAGE_PALETTE[hash(name) % len(_PACKAGE_PALETTE)]


def _classify_line(line):
    """Return ``'warning'``, ``'error'`` or `None` for one output line."""
    match = _COMPILER_DIAG_RE.search(line)
    if match:
        return match.group(1).lower()
    match = _CMAKE_DIAG_RE.match(line)
    if match:
        return 'warning' if match.group(1) == 'Warning' else 'error'
    return None


def _plain_diag_fragment(warnings, errors):
    """Plain-text (uncolored) '<n>w <n>e'-style fragment, for width math."""
    parts = []
    if warnings:
        parts.append('{0}w'.format(warnings))
    if errors:
        parts.append('{0}e'.format(errors))
    return ' '.join(parts)


def _diag_fragment(paint, warnings, errors):
    """Colored version of :func:`_plain_diag_fragment`."""
    parts = []
    if warnings:
        parts.append(paint.yellow('{0}w'.format(warnings)))
    if errors:
        parts.append(paint.bold_red('{0}e'.format(errors)))
    return ' '.join(parts)


def _fit(plain, colored, width):
    """
    Return `colored` if it fits in `width` printed columns, else `plain`
    truncated to `width` characters.

    Never truncates `colored` itself: slicing a string that contains ANSI
    escape codes on a narrow terminal could cut a code in half and corrupt
    the screen, so when the colored text would not fit, the *uncolored*
    text is truncated instead (color codes add no visible width, so
    `plain` and `colored` always have the same *printed* length when both
    fit).
    """
    if len(plain) <= width:
        return colored
    return plain[:width]


class _Paint:
    """
    A tiny, always-safe ANSI colorizer.

    `colcon_core.output_style.Style` exists as an extension point, but (see
    the module docstring) nothing currently implements it, so every
    `Style.X(...)` call is a no-op. This does the actual coloring instead.

    Every method is a plain passthrough when `enabled` is false (piped
    output, `NO_COLOR` set, or a non-TTY), so nothing here ever writes an
    escape code somewhere it could corrupt a log file.
    """

    def __init__(self, enabled):  # noqa: D107
        self._enabled = enabled

    def _wrap(self, code, text):
        if not self._enabled or not text:
            return text
        return '\x1b[{0}m{1}\x1b[0m'.format(code, text)

    def bold(self, text):
        return self._wrap('1', text)

    def dim(self, text):
        return self._wrap('2', text)

    def red(self, text):
        return self._wrap('31', text)

    def yellow(self, text):
        return self._wrap('33', text)

    def cyan(self, text):
        return self._wrap('36', text)

    def bold_red(self, text):
        return self._wrap('1;31', text)

    def bold_green(self, text):
        return self._wrap('1;32', text)

    def bold_yellow(self, text):
        return self._wrap('1;33', text)

    def package_name(self, text):
        return self._wrap(_package_color_code(text), text)


class _JobState:
    """Bookkeeping for a single job, keyed by the colcon `Job` instance."""

    __slots__ = (
        'identifier', 'start_time', 'end_time', 'rc', 'progress', 'tail',
        'warnings', 'errors',
    )

    def __init__(self, identifier):  # noqa: D107
        self.identifier = identifier
        self.start_time = None
        self.end_time = None
        self.rc = None
        self.progress = None
        self.tail = deque(maxlen=DEFAULT_TAIL_LINES)
        self.warnings = 0
        self.errors = 0

    def duration(self, *, now=None):
        """Elapsed (or final) duration in seconds."""
        if self.start_time is None:
            return 0.0
        end = self.end_time if self.end_time is not None else (
            now if now is not None else time.monotonic())
        return max(0.0, end - self.start_time)


class _ScreenWriter:
    """
    Owns the bottom-of-screen "live region" and keeps it from corrupting
    (or being corrupted by) any other output.

    Several other event handlers write to `sys.stdout`/`sys.stderr` while
    a build runs (`console_start_end`, `console_direct`, `console_stderr`,
    a build tool's own pass-through output, ...). If those writes happen
    between two of *our* redraws, a naive "move the cursor up N lines and
    clear" would erase lines that we do not own, corrupting the terminal.

    To avoid that, every real write to stdout/stderr is intercepted: the
    live region is erased first (a no-op if it is already clear), *then*
    the real write happens, and finally the live region -- if still wanted
    -- gets redrawn on top. This is the same technique colcon-core's own
    built-in `status` event handler uses for its single status line; here
    it is generalized to a multi-line region.
    """

    def __init__(self):
        self._line_count = 0
        self._installed = False
        self._real_writes = {}

    def install(self):
        if self._installed:
            return
        try:
            targets = [
                (sys.stdout, 'write'),
                (sys.stdout.buffer, 'write'),
                (sys.stderr, 'write'),
                (sys.stderr.buffer, 'write'),
            ]
        except AttributeError:
            return
        for obj, attr in targets:
            real = getattr(obj, attr)
            self._real_writes[(id(obj), attr)] = (obj, attr, real)
            setattr(obj, attr, self._make_hook(real))
        self._installed = True

    def uninstall(self):
        if not self._installed:
            return
        self.clear()
        for obj, attr, real in self._real_writes.values():
            setattr(obj, attr, real)
        self._real_writes.clear()
        self._installed = False

    def _make_hook(self, real_write):
        def hook(data):
            self.clear()
            return real_write(data)
        return hook

    def _raw_stdout_write(self, text):
        _, _, real = self._real_writes.get(
            (id(sys.stdout.buffer), 'write'),
            (None, None, None))
        if real is None:
            return
        real(text.encode())
        sys.stdout.flush()

    def clear(self):
        n = self._line_count
        if not n:
            return
        # guard re-entrancy: the write below goes through the *real*
        # writer, never the hook, so there is nothing to guard against,
        # but zero the counter first anyway to keep the invariant simple.
        self._line_count = 0
        self._raw_stdout_write(
            '\x1b[{n}A'.format(n=n)
            + '\x1b[2K\x1b[1B' * n
            + '\x1b[{n}A'.format(n=n))

    def draw(self, lines):
        self.clear()
        if not lines:
            return
        self._raw_stdout_write('\n'.join(lines) + '\n')
        self._line_count = len(lines)


class LiveStatusEventHandler(EventHandlerExtensionPoint):
    """
    Show a multi-row live status board while packages build in parallel.

    On a TTY: continuously redraws one line per in-progress package (name +
    elapsed time + build-tool progress + warning/error counts, when
    available) below a one-line header (elapsed / done / running / warnings
    / failed counts). When the build ends, the live region is replaced by a
    build-time table sorted slowest-first, followed by the tail of output
    for every failed package. Colorized on a TTY unless `NO_COLOR` is set.

    When stdout is not a TTY (redirected to a file, CI log, etc.) no live
    view is drawn -- there is nothing to redraw in a log file -- but the
    final build-time table and failure tails are still printed (in plain
    text, no color), so the log stays useful.

    Handles events of the following types:
    - :py:class:`colcon_core.event.job.JobQueued`
    - :py:class:`colcon_core.event.job.JobStarted`
    - :py:class:`colcon_core.event.job.JobProgress`
    - :py:class:`colcon_core.event.job.JobEnded`
    - :py:class:`colcon_core.event.job.JobSkipped`
    - :py:class:`colcon_core.event.output.StdoutLine`
    - :py:class:`colcon_core.event.output.StderrLine`
    - :py:class:`colcon_core.event.timer.TimerEvent`
    - :py:class:`colcon_core.event_reactor.EventReactorShutdown`
    """

    PRIORITY = 50

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            EventHandlerExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

        # disabled by default: this is an *additional* handler users opt
        # into (alongside disabling the built-in status/summary handlers),
        # not a replacement colcon should always load.
        self.enabled = False

        self._tty = sys.stdout.isatty()
        # colorize on a TTY unless NO_COLOR is set (https://no-color.org);
        # never on a non-TTY, so a redirected log file never gets escape
        # codes written into it
        self._color = self._tty and os.environ.get('NO_COLOR') is None
        self._paint = _Paint(self._color)
        self._start_time = time.monotonic()
        self._queued_count = 0
        self._jobs = OrderedDict()  # Job instance -> _JobState
        self._finished = []  # _JobState, in JobEnded/JobSkipped order
        self._max_visible_rows = DEFAULT_MAX_VISIBLE_ROWS
        self._shutting_down = False
        self._screen = _ScreenWriter() if self._tty else None

        if self._screen is not None:
            self._screen.install()

    # ------------------------------------------------------------------
    # bookkeeping helpers
    # ------------------------------------------------------------------

    def _state_for(self, job, identifier=None):
        state = self._jobs.get(job)
        if state is None:
            state = _JobState(identifier or getattr(job, 'identifier', '?'))
            self._jobs[job] = state
        return state

    @staticmethod
    def _extract_progress(line):
        match = _PERCENT_RE.match(line)
        if match:
            return match.group(1).strip() + '%'
        match = _FRACTION_RE.match(line)
        if match:
            done, total = int(match.group(1)), int(match.group(2))
            if total:
                return '{:.0%}'.format(done / total)
        return None

    def _running_jobs(self):
        return [
            (job, state) for job, state in self._jobs.items()
            if state.start_time is not None and state.end_time is None
        ]

    # ------------------------------------------------------------------
    # live rendering (TTY only)
    # ------------------------------------------------------------------

    def _render_live_region(self):
        if self._screen is None or self._shutting_down:
            return

        now = time.monotonic()
        running = self._running_jobs()

        width = shutil.get_terminal_size(fallback=(100, 24)).columns
        lines = []

        elapsed = format_duration(
            now - self._start_time, fixed_decimal_points=1)
        failed = sum(
            1 for s in self._finished if s.rc and s.rc != SIGINT_RESULT)
        total_warnings = sum(s.warnings for s in self._jobs.values())
        done_fragment = '{0}/{1} done'.format(
            len(self._finished), self._queued_count)
        warn_fragment = (
            '  {0} warnings'.format(total_warnings) if total_warnings else '')
        failed_fragment = '  {0} failed'.format(failed) if failed else ''

        plain_header = '[{elapsed}] {done}  {running} running{warn}{failed}'.format(
            elapsed=elapsed, done=done_fragment, running=len(running),
            warn=warn_fragment, failed=failed_fragment)
        colored_header = '[{elapsed}] {done}  {running} running{warn}{failed}'.format(
            elapsed=elapsed,
            done=self._paint.bold_green(done_fragment),
            running=len(running),
            warn=self._paint.yellow(warn_fragment) if total_warnings else '',
            failed=self._paint.bold_red(failed_fragment) if failed else '')
        lines.append(_fit(plain_header, colored_header, width))

        visible = running[:self._max_visible_rows]
        for _job, state in visible:
            name = state.identifier
            if len(name) > _NAME_COL_WIDTH:
                name = name[:_NAME_COL_WIDTH - 1] + '…'
            padded_name = '{0:<{1}}'.format(name, _NAME_COL_WIDTH)
            duration = format_duration(
                state.duration(now=now), fixed_decimal_points=1)

            plain_row = '  ▸ {name} {duration:>8}'.format(
                name=padded_name, duration=duration)
            colored_row = '  ▸ {name} {duration:>8}'.format(
                name=self._paint.package_name(padded_name),
                duration=duration)

            if state.progress:
                fragment = '  ' + state.progress
                plain_row += fragment
                colored_row += fragment

            diag_plain = _plain_diag_fragment(state.warnings, state.errors)
            if diag_plain:
                plain_row += '  ' + diag_plain
                colored_row += '  ' + _diag_fragment(
                    self._paint, state.warnings, state.errors)

            lines.append(_fit(plain_row, colored_row, width))

        hidden = len(running) - len(visible)
        if hidden > 0:
            lines.append(self._paint.dim(
                '  … and {0} more running'.format(hidden)))

        self._screen.draw(lines)

    # ------------------------------------------------------------------
    # final report (always printed, TTY or not)
    # ------------------------------------------------------------------

    def _print_final_report(self):
        total_duration = format_duration(time.monotonic() - self._start_time)

        ok = [s for s in self._finished if s.rc == 0]
        failed = [s for s in self._finished if s.rc and s.rc != SIGINT_RESULT]
        aborted = [s for s in self._finished if s.rc == SIGINT_RESULT]
        skipped = [s for s in self._finished if s.rc is None]

        by_duration = sorted(
            self._finished, key=lambda s: s.duration(), reverse=True)
        name_width = max([len(s.identifier) for s in by_duration] + [7])
        diag_width = max(
            [len(_plain_diag_fragment(s.warnings, s.errors))
             for s in by_duration] + [0])

        print()
        print(self._paint.bold('Build time summary')
              + '  (wall time {0})'.format(total_duration))
        for state in by_duration:
            if state.rc is None:
                mark = self._paint.dim('SKIP  ')
            elif state.rc == 0:
                mark = self._paint.bold_green('OK    ')
            elif state.rc == SIGINT_RESULT:
                mark = self._paint.bold_yellow('ABORT ')
            else:
                mark = self._paint.bold_red('FAILED')

            line = '  {mark}  {name:<{w}} {duration:>10}'.format(
                mark=mark, name=state.identifier, w=name_width,
                duration=format_duration(
                    state.duration(), fixed_decimal_points=2))
            if diag_width:
                plain_diag = _plain_diag_fragment(
                    state.warnings, state.errors)
                colored_diag = _diag_fragment(
                    self._paint, state.warnings, state.errors)
                line += '  ' + colored_diag + (
                    ' ' * (diag_width - len(plain_diag)))
            print(line)

        print()
        summary_line = (
            '{0} finished, {1} failed, {2} aborted, {3} skipped'.format(
                len(ok), len(failed), len(aborted), len(skipped)))
        if failed:
            plain_failed = '{0} failed'.format(len(failed))
            summary_line = summary_line.replace(
                plain_failed, self._paint.bold_red(plain_failed), 1)
        print(summary_line)

        for state in failed:
            print()
            print(self._paint.bold_red(
                '----- {0}: last output -----'.format(state.identifier)))
            if not state.tail:
                print('  (no captured output)')
            for stream, line in state.tail:
                if stream == 'stderr':
                    print('  ' + self._paint.red('[stderr] ' + line))
                else:
                    print('  ' + self._paint.dim(line))

    # ------------------------------------------------------------------
    # event dispatch
    # ------------------------------------------------------------------

    def __call__(self, event):  # noqa: D102
        data = event[0]

        if isinstance(data, JobQueued):
            self._queued_count += 1
            return

        if isinstance(data, JobStarted):
            job = event[1]
            state = self._state_for(job, data.identifier)
            state.start_time = time.monotonic()
            # a new row appearing is worth showing right away
            self._render_live_region()
            return

        if isinstance(data, JobProgress):
            job = event[1]
            state = self._jobs.get(job)
            if state is not None:
                state.progress = data.progress
            # left for the next TimerEvent tick; progress changes too
            # frequently to redraw on every single one
            return

        if isinstance(data, (StdoutLine, StderrLine)):
            job = event[1]
            state = self._jobs.get(job)
            if state is None:
                return
            line = data.line
            if isinstance(line, bytes):
                line = line.decode(errors='replace')
            line = _strip_ansi(line.rstrip('\n'))
            stream = 'stderr' if isinstance(data, StderrLine) else 'stdout'
            state.tail.append((stream, line))
            progress = self._extract_progress(line)
            if progress:
                state.progress = progress
            kind = _classify_line(line)
            if kind == 'warning':
                state.warnings += 1
            elif kind == 'error':
                state.errors += 1
            # also left for the next TimerEvent tick, for the same reason
            return

        if isinstance(data, JobSkipped):
            job = event[1]
            state = self._state_for(job, data.identifier)
            now = time.monotonic()
            if state.start_time is None:
                state.start_time = now
            state.end_time = now
            state.rc = None
            self._finished.append(state)
            self._render_live_region()
            return

        if isinstance(data, JobEnded):
            job = event[1]
            state = self._state_for(job, data.identifier)
            state.end_time = time.monotonic()
            state.rc = data.rc
            self._finished.append(state)
            # a row disappearing is worth showing right away too
            self._render_live_region()
            return

        if isinstance(data, TimerEvent):
            self._render_live_region()
            return

        if isinstance(data, EventReactorShutdown):
            self._shutting_down = True
            if self._screen is not None:
                self._screen.uninstall()
            self._print_final_report()
            return
