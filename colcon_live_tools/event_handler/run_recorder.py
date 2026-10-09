# Copyright 2026 OEDO Dynamics Inc.
# Licensed under the Apache License, Version 2.0

"""
Silent event handler that records each job's outcome for the `ltest` verb.

It prints nothing. It keeps, per job identifier, the exit code, whether the
job was skipped, whether a `TestFailure` event was seen, and the duration.
`ltest` reads the records after the run; they live in a module-level dict,
which is fine because one colcon invocation runs one test session.
"""

from collections import OrderedDict
import time

from colcon_core.event.job import JobEnded
from colcon_core.event.job import JobSkipped
from colcon_core.event.job import JobStarted
from colcon_core.event.test import TestFailure
from colcon_core.event_handler import EventHandlerExtensionPoint
from colcon_core.plugin_system import satisfies_version

#: identifier -> dict(rc, skipped, test_failure, duration)
_RECORDS = OrderedDict()
_STARTED = {}


def reset():
    """Forget everything recorded so far (call before each `ltest` run)."""
    _RECORDS.clear()
    _STARTED.clear()


def snapshot():
    """A copy of the records, in the order the jobs were first seen."""
    return OrderedDict(
        (name, dict(record)) for name, record in _RECORDS.items())


def _record(identifier):
    record = _RECORDS.get(identifier)
    if record is None:
        record = {'rc': None, 'skipped': False, 'test_failure': False,
                  'duration': 0.0}
        _RECORDS[identifier] = record
    return record


class RunRecorderEventHandler(EventHandlerExtensionPoint):
    """Record job outcomes for `ltest`; never writes to the terminal."""

    PRIORITY = 50

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            EventHandlerExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')
        self.enabled = False

    def __call__(self, event):  # noqa: D102
        data = event[0]
        if isinstance(data, JobStarted):
            _STARTED[data.identifier] = time.monotonic()
            _record(data.identifier)
        elif isinstance(data, JobEnded):
            record = _record(data.identifier)
            record['rc'] = data.rc
            started = _STARTED.get(data.identifier)
            if started is not None:
                record['duration'] = time.monotonic() - started
        elif isinstance(data, JobSkipped):
            _record(data.identifier)['skipped'] = True
        elif isinstance(data, TestFailure):
            _record(data.identifier)['test_failure'] = True
