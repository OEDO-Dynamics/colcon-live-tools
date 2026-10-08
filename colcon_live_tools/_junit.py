# Copyright 2026 OEDO Dynamics Inc.
# Licensed under the Apache License, Version 2.0

"""
Read the JUnit XML that colcon test tasks write (gtest, pytest, cppcheck,
xmllint, ...) and summarize it per package.

Only the test cases are counted (the ``tests`` / ``failures`` attributes of a
suite are not trusted, since some producers leave them out). A test case is:

- ``failed`` when it has a ``<failure>`` child,
- ``error`` when it has an ``<error>`` child,
- ``skipped`` when it has a ``<skipped>`` child,
- ``passed`` otherwise.

``--fail-on-skip`` turns a skipped case into ``skip-failed`` when its skip
reason matches one of the regular expressions.
"""

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional

PASSED = 'passed'
FAILED = 'failed'
ERROR = 'error'
SKIPPED = 'skipped'
SKIP_FAILED = 'skip-failed'


class NotJUnitError(ValueError):
    """The XML file is not a JUnit report (for example a CTest Test.xml)."""


@dataclass
class TestCase:
    """One ``<testcase>`` and its outcome."""

    classname: str = ''
    name: str = ''
    status: str = PASSED
    message: str = ''
    file: Optional[str] = None
    line: Optional[str] = None
    junit: str = ''
    matched_skip: Optional[str] = None

    @property
    def full_name(self):
        """``classname.name``, or just the name when there is no classname."""
        return '.'.join(part for part in (self.classname, self.name) if part)

    @property
    def is_failure(self):
        """True for failed, errored and skip-failed cases."""
        return self.status in (FAILED, ERROR, SKIP_FAILED)


@dataclass
class PackageSummary:
    """All test cases found for one package in one run."""

    name: str
    files: List[str] = field(default_factory=list)
    cases: List[TestCase] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)

    @property
    def tests(self):
        return len(self.cases)

    @property
    def failures(self):
        return sum(1 for c in self.cases if c.status in (FAILED, SKIP_FAILED))

    @property
    def errors(self):
        return sum(1 for c in self.cases if c.status == ERROR)

    @property
    def skipped(self):
        """All skipped cases, including skip-failed ones."""
        return sum(1 for c in self.cases if c.status in (SKIPPED, SKIP_FAILED))

    @property
    def failed_cases(self):
        return [c for c in self.cases if c.is_failure]


def _message_of(element):
    if element is None:
        return ''
    message = (element.get('message') or '').strip()
    body = (element.text or '').strip()
    if body and body != message:
        return '\n'.join(part for part in (message, body) if part)
    return message


def _testcase(element, junit):
    case = TestCase(
        classname=element.get('classname') or '',
        name=element.get('name') or '',
        file=element.get('file') or None,
        line=element.get('line') or None,
        junit=junit)
    failure = element.find('failure')
    error = element.find('error')
    skipped = element.find('skipped')
    if failure is not None:
        case.status, case.message = FAILED, _message_of(failure)
    elif error is not None:
        case.status, case.message = ERROR, _message_of(error)
    elif skipped is not None:
        case.status, case.message = SKIPPED, _message_of(skipped)
    return case


def parse_junit(path):
    """
    Return the test cases of one JUnit file.

    Raises `NotJUnitError` when the root element is neither ``testsuite`` nor
    ``testsuites``, and `xml.etree.ElementTree.ParseError` for broken XML.
    """
    root = ET.parse(path).getroot()
    if root.tag not in ('testsuite', 'testsuites'):
        raise NotJUnitError('root element is <{0}>'.format(root.tag))
    containers = [e for e in root.iter() if e.tag in ('testsuite', 'testsuites')]
    cases = []
    for container in containers:
        for element in container.findall('testcase'):
            cases.append(_testcase(element, path))
    return cases


def apply_fail_on_skip(cases, patterns):
    """Mark skipped cases whose skip reason matches any pattern as failures."""
    compiled = [re.compile(p) for p in (patterns or ())]
    if not compiled:
        return
    for case in cases:
        if case.status != SKIPPED:
            continue
        for pattern in compiled:
            if pattern.search(case.message or ''):
                case.status = SKIP_FAILED
                case.matched_skip = pattern.pattern
                break


def find_junit_files(search_dir, *, since=None):
    """
    All ``*.xml`` files under `search_dir`, oldest name first.

    With `since` (a POSIX timestamp), files modified before it are skipped,
    so results left over from an earlier run are not reported as current.
    """
    found = []
    if not os.path.isdir(search_dir):
        return found
    for root, _dirs, files in os.walk(search_dir):
        for name in files:
            if not name.endswith('.xml'):
                continue
            path = os.path.join(root, name)
            if since is not None and os.path.getmtime(path) < since:
                continue
            found.append(path)
    return sorted(found)


def summarize_package(name, search_dir, *, since=None, fail_on_skip=()):
    """Parse every JUnit file under `search_dir` into a `PackageSummary`."""
    summary = PackageSummary(name=name)
    for path in find_junit_files(search_dir, since=since):
        try:
            cases = parse_junit(path)
        except NotJUnitError:
            continue
        except (ET.ParseError, OSError) as exc:
            summary.problems.append('{0}: {1}'.format(path, exc))
            continue
        summary.files.append(path)
        summary.cases.extend(cases)
    apply_fail_on_skip(summary.cases, fail_on_skip)
    return summary
