^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Changelog for package colcon-live-tools
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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
