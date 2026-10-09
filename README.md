# colcon-live-tools

[![CI](https://github.com/OEDO-Dynamics/colcon-live-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/OEDO-Dynamics/colcon-live-tools/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/colcon-live-tools.svg)](https://pypi.org/project/colcon-live-tools/)
[![Python versions](https://img.shields.io/pypi/pyversions/colcon-live-tools.svg)](https://pypi.org/project/colcon-live-tools/)
[![License](https://img.shields.io/github/license/OEDO-Dynamics/colcon-live-tools.svg)](LICENSE)

A lightweight, terminal-native, `catkin_tools`-style live build experience for `colcon`.
In the same spirit as `catkin_make` → `catkin build`, this adds a new command,
`colcon lbuild` (short alias: `colcon lb`), in place of `colcon build`.

```bash
colcon lbuild
```

That alone turns on parallel, independent builds (one package failing doesn't stop the
others), a colorized live status board, per-package warning/error counts, and a
build-time table at the end. No flags to remember.

## What this solves

`colcon build` ships two built-in event handlers, `status` (a one-line status bar) and
`summary` (a short summary at the end), but neither shows every package currently
building at once (only as many as fit in the terminal width), and neither prints a
`catkin_tools`-style "build time per package" table. `colcon`'s default behavior is also
to abort unrelated packages as soon as one fails (`catkin_tools` doesn't), and its
default parallelism is capped at `2`. There is a `colcon_core.output_style` extension
point for colorized output, but as of this writing no package implements it, so plain
`colcon build` is effectively colorless.

This package adds three things:

1. **`live_status` event handler** — while the build runs, shows every in-progress
   package on its own line with elapsed time (rows beyond the terminal height collapse
   into `... and N more running`), and at the end prints a per-package build-time table
   (slowest first) plus the tail of the log for each failed package. On a TTY, it's
   colorized (a stable-per-run random color per package name, green/red/yellow for
   OK/FAILED/ABORTED, yellow for warning counts). It's automatically colorless when
   `NO_COLOR` is set or stdout isn't a TTY. It also does a lightweight scan of every
   stdout/stderr line for `warning:`/`error:`/`CMake Warning`/`CMake Error` and tallies
   per-package warning/error counts in both the live rows and the final table (similar
   to `catkin_tools`'s "N warnings" — only the count is shown for packages that still
   succeeded, not the full warning text).
2. **`lbuild` / `lb` verb** — accepts exactly the same arguments as `colcon build`, but
   with different defaults: `live_status` on, `--continue-on-error` on, and
   `--parallel-workers` unlimited (`0`). It also automatically disables whichever other
   handlers that would duplicate or clutter the live view are actually installed
   (`status`/`summary`/`console_start_end`/`console_stderr`/`console_cohesion`/
   `console_direct`/`console_package_list`). `live_status` watches every package's
   stdout/stderr internally regardless of whether those handlers are enabled, so turning
   them off loses no information. Any of these defaults can be overridden by passing the
   corresponding flag explicitly. Help text for this package's own options (only — not
   `colcon build`'s inherited ones) is shown in Japanese, Brazilian Portuguese, or
   English, detected from `LC_ALL`/`LC_MESSAGES`/`LANG`/`LANGUAGE`.
3. **`lclean` / `lc` verb** — a `catkin clean` equivalent. Shows whichever of the
   `build`/`install`/`log` directories actually exist and asks for confirmation before
   removing them, unless `-y`/`--yes` is passed.
4. **`ltest` / `lt` verb** — `colcon test` with the same live board, a readable result
   summary (tests / failures / errors / skipped per package, the failing test cases with
   their messages, and where the JUnit files are), a non-zero exit code on any failure,
   and an isolated `ROS_DOMAIN_ID` for the run.
5. **CI mode** (`lbuild` and `ltest`) — when `--ci` is given or the `CI` /
   `GITHUB_ACTIONS` environment variable is set, the live board is replaced by a stable
   per-package log: GitHub Actions groups, `::error` annotations, and a Markdown summary
   in `$GITHUB_STEP_SUMMARY`. A non-terminal stdout alone does not switch modes, so
   `colcon lb | tee log` prints what 0.1.1 printed.

The only dependency is `colcon-core` — no `rich`, no `curses`.

## Installation

```bash
pip install --user colcon-live-tools
```

or, from a local checkout:

```bash
pip install --user -e /path/to/colcon-live-tools
```

## Usage

### `colcon lbuild` / `colcon lb`

`colcon lbuild` (alias: `colcon lb`) accepts every argument `colcon build` does —
`--packages-select`, `--packages-up-to`, `--cmake-args`, `--symlink-install`,
`--merge-install`, `--build-base`, `--install-base`, and so on all work exactly as they
do with `colcon build`. On top of that, three defaults are changed:

| Option | `colcon build`'s default | `colcon lbuild`'s default |
|---|---|---|
| `--event-handlers` | each handler's own individual default | disables `status`, `summary`, `console_start_end`, `console_stderr`, `console_cohesion`, `console_direct`, `console_package_list` (only the ones actually installed) and enables `live_status+` |
| `--continue-on-error` | off | on — an unrelated package's failure doesn't abort in-flight packages; only packages that (recursively) depend on the failed one are skipped |
| `--parallel-workers` (alias `-j`/`--jobs`) | `2` | `0` (unlimited) |

Any of these can be overridden explicitly, and the explicit value wins:

```bash
colcon lbuild -j 4                                            # cap parallel workers at 4
colcon lbuild --no-continue-on-error                          # restore colcon build's own default: abort everything on the first failure
colcon lbuild --event-handlers status+ summary+ live_status-  # go back to plain colcon build's console output
```

Run `colcon lbuild --help` for the authoritative, full option list — the description
shown for `--event-handlers` and `--parallel-workers` reflects the actual defaults
computed for *your* environment (which handlers get disabled depends on which colcon
extension packages happen to be installed).

The `build`/`install`/`log` directories are shared with `colcon build` (same marker-file
mechanism), so it's fine to mix `colcon build` and `colcon lbuild` in the same workspace.

### `colcon lclean` / `colcon lc`

```bash
colcon lclean                                                 # show build/install/log that exist, ask for confirmation
colcon lclean -y                                               # skip the confirmation (like `catkin clean -y`)
colcon lclean --build-base b2 --install-base i2 --log-base l2  # non-default directory names, same meaning as colcon build's own flags
```

Only removes directories that actually exist; nothing else is touched (no per-package
granularity, no build "profiles" the way `catkin_tools` has).

### `colcon ltest` / `colcon lt`

`colcon lt` (long form `colcon ltest`) accepts every argument `colcon test` does, including
`--packages-select`, `--packages-up-to`, `--retest-until-pass` and `--abort-on-error`.

```bash
colcon lt --packages-select my_pkg               # live board, then a summary
colcon lt --retest-failed                        # only the packages that failed last time
colcon lt --fail-on-skip 'requires hardware'     # a skip whose reason matches counts as a failure
colcon lt --no-isolated-domain --no-user-site    # keep the caller's ROS environment as is
```

| Option | Default | What it does |
|---|---|---|
| exit code | non-zero on any failure | A failing test case makes the run fail even if `colcon test` itself returned 0 (the same as `colcon test --return-code-on-test-failure`, but always on). |
| `--allow-no-tests` | off | In CI mode, a run in which no test case ran ends non-zero (so a mistyped `--packages-select` cannot turn green). This flag allows it. In a terminal the run only prints a warning. |
| `--isolated-domain` / `--no-isolated-domain` | **on** | Picks a random `ROS_DOMAIN_ID` from 1 to 101 (never the current one) whose DDS ports are free on this host, and sets `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`. See below for why. |
| `--no-user-site` | off | Sets `PYTHONNOUSERSITE=1` for the test processes, so packages in `~/.local` cannot shadow the workspace. colcon itself is not affected. |
| `--fail-on-skip PATTERN` | none | Regular expression matched against each skipped test case's skip reason. A match is counted as a failure (repeatable). |
| `--retest-failed` | off | Only tests the packages that failed in the last `ltest` run, recorded in `build/.ltest-last-failed.json`. Combined with `--packages-select` it narrows further. Packages that were not run keep their recorded state. |
| `--ci` | off | Forces CI mode (see below). |

After the run, a summary is printed:

```
Test time summary  (wall time 6.13s, ROS_DOMAIN_ID=217, ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST)
  Package              Tests  Failures  Errors  Skipped  Result
  oedo_response_curve    147         0       0       18  PASS
  oedo_foo                40         1       0        0  FAIL
  total                  187         1       0       18

1 package(s) failed: oedo_foo
----- oedo_foo: failures -----
  FAILED  CurveTest.bad
      Expected: 1
      Which is: 2
      at test/curve_test.cpp:42
      junit: .../build/oedo_foo/test_results/oedo_foo/gtest.xml
```

The JUnit files are read from `build/<package>/` (or `--test-result-base`), and only files
written by this run are counted, so results left over from an earlier run do not show up.
A package with no JUnit file and exit code 0 is reported as `NO JUNIT`, not as a failure.

**Why the isolated domain is on by default, and why 1 to 101.** On a machine where the same LAN also has
live robot nodes, a test that publishes or subscribes on the default domain can talk to
them. Picking a free domain and keeping discovery on loopback stops test traffic from
leaving the process group that colcon started. Use `--no-isolated-domain` when a test
really needs to reach another machine, or in an environment you fully control. The domain
choice is a heuristic: it sees DDS ports bound on this host, not participants on other
machines (which loopback discovery does not reach anyway). Domain 0 is the default domain
that the isolation is meant to avoid. Above 101 the DDS ports reach the Linux ephemeral
port range (32768–60999), where a clash fails at random, so the candidates are 1 to 101
(the range ROS 2 recommends on Linux).

**What `--no-user-site` does and does not do.** It sets the variable in the environment
of the whole `colcon test` run, so every Python child process started by a test (not only
`pytest`) runs without the user site-packages. There is no way to narrow it to `pytest`
alone. The `colcon` process itself is already running and is not affected.

### CI mode (GitHub Actions and other CI)

CI mode is chosen per run and applies to `colcon lbuild`/`lb` and `colcon ltest`/`lt`. It is on
when `--ci` is passed, or when `CI` or `GITHUB_ACTIONS` is set to a value other than
`0`/`false`/`no`/`off` (GitHub Actions sets `GITHUB_ACTIONS` for you). Output piped to a
file without these settings is the same as in earlier releases.

In CI mode there is no cursor movement. Each package's output is printed as one block when
its job ends (so parallel packages never interleave), preceded by `Starting >>> <pkg>` and
followed by `Finished <<< <pkg> [time]` or `Failed <<< <pkg> ...`. On GitHub Actions:

- each block is a `::group::` (collapsed in the log),
- a failed package gets an `::error` annotation, with `file=`/`line=` when a compiler
  diagnostic was seen,
- a failing test case gets an `::error` annotation with its file and line when JUnit
  provides them,
- the summary is appended to `$GITHUB_STEP_SUMMARY` as Markdown tables.

Outside GitHub Actions the groups and annotations are replaced by plain
`===== <pkg>: OK ... =====` lines, and no workflow commands are printed.

A workflow example:

```yaml
name: CI
on: [push, pull_request]
jobs:
  build-and-test:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - name: Install ROS 2 and colcon
        run: |
          # install ROS 2 Jazzy and colcon-common-extensions as your project already does
          python3 -m pip install --break-system-packages colcon-live-tools
      - name: Build
        run: |
          source /opt/ros/jazzy/setup.bash
          colcon lb --packages-select my_pkg
      - name: Test
        run: |
          source /opt/ros/jazzy/setup.bash
          colcon lt --packages-select my_pkg --fail-on-skip 'requires hardware'
```

`colcon lt` exits non-zero when a test fails, so the step fails without further configuration.

### Trying it out without touching your own workspace

```bash
examples/run_demo.sh
```

Builds four dummy CMake packages under `examples/demo_ws` (three succeed at different
speeds, one fails on purpose) with `colcon lbuild`, so you can see the live board and
the final report end-to-end. Needs `colcon-core` + `colcon-cmake` (and this package)
installed, plus `cmake` on `PATH` — no ROS install required.

### Using the event handler without the verb

If you'd rather not switch an existing build script over to the `lbuild`/`lb` verb, the
`live_status` event handler can be turned on directly on plain `colcon build`:

```bash
colcon build --event-handlers status- summary- console_start_end- console_stderr- \
    console_direct- live_status+ --continue-on-error --parallel-workers 0
```

(exactly which handlers are worth disabling depends on which ones your environment
actually has installed; the default `--event-handlers` value `colcon lbuild --help`
reports for your environment is a reliable reference.)

### Non-TTY environments (CI, output redirected to a file)

CI mode is described above. The final table and the failure tails are printed in every mode,
and are plain text when not on a terminal. Output to a pipe or a log file is unchanged unless
CI mode is requested.

## Reading the output

While building:

```
[12.3s] 4/9 done  3 running  1 failed
  ▸ oedo_controller_edge              8.1s   45%
  ▸ oedo_can_bridge                   3.4s
  ▸ oedo_lidar_filter                 0.9s
```

At the end (colorized on a TTY; the `WARN` column is omitted entirely if there are no
warnings/errors at all):

```
Build time summary  (wall time 14.02s)
  OK      oedo_bringup                   12.41s
  FAILED  oedo_controller_edge            8.10s  1e
  OK      oedo_can_bridge                 3.40s  2w
  OK      oedo_lidar_filter                0.90s

3 finished, 1 failed, 0 aborted, 0 skipped

----- oedo_controller_edge: last output -----
  [stderr] error: 'foo' was not declared in this scope
  [stderr] make[2]: *** [CMakeFiles/oedo_controller_edge.dir/build.make:76: ...] Error 1
```

(`2w`/`1e` means "2 warnings, 1 error" — only the count is shown; full warning text for
packages that still succeeded is left in that package's own log file under `log/`.)

## Verifying each package really builds independently

`colcon-live-tools`/`lbuild` doesn't touch `colcon build`'s parallel execution or
dependency resolution at all — only event handlers and default values change. With that
said, here's what was actually verified by building colcon itself with it:

- **Build/install isolation**: like `catkin_make_isolated`/`catkin build` (not
  `catkin_make`, which lumps every package into one CMake run), `build/<package>/` and
  `install/<package>/` are fully separated per package. A dependency's actually-installed
  artifacts (library, headers, CMake config files) are found via `find_package()` by
  whatever depends on it, linked, and confirmed to work, on real hardware builds.
- **Dependency ordering and skipping**: for `ament_cmake`/`ament_python` (what ROS 2
  packages normally use), build order follows `package.xml`'s `<depend>` tags correctly,
  and with `--continue-on-error` on, a package whose dependency failed is correctly
  `SKIP`ped (unrelated packages keep building in parallel). Confirmed by reproducing this
  directly. **Requires the `colcon-ros` package** (normally pulled in by
  `colcon-common-extensions`; `pip show colcon-ros` to double check).
- **Caveat (shouldn't affect normal ROS 2 setups)**: if a package's `package.xml`
  `<export><build_type>` is plain `cmake` (not `ament_cmake`/`ament_python`), colcon
  doesn't read `<depend>` at all — it infers dependencies by scanning
  `CMakeLists.txt`'s `find_package()`/`pkg_check_modules()` calls instead. This is
  colcon's own behavior, unrelated to `colcon-live-tools`. So a dependency declared in
  `package.xml` but not actually `find_package()`d in CMake won't be ordered or skipped
  correctly. Reproduced directly with a synthetic test. A normal ROS 2 workspace
  (`ament_cmake`/`ament_python` packages) shouldn't hit this, but it's worth knowing if
  you mix in plain-`cmake`-type packages.

To check your own workspace's dependency graph (no build performed):

```bash
python3 -c "
from colcon_core.package_discovery import discover_packages, add_package_discovery_arguments
from colcon_core.package_identification import get_package_identification_extensions
import argparse
parser = argparse.ArgumentParser()
add_package_discovery_arguments(parser)
args = parser.parse_args(['--base-paths', 'src'])
for pkg in sorted(discover_packages(args, get_package_identification_extensions()), key=lambda p: p.name):
    print(pkg.name, pkg.type, dict(pkg.dependencies))
"
```

## Implementation note: not clobbering other handlers' output

While a build runs, other enabled event handlers (`console_start_end`,
`console_stderr`, ...) also write to stdout/stderr. A naive "move the cursor up N lines
and clear" redraw would erase those lines if they land between two of our redraws
(this actually happened — a `Failed <<< pkg_fail ...` line was found to get erased this
way, and has since been fixed). To avoid it, `sys.stdout`/`sys.stderr`'s `write` is
hooked the same way colcon-core's own `status` handler does for its single status line:
wherever a write comes from, the live region is cleared first, then the real write
happens, then the live region is redrawn on top (see `_ScreenWriter` in
`live_status.py`).

## License

Apache License 2.0. See [LICENSE](LICENSE).

---

# colcon-live-tools (日本語)

`catkin_tools` 風の、軽量・ターミナルネイティブな colcon ビルド体験。
`catkin_make` → `catkin build` の変化と同じ発想で、`colcon build` の代わりに
`colcon lbuild`（短縮形 `colcon lb`）という新しいコマンドを追加する。

```bash
colcon lbuild
```

これだけで、並列・独立ビルド（1パッケージ失敗しても他は続行）＋色付きライブ状況表示＋
警告/エラー数の集計＋ビルド時間テーブルが有効になる。フラグを並べる必要はない。

## これは何を解決するか

`colcon build` には標準で `status`（1行のステータスバー）と `summary`（終了時の簡易サマリ）という
イベントハンドラが入っているが、同時ビルド中の全パッケージを見せることはできず（ターミナル幅に収まる分だけ）、
`catkin_tools` にあったような「パッケージ別のビルド時間テーブル」も出力しない。また colcon のデフォルトは
1パッケージが失敗すると無関係な他パッケージも中断してしまう（`catkin_tools` は違う）し、
デフォルトの並列数も `2` に制限されている。色付け用の `colcon_core.output_style` という拡張点も
あるが、これを書いている時点でそれを実装したパッケージは存在せず、素の `colcon build` は事実上
無色のままになっている。

このパッケージは3つのものを追加する:

1. **`live_status` イベントハンドラ** -- ビルド中は実行中の全パッケージを1行ずつ経過時間つきで表示し
   （ターミナル行数を超える分は `... and N more running` にまとめる）、終了時にパッケージ別の
   ビルド時間テーブル（遅い順）と失敗パッケージごとの末尾ログを表示する。TTYであれば色付け
   （パッケージ名はビルド1回ごとに安定した色をランダムに割り当て、OK/FAILED/ABORTは緑/赤/黄、
   警告数は黄）もする。`NO_COLOR` 環境変数か非TTYでは自動的に無色になる。
   さらに、標準出力/標準エラーの各行を `warning:`/`error:`/`CMake Warning`/`CMake Error` で
   簡易スキャンし、パッケージごとの警告/エラー数を集計してライブ行と最終テーブルに出す
   （`catkin_tools` の「N warnings」表示に近い。成功したパッケージの警告本文までは出さず、件数のみ）。
2. **`lbuild` / `lb` コマンド（colcon の verb）** -- `colcon build` と全く同じ引数を受け付けるが、
   デフォルトだけが違う: `live_status` が有効、`--continue-on-error` が有効、`--parallel-workers` が
   無制限（`0`）、かつ `live_status` と表示が重複する/ターミナルを賑やかにする他のハンドラ
   （`status`/`summary`/`console_start_end`/`console_stderr`/`console_cohesion`/`console_direct`/
   `console_package_list` のうち実際に入っているもの）を自動的に無効化する。`live_status` は
   有効・無効に関わらず全パッケージの標準出力/標準エラーを内部で見ているので、これらを切っても
   情報は失われない。明示的にフラグを渡せばいつでも上書きできる。`--help` の説明文は
   `LC_ALL`/`LC_MESSAGES`/`LANG`/`LANGUAGE` から判定した言語（日本語・ポルトガル語・英語、
   それ以外は英語にフォールバック）で表示される（このパッケージ自身が追加・上書きする
   引数の説明のみ。`colcon build` 本来の引数の説明は英語のまま）。
3. **`lclean` / `lc` コマンド（colcon の verb）** -- `catkin clean` 相当。`build`/`install`/`log`
   ディレクトリのうち実際に存在するものだけを表示し、`-y`/`--yes` を渡さない限り削除前に確認を求める。
4. **`ltest` / `lt` コマンド（colcon の verb）** -- `colcon test` にパッケージごとのライブ表示を付け、
   見やすい結果要約（パッケージごとの tests/failures/errors/skipped、失敗したテストケースとメッセージ、
   junit の場所）を出す。失敗があれば非0で終了し、実行ごとに ROS_DOMAIN_ID を分離する。
5. **CI モード**（`lbuild` と `ltest`） -- `--ci` を渡した場合、または `CI`/`GITHUB_ACTIONS`
   環境変数が設定されている場合、ライブ表示をやめてパッケージごとの安定したログにする（GitHub Actions の
   グループと `::error` 注記、`$GITHUB_STEP_SUMMARY` への Markdown 要約）。標準出力が端末でないだけでは
   切り替わらないので、`colcon lb | tee log` の出力は 0.1.1 と同じになる。

依存は `colcon-core` のみ。`rich` や `curses` などは使わない。

## インストール

```bash
pip install --user colcon-live-tools
```

もしくはローカルのチェックアウトから:

```bash
pip install --user -e /path/to/colcon-live-tools
```

## 使い方

### `colcon lbuild` / `colcon lb`

`colcon lbuild`（別名 `colcon lb`）は `colcon build` が受け付ける引数をすべてそのまま
受け付ける -- `--packages-select`、`--packages-up-to`、`--cmake-args`、
`--symlink-install`、`--merge-install`、`--build-base`、`--install-base` などは
`colcon build` と全く同じ動作をする。そのうえで、以下の3つのデフォルト値だけが変わる:

| オプション | `colcon build` 本来のデフォルト | `colcon lbuild` のデフォルト |
|---|---|---|
| `--event-handlers` | 各ハンドラごとの個別のデフォルト | `status`・`summary`・`console_start_end`・`console_stderr`・`console_cohesion`・`console_direct`・`console_package_list`（実際にインストールされているものだけ）を無効化し、`live_status+` を有効化 |
| `--continue-on-error` | 無効 | 有効 -- 無関係なパッケージが失敗しても進行中のパッケージは中断されず、失敗したパッケージに（再帰的に）依存するパッケージだけがスキップされる |
| `--parallel-workers`（別名 `-j`/`--jobs`） | `2` | `0`（無制限） |

これらは個別に明示的なフラグで上書きでき、その場合は明示的な値が優先される:

```bash
colcon lbuild -j 4                                            # 並列数を4に制限
colcon lbuild --no-continue-on-error                          # colcon build 本来のデフォルトに戻す: 1つ失敗したら他も中断
colcon lbuild --event-handlers status+ summary+ live_status-  # ライブ表示を切って元の colcon build の表示に戻す
```

正確な全オプション一覧は `colcon lbuild --help` を参照（`--event-handlers` と
`--parallel-workers` の説明文には、実行環境ごとに実際に計算されたデフォルト値が
表示される -- どのハンドラが無効化されるかは、その環境にどの colcon 拡張パッケージが
入っているかによって変わる）。

`build`/`install`/`log` ディレクトリは `colcon build` と共有される（マーカーファイルの仕組み上、
同じワークスペースで `colcon build` と `colcon lbuild` を混在させても問題ない）。

### `colcon lclean` / `colcon lc`

```bash
colcon lclean                                                 # build/install/log のうち実在するものを表示し、確認
colcon lclean -y                                               # 確認なしで削除（catkin clean -y 相当）
colcon lclean --build-base b2 --install-base i2 --log-base l2  # ディレクトリ名を変える場合。colcon build 本来の同名フラグと同じ意味
```

実在するディレクトリだけを削除する（パッケージ単位の削除や、`catkin_tools` にあるような
ビルドプロファイルの概念はない）。

### `colcon ltest` / `colcon lt`

`colcon lt`（正式名 `colcon ltest`）は `colcon test` が受け付ける引数をすべて受け付ける
（`--packages-select`、`--packages-up-to`、`--retest-until-pass`、`--abort-on-error` など）。

```bash
colcon lt --packages-select my_pkg               # ライブ表示のあと要約を出す
colcon lt --retest-failed                        # 前回失敗したパッケージだけ回す
colcon lt --fail-on-skip 'requires hardware'     # スキップ理由が一致したものを失敗扱い
colcon lt --no-isolated-domain --no-user-site    # 呼び出し元の ROS 環境のまま実行
```

| オプション | 既定 | 働き |
|---|---|---|
| 終了コード | 失敗があれば非0 | `colcon test` 自体が 0 を返しても、失敗したテストケースがあれば非0（`--return-code-on-test-failure` と同じだが常に有効） |
| `--allow-no-tests` | 無効 | CI モードで試験ケースが1件も実行されなかった場合に非0で終わる（打ち間違えた `--packages-select` で緑にならないため）。このフラグで許可する。端末では警告のみ |
| `--isolated-domain` / `--no-isolated-domain` | **有効** | この機で DDS ポートの空いている乱数の `ROS_DOMAIN_ID`（1〜101、現在の値は除く）を選び、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST` を設定する。理由は後述 |
| `--no-user-site` | 無効 | テストのプロセスに `PYTHONNOUSERSITE=1` を渡し、`~/.local` のパッケージがワークスペースを隠さないようにする。colcon 本体には影響しない |
| `--fail-on-skip PATTERN` | なし | スキップされたテストケースの理由に対する正規表現。一致したものは失敗として数える（複数指定可） |
| `--retest-failed` | 無効 | 前回の `ltest` 実行で失敗したパッケージだけを回す（`build/.ltest-last-failed.json` に記録）。`--packages-select` と併用すると両方で絞り込む。今回実行されなかったパッケージの記録は残す |
| `--ci` | 無効 | CI モードを強制する（後述） |

実行後は次のような要約を出す（上の英語版と同じ形式）。junit は `build/<パッケージ>/`（または
`--test-result-base`）から読み、今回の実行で書かれたファイルだけを数えるので、以前の結果が混ざらない。
junit が無く終了コードが 0 のパッケージは失敗ではなく `NO JUNIT` と表示する。

**分離ドメインを既定で有効にする理由と、候補を 1〜101 にする理由。** 同じ LAN に実機の ROS ノードがいる環境では、既定ドメインで
publish/subscribe する試験が実機と混線しうる（建機の制御系では危険）。空いている乱数のドメインを選び、
検出を loopback に限ることで、試験の通信が colcon を起動した側の外へ出ないようにする。試験が本当に
別マシンへ届く必要がある場合や、完全に管理された環境では `--no-isolated-domain` を使う。ドメインの
空き判定は「この機で DDS ポートが塞がっていないか」のヒューリスティックで、別マシンの参加者は見えない
（そもそも loopback の検出では届かない）。ドメイン 0 は分離したい既定ドメインそのもの。101 より上では
DDS ポートが Linux のエフェメラルポート範囲（32768〜60999）に入り、衝突すると不定期に失敗するため、
候補は ROS 2 が Linux で推奨する 1〜101 に限る。

**`--no-user-site` の効く範囲。** 変数は `colcon test` 全体の環境に設定されるため、試験が起動する Python の
子プロセス（`pytest` だけでなくすべて）が ユーザー site-packages なしで動く。`pytest` だけに絞る手段は無い。
すでに動いている `colcon` プロセス本体には影響しない。

### CI モード（GitHub Actions など）

CI モードは実行ごとに決まり、`colcon lbuild`/`lb` と `colcon ltest`/`lt` の両方に効く:

- `--ci` を渡した場合、または `CI` か `GITHUB_ACTIONS` が `0`/`false`/`no`/`off` 以外に設定されている場合
  （GitHub Actions は `GITHUB_ACTIONS` を自動で設定する）。
- 上記のどれでもない場合（パイプ、ログファイル）は、0.1.1 と同じ出力になる。

CI モードではカーソル移動をしない。各パッケージの出力は、そのジョブが終わった時点で 1 ブロックとして
出す（並列のパッケージ同士が混ざらない）。前に `Starting >>> <パッケージ>`、後ろに
`Finished <<< <パッケージ> [時間]` または `Failed <<< ...` を付ける。GitHub Actions では:

- 各ブロックは `::group::`（ログ上で折りたたまれる）、
- 失敗したパッケージには `::error` 注記（コンパイラの診断を見ていれば `file=`/`line=` 付き）、
- junit が行番号を持つ失敗したテストケースには、そのファイルと行の `::error` 注記、
- 要約を Markdown の表で `$GITHUB_STEP_SUMMARY` に追記する。

GitHub Actions 以外では、グループと注記の代わりに `===== <パッケージ>: OK ... =====` の行を出し、
ワークフローコマンドは出さない。

ワークフローの例は上の英語版を参照（`colcon lb` でビルド、`colcon lt --fail-on-skip '...'` で試験。
`colcon lt` は失敗があると非0で終わるので、追加の設定なしでステップが失敗する）。

### 自分のワークスペースを使わずに試す

```bash
examples/run_demo.sh
```

`examples/demo_ws` 以下にある4つのダミー CMake パッケージ（3つは異なる速度で成功、
1つはわざと失敗）を `colcon lbuild` でビルドし、ライブ表示と最終レポートを
一通り確認できる。`colcon-core` + `colcon-cmake`（とこのパッケージ）と、
`cmake` コマンドが `PATH` にあればよい。ROS のインストールは不要。

### verb を使わず素の `colcon build` にイベントハンドラだけ足したい場合

`lbuild`/`lb` verb を使わず、既存のスクリプトに手を加えたくない場合は、イベントハンドラだけ
明示的に有効化することもできる（無効化すべきハンドラは環境によって入っているものが違うので、
`colcon lbuild --help` の `--event-handlers` の説明に出るデフォルト値をその環境の実際の値として
参考にするのが確実）:

```bash
colcon build --event-handlers status- summary- console_start_end- console_stderr- \
    console_direct- live_status+ --continue-on-error --parallel-workers 0
```

### 非TTY環境（CI・ログファイル出力など）

CI モードは上のとおり。終了時のテーブルと失敗ログの末尾はどのモードでも出力され、端末でない場合は
プレーンテキストになる。CI モードを要求しない限り、パイプやログファイルへの出力は変わらない。

## 出力の読み方

ビルド中:

```
[12.3s] 4/9 done  3 running  1 failed
  ▸ oedo_controller_edge              8.1s   45%
  ▸ oedo_can_bridge                   3.4s
  ▸ oedo_lidar_filter                 0.9s
```

終了時（TTY では色付き。`WARN` 欄は警告/エラーが1件もなければ列自体が出ない）:

```
Build time summary  (wall time 14.02s)
  OK      oedo_bringup                   12.41s
  FAILED  oedo_controller_edge            8.10s  1e
  OK      oedo_can_bridge                 3.40s  2w
  OK      oedo_lidar_filter                0.90s

3 finished, 1 failed, 0 aborted, 0 skipped

----- oedo_controller_edge: last output -----
  [stderr] error: 'foo' was not declared in this scope
  [stderr] make[2]: *** [CMakeFiles/oedo_controller_edge.dir/build.make:76: ...] Error 1
```

（`2w`/`1e` は「警告2件」「エラー1件」。件数だけを表示し、成功したパッケージの警告本文は
出さない -- 必要なら `log/` 以下の該当パッケージのログファイルに全文が残っている。）

## 各パッケージが本当に独立してビルドされているか（検証結果）

`colcon-live-tools`/`lbuild` は `colcon build` の並列実行・依存関係解決そのものには一切手を
加えていない（イベントハンドラとデフォルト値の変更だけ）。そのうえで、この colcon 自体の挙動を
実際にビルドさせて検証した結果:

- **ビルド/インストールの分離**: `catkin_make`（全パッケージを1つの CMake 実行にまとめる）ではなく
  `catkin_make_isolated`/`catkin build` と同じで、`build/<パッケージ名>/`・`install/<パッケージ名>/`
  がパッケージごとに完全に分かれる。依存パッケージが実際にインストールした成果物（ライブラリ・
  ヘッダ・CMake configファイル）を、依存する側が `find_package()` 経由で見つけて実際にリンクし、
  正しく動作することを実機ビルドで確認済み。
- **依存順序とスキップ**: `ament_cmake`/`ament_python`（= ROS 2 パッケージが通常使うタイプ）では、
  `package.xml` の `<depend>` に基づいて正しくビルド順序が決まり、`--continue-on-error` 有効時は
  依存先が失敗したパッケージが正しく `SKIP` される（依存していない無関係なパッケージは並行して
  ビルドが続く）ことを実際に再現・確認済み。ただし **これには `colcon-ros` パッケージが必要**
  （`colcon-common-extensions` の依存関係に含まれるので、`pip install colcon-common-extensions`
  していれば通常は入っているはずだが、`pip show colcon-ros` で確認しておくと安心）。
- **注意点（ROS 2 の通常構成では影響しないはず）**: `package.xml` の `<export><build_type>` が
  素の `cmake`（`ament_cmake`/`ament_python` ではない）の場合、colcon は `<depend>` タグを見ておらず、
  `CMakeLists.txt` 内の `find_package()`/`pkg_check_modules()` 呼び出しをスキャンして依存関係を
  推測している（これは colcon 自体の仕様で、`colcon-live-tools` とは無関係）。そのため
  「`package.xml` には書いたが CMake 側で `find_package()` していない」依存は順序付け・スキップの
  対象にならない。手元の合成テストで実際に再現した。通常の ROS 2 パッケージ（`ament_cmake`/
  `ament_python`）ではまず該当しないが、素の `cmake` 型のパッケージを混在させる場合は
  覚えておくとよい。

自分のワークスペースで確認したい場合は、以下を実行すると（ビルドはせず）各パッケージの
依存関係グラフだけを確認できる:

```bash
python3 -c "
from colcon_core.package_discovery import discover_packages, add_package_discovery_arguments
from colcon_core.package_identification import get_package_identification_extensions
import argparse
parser = argparse.ArgumentParser()
add_package_discovery_arguments(parser)
args = parser.parse_args(['--base-paths', 'src'])
for pkg in sorted(discover_packages(args, get_package_identification_extensions()), key=lambda p: p.name):
    print(pkg.name, pkg.type, dict(pkg.dependencies))
"
```

## 実装メモ: 他のハンドラの出力を壊さないための工夫

ビルド中、`console_start_end` や `console_stderr` など他の有効なイベントハンドラも同時に
標準出力/標準エラーに書き込む。素朴に「カーソルをN行上げて消してから再描画」を実装すると、
再描画の合間に他のハンドラが行を書き込んだ場合にその行を誤って消してしまう（実際にこれで
`Failed <<< pkg_fail ...` の行が消えるバグを発見し、修正済み）。これを避けるため、
`sys.stdout`/`sys.stderr` の `write` を colcon 標準の `status` ハンドラと同じ手法でフックし、
どこから書き込まれてもライブ表示領域を書き込み前に必ず消してから本来の書き込みを行う、
という方式にしている（`live_status.py` 内の `_ScreenWriter`）。

## ライセンス

Apache License 2.0。[LICENSE](LICENSE) を参照。
