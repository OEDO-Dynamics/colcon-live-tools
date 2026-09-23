# Publishing to PyPI

Maintainer-only notes for releasing `colcon-live-tools`. Not needed by users of this
package — see [README.md](../README.md) for that. Kept out of the README on purpose so
the public-facing docs stay focused on using the package, not maintaining it.

## Current state

- Package name `colcon-live-tools` is registered on PyPI: https://pypi.org/project/colcon-live-tools/
- Released versions: see the link above (`0.1.0`, then `0.1.1` as of 2026-09-23).
- Credentials: an API token for both `pypi` and `testpypi` index servers lives in
  `~/.pypirc` (or the repo-root `.pypirc`, which is git-ignored — see below). Format:

  ```ini
  [distutils]
  index-servers =
      pypi
      testpypi

  [pypi]
  username = __token__
  password = <PyPI API token>

  [testpypi]
  repository = https://test.pypi.org/legacy/
  username = __token__
  password = <TestPyPI API token>
  ```

  Never commit this file. Confirm `.pypirc` is listed in `.gitignore` before adding
  anything to it.

## PyPI does not allow overwriting a version

Once a version (e.g. `0.1.0`) has been uploaded, PyPI permanently rejects re-uploading
that exact version, even after deleting it there. Every release — including a
docs-only or comment-only change with no functional difference — needs a fresh version
number.

## Release checklist

1. Bump the version:
   - `colcon_live_tools/__init__.py` → `__version__ = 'X.Y.Z'`
   - `CHANGELOG.rst` → add a new dated section at the top, in the format
     `catkin_generate_changelog`/`bloom` expects (see the comment at the bottom of that
     file) — this is what lets a future ROS/apt release via `bloom` pick it up
     automatically.
2. Build in a clean environment:

   ```bash
   python -m pip install --upgrade build twine
   rm -rf dist build *.egg-info
   python -m build          # produces dist/*.tar.gz and dist/*.whl
   ```

3. Sanity-check the built distribution:

   ```bash
   python -m twine check dist/*
   ```

4. (Recommended) Upload to TestPyPI first and verify install from there in a scratch
   venv:

   ```bash
   python -m twine upload --repository testpypi dist/*
   python -m venv /tmp/colcon-live-tools-smoke && . /tmp/colcon-live-tools-smoke/bin/activate
   pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ colcon-live-tools
   colcon --help | grep -E "lbuild|lclean"
   deactivate
   ```

5. Upload to the real index:

   ```bash
   python -m twine upload dist/*
   ```

6. Tag the release in git and push the tag:

   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

## Optional: apt / ROS build farm distribution (`bloom`)

`colcon-core` and its own extension packages are also distributed via the ROS apt
repository (`packages.ros.org`), built by the ROS build farm — not a personal PPA. This
is a separate, heavier process than a PyPI release, gated by ROS community review, and
not something done for every release. Only pursue this once there is real demand beyond
`pip install`.

1. PyPI release (above) must exist first — `bloom` pulls from there.
2. `pip install -U bloom`
3. `bloom` has a `pip` release track for plain (non-ROS-package) pip packages — the
   same track `colcon-core`'s own extensions use:

   ```bash
   bloom-release --track pip --rosdistro <a current ROS distro name> colcon-live-tools
   ```

   This generates Debian packaging (expected name: `python3-colcon-live-tools`) from
   the PyPI source distribution.
4. `bloom-release` opens a pull request against `ros/rosdistro`. This is reviewed and
   merged by ROS maintainers — can take anywhere from a few days to a few weeks.
5. Once merged, the ROS build farm builds `.deb` packages automatically and publishes
   them to `packages.ros.org`. Users with the ROS apt source configured can then
   `sudo apt install python3-colcon-live-tools`.
6. Every new version needs its own PyPI release followed by another `bloom-release`
   run — this does not auto-track new PyPI releases.
