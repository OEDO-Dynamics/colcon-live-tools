#!/usr/bin/env bash
# Quick demo: build 4 dummy CMake packages (three succeed at different
# speeds, one fails fast) with colcon-live-tools enabled, so you can see
# the live board and the final build-time table without touching your own
# workspace.
#
# Requires: colcon-core + colcon-cmake (and this package) already installed,
# plus `cmake` on PATH. No ROS install needed -- these are plain CMake
# projects with no source files.
set -euo pipefail
cd "$(dirname "$0")/demo_ws"
rm -rf build install log
colcon lbuild
