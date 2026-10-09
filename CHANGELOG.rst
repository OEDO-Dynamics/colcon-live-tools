^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Changelog for package colcon-live-tools
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

0.2.0 (2026-10-09)
------------------
* Added ``ltest`` / ``lt`` verb: ``colcon test`` with the same live per-package
  board as ``lbuild``, a readable result summary (tests, failures, errors and
  skipped per package; failing test cases with their messages; JUnit locations),
  a non-zero exit code on any failure, and an isolated ``ROS_DOMAIN_ID`` for the
  run (``--isolated-domain``, on by default; ``--no-isolated-domain`` turns it off).
  The isolated domain is drawn from 1 to 101, not the current domain.
* ``ltest`` options: ``--no-user-site`` (``PYTHONNOUSERSITE=1`` for the test
  processes, including every Python child of the run), ``--fail-on-skip PATTERN``
  (a skip whose reason matches counts as a failure), ``--retest-failed`` (only the
  packages that failed last time), ``--allow-no-tests`` (a run with zero test cases
  is an error in CI mode unless this is given).
* CI mode for ``lbuild`` and ``ltest``: enabled by ``--ci``, or by ``CI`` or
  ``GITHUB_ACTIONS`` being set. It prints a stable per-package log instead of the
  live board; on GitHub Actions it uses ``::group::`` blocks, ``::error``
  annotations, and writes a Markdown summary to ``$GITHUB_STEP_SUMMARY``. A non-TTY
  stdout alone does not enable it, so piped ``lbuild`` output is unchanged from
  0.1.1.
* ``lbuild`` and ``lclean`` terminal behavior is unchanged.
* The new event handlers are registered as ``live_tools_test_status``,
  ``live_tools_ci_status``, ``live_tools_ci_test_status`` and
  ``live_tools_test_recorder`` (the existing ``live_status`` name is kept).
  When a CI handler is not registered, ``lbuild`` falls back to the live board
  instead of failing with a ``KeyError``.
* Added a pytest suite under ``test/`` (JUnit summary, CI mode, workflow commands,
  step summary, fail-on-skip, domain isolation, the ``ltest`` verb), run in CI.

0.1.1 (2026-09-23)
------------------
* No functional changes.
* README rewritten: English moved to the top (with the original Japanese
  kept below it), CI/PyPI/license badges added, maintainer-only PyPI/apt
  publishing instructions moved out to ``.docs/PUBLISHING.md``, and the
  usage section expanded with a full option reference for ``lbuild``/
  ``lb``/``lclean``/``lc``.
* Stale Japanese-only ``TODO`` comments in ``setup.cfg`` resolved and
  translated (kept bilingual, English + Japanese).
* Added ``.gitignore`` (covers build artifacts and local ``.pypirc``).

0.1.0 (2026-09-23)
------------------
* Initial release.
* ``live_status`` event handler: live per-package build status board with
  colors, warning/error counts, and a final build-time summary table.
* ``lbuild`` / ``lb`` verb: ``colcon build`` with catkin_tools-like
  defaults (live status on, ``--continue-on-error`` on, unlimited
  parallel workers).
* ``lclean`` / ``lc`` verb: ``catkin clean``-equivalent workspace cleanup.
* Locale-aware (``ja``/``pt``/``en``) help text for this package's own
  arguments.

..
   This file follows the format used by ``catkin_generate_changelog`` /
   bloom, so that a future ROS (apt) release of this package can pick it
   up automatically. Add a new dated section at the top for every release.
