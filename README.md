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

When `sys.stdout.isatty()` is false, no live redraw happens (redrawing a log file has no
effect). One-line `Starting >>> pkg` / `Finished <<< pkg [1.23s]` logging still comes
from colcon's own `console_start_end` handler (on by default) as usual, so
`live_status` doesn't duplicate it. The final build-time table and failure tails are
always printed — TTY or not, colored or not.

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

`sys.stdout.isatty()` が False の場合、ライブ描画は行わない（ログファイルに描画しても意味がないため）。
`Starting >>> pkg` / `Finished <<< pkg [1.23s]` のような1行ログは、有効になっている
`console_start_end` ハンドラ（colcon 標準、デフォルト有効）がそのまま出力するので、
`live_status` 側で重複して出すことはしない。ビルド終了時のテーブルと失敗ログの末尾は
TTY かどうかに関わらず常に出力される。

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
