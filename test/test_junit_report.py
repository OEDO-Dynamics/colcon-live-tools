# Copyright 2026 OEDO Dynamics Inc.
# Licensed under the Apache License, Version 2.0

"""JUnit reading, per-package summaries, fail-on-skip and the ltest report."""

import os
import time

from colcon_live_tools import _junit
from colcon_live_tools import _test_report

GTEST = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites tests="3" failures="1" disabled="0" errors="0">
  <testsuite name="CurveTest" tests="3" failures="1" disabled="0" errors="0">
    <testcase name="ok" classname="CurveTest" status="run" time="0.001"/>
    <testcase name="bad" classname="CurveTest" status="run" time="0.002"
              file="/src/test/curve_test.cpp" line="42">
      <failure message="Expected: 1&#10;Which is: 2">curve_test.cpp:42&#10;  Failure</failure>
    </testcase>
    <testcase name="later" classname="CurveTest" status="notrun">
      <skipped message="requires hardware"/>
    </testcase>
  </testsuite>
</testsuites>
"""

PYTEST_OK = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="2" errors="0" failures="0" skipped="1">
    <testcase classname="test_a" name="test_x" time="0.1"/>
    <testcase classname="test_a" name="test_y" time="0.1">
      <skipped type="pytest.skip" message="no display"/>
    </testcase>
  </testsuite>
</testsuites>
"""

PYTEST_ERROR = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="1" errors="1">
    <testcase classname="test_b" name="test_setup">
      <error message="fixture failed">Traceback: boom</error>
    </testcase>
  </testsuite>
</testsuites>
"""

CTEST_SITE = '<?xml version="1.0"?><Site BuildName="x"><Testing/></Site>'


def _write(directory, name, text, mtime=None):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(text, encoding='utf-8')
    if mtime is not None:
        os.utime(str(path), (mtime, mtime))
    return str(path)


def test_parse_junit_classifies_each_case(tmp_path):
    path = _write(tmp_path, 'gtest.xml', GTEST)
    cases = _junit.parse_junit(path)
    statuses = {c.name: c.status for c in cases}
    assert statuses == {
        'ok': 'passed', 'bad': 'failed', 'later': 'skipped'}
    bad = [c for c in cases if c.name == 'bad'][0]
    assert bad.full_name == 'CurveTest.bad'
    assert bad.file == '/src/test/curve_test.cpp' and bad.line == '42'
    assert bad.message.startswith('Expected: 1')
    assert bad.junit == path


def test_non_junit_xml_is_skipped_not_counted(tmp_path):
    _write(tmp_path / 'pkg', 'Test.xml', CTEST_SITE)
    summary = _junit.summarize_package('pkg', str(tmp_path / 'pkg'))
    assert summary.files == []
    assert summary.tests == 0


def test_summary_counts_and_skip_reason_filter(tmp_path):
    base = tmp_path / 'build' / 'pkg'
    _write(base, 'gtest.xml', GTEST)
    _write(base, 'pytest.xml', PYTEST_OK)
    plain = _junit.summarize_package('pkg', str(base))
    assert (plain.tests, plain.failures, plain.errors, plain.skipped) == (5, 1, 0, 2)
    assert len(plain.files) == 2

    gated = _junit.summarize_package(
        'pkg', str(base), fail_on_skip=['hardware'])
    # the 'requires hardware' skip now counts as a failure; 'no display' does not
    assert (gated.failures, gated.skipped) == (2, 2)
    skip_failed = [c for c in gated.cases if c.status == _junit.SKIP_FAILED]
    assert [c.name for c in skip_failed] == ['later']
    assert skip_failed[0].matched_skip == 'hardware'


def test_fail_on_skip_matches_reason_not_name(tmp_path):
    cases = [_junit.TestCase(name='hardware_test', status=_junit.SKIPPED,
                             message='no display')]
    _junit.apply_fail_on_skip(cases, ['hardware'])
    assert cases[0].status == _junit.SKIPPED


def test_stale_junit_files_are_ignored_with_since(tmp_path):
    base = tmp_path / 'pkg'
    old = time.time() - 3600
    _write(base, 'old.xml', PYTEST_ERROR, mtime=old)
    _write(base, 'new.xml', PYTEST_OK)
    summary = _junit.summarize_package('pkg', str(base), since=time.time() - 60)
    assert [os.path.basename(f) for f in summary.files] == ['new.xml']
    assert summary.errors == 0


def test_broken_xml_is_reported_as_a_problem(tmp_path):
    base = tmp_path / 'pkg'
    _write(base, 'broken.xml', '<testsuites><testsuite>')
    summary = _junit.summarize_package('pkg', str(base))
    assert summary.files == [] and len(summary.problems) == 1


def test_build_rows_status_rules(tmp_path):
    base = tmp_path / 'pkg'
    _write(base, 'gtest.xml', GTEST)
    summaries = {'pkg': _junit.summarize_package('pkg', str(base))}
    records = {
        'pkg': {'rc': 1, 'skipped': False, 'test_failure': False, 'duration': 1.0},
        'ok': {'rc': 0, 'skipped': False, 'test_failure': False, 'duration': 1.0},
        'blocked': {'rc': None, 'skipped': True, 'test_failure': False,
                    'duration': 0.0},
    }
    rows = {r.name: r for r in _test_report.build_rows(summaries, records)}
    assert rows['pkg'].status == _test_report.FAIL
    assert rows['ok'].status == _test_report.NO_JUNIT
    assert rows['blocked'].status == _test_report.SKIP


def test_render_text_lists_failing_case_and_location(tmp_path):
    base = tmp_path / 'pkg'
    _write(base, 'gtest.xml', GTEST)
    summaries = {'pkg': _junit.summarize_package('pkg', str(base))}
    records = {'pkg': {'rc': 1, 'skipped': False, 'test_failure': True,
                       'duration': 2.0}}
    rows = _test_report.build_rows(summaries, records)
    lines = _test_report.render_text(rows, title='Test time summary', wall_time=3.0)
    text = '\n'.join(lines)
    assert 'Tests' in lines[1] and 'Failures' in lines[1]
    assert 'FAIL' in text
    assert 'CurveTest.bad' in text
    assert 'Expected: 1' in text
    assert 'at /src/test/curve_test.cpp:42' in text
    assert '1 package(s) failed: pkg' in text


def test_render_markdown_and_annotations(tmp_path):
    base = tmp_path / 'pkg'
    _write(base, 'gtest.xml', GTEST)
    summaries = {'pkg': _junit.summarize_package('pkg', str(base))}
    records = {'pkg': {'rc': 0, 'skipped': False, 'test_failure': False,
                       'duration': 2.0}}
    rows = _test_report.build_rows(summaries, records)
    # rc 0 but a failing case still makes the package FAIL
    assert rows[0].status == _test_report.FAIL
    markdown = _test_report.render_markdown(rows, title='Test results', wall_time=3.0)
    assert markdown.startswith('### Test results')
    assert '| pkg | FAIL | 3 | 1 | 0 | 1 |' in markdown
    assert '#### Failed test cases' in markdown
    notes = _test_report.render_annotations(rows, environ={})
    assert len(notes) == 1
    assert notes[0].startswith('::error file=/src/test/curve_test.cpp,line=42,title=pkg::')
    assert 'CurveTest.bad' in notes[0]


def test_passing_run_has_no_failure_section(tmp_path):
    base = tmp_path / 'pkg'
    _write(base, 'pytest.xml', PYTEST_OK)
    summaries = {'pkg': _junit.summarize_package('pkg', str(base))}
    records = {'pkg': {'rc': 0, 'skipped': False, 'test_failure': False,
                       'duration': 0.5}}
    rows = _test_report.build_rows(summaries, records)
    text = '\n'.join(_test_report.render_text(rows, title='T', wall_time=1.0))
    assert 'all packages passed' in text
    assert _test_report.render_annotations(rows) == []
    assert '#### Failed' not in _test_report.render_markdown(
        rows, title='T', wall_time=1.0)
