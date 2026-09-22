# colcon-live-tools

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
pip install --user -e /path/to/colcon-live-tools
# もしくは公開後は
pip install --user colcon-live-tools
```

## 使い方

```bash
colcon lbuild          # これで十分
colcon lb               # さらに短い別名（同じ動作）
```

上書きしたいときだけフラグを渡す:

```bash
colcon lbuild -j 4                     # 並列数を4に制限（デフォルトは無制限）
colcon lbuild --no-continue-on-error    # 1つ失敗したら他も中断する、colcon build 本来の挙動に戻す
colcon lbuild --event-handlers status+ summary+ live_status-   # ライブ表示を切って元の colcon build の表示に戻す
```

それ以外（`--packages-select`、`--cmake-args`、`--symlink-install` など）は `colcon build` と
まったく同じ引数がそのまま使える。`colcon lbuild --help` で全オプションを確認できる。

`build`/`install`/`log` ディレクトリは `colcon build` と共有される（マーカーファイルの仕組み上、
同じワークスペースで `colcon build` と `colcon lbuild` を混在させても問題ない）。

ワークスペースを掃除したいときは:

```bash
colcon lclean          # build/install/log のうち実在するものを表示し、確認してから削除
colcon lc -y            # 確認なしで削除（catkin clean -y 相当）
```

### verb を使わず素の `colcon build` にイベントハンドラだけ足したい場合

`lbuild`/`lb` verb を使わず、既存のスクリプトに手を加えたくない場合は、イベントハンドラだけ
明示的に有効化することもできる（無効化すべきハンドラは環境によって入っているものが違うので、
`colcon lbuild --help` の `--event-handlers` の説明に出るデフォルト値をその環境の実際の値として
参考にするのが確実):

```bash
colcon build --event-handlers status- summary- console_start_end- console_stderr- \
    console_direct- live_status+ --continue-on-error --parallel-workers 0
```

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

## 非TTY環境（CI・ログファイル出力など）

`sys.stdout.isatty()` が False の場合、ライブ描画は行わない（ログファイルに描画しても意味がないため）。
`Starting >>> pkg` / `Finished <<< pkg [1.23s]` のような1行ログは、有効になっている
`console_start_end` ハンドラ（colcon 標準、デフォルト有効）がそのまま出力するので、
`live_status` 側で重複して出すことはしない。ビルド終了時のテーブルと失敗ログの末尾は
TTY かどうかに関わらず常に出力される。

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
  対象にならない。手元の合成テストで実際に再現した。OEDO のワークスペースは通常の ROS 2
  パッケージ（`ament_cmake`/`ament_python`）のはずなので通常は該当しないが、素の `cmake` 型の
  パッケージを混在させる場合は覚えておくとよい。

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

## OSS として配布する (pip/PyPI・apt)

このパッケージは今のところローカルの `pip install -e .` でしか入れられないが、
配布できるように準備してある。**pip (PyPI)** と **apt** の両方とも可能で、性質が大きく違う。

### pip / PyPI -- 自分の裁量で今すぐ進められる

`colcon-core` 自身や `colcon-common-extensions` などの colcon 拡張パッケージ群は、
主に PyPI (pip) で配布されている。このパッケージも同じ形にできる状態になっている:

- `pyproject.toml`（ビルドバックエンド指定）と `setup.cfg`（メタデータ・エントリポイント）は
  すでにある。今回、`classifiers`・`keywords`・`python_requires`・`project_urls` などを追加し、
  クリーンな venv で `python -m build` → できた wheel を別の venv に入れて
  `colcon lb`/`colcon lc` が登録されることまで確認済み。
- パッケージ名 `colcon-live-tools` は 2026-09-23 時点で PyPI 未登録（空き）を確認済み。
- `MANIFEST.in`・`CHANGELOG.rst`・GitHub Actions の CI（`.github/workflows/ci.yml`、
  flake8 + ビルド + verb 登録の smoke test を Python 3.8/3.10/3.12 で実行）を追加した。

**公開前に必ず自分で決めて `setup.cfg` を直してほしい2箇所**（`TODO` コメントを入れてある）:

- `author_email` -- 個人のメールアドレスをそのまま公開して良いか確認してから記入
- `url`/`project_urls` -- 実際に使う GitHub リポジトリの URL に差し替え（今は仮のURL）

公開手順:

```bash
python -m pip install --upgrade build twine
python -m build                       # dist/*.tar.gz と dist/*.whl ができる
python -m twine upload --repository testpypi dist/*   # 先にTestPyPIで試すと安全
python -m twine upload dist/*                          # 本番のPyPIへ
```

（PyPI・TestPyPI それぞれでアカウント登録と API トークン発行が必要。トークンは
`~/.pypirc` か `TWINE_PASSWORD` 環境変数で渡す。）公開後は誰でも

```bash
pip install --user --break-system-packages colcon-live-tools
```

で入るようになる。バージョンを上げて再公開したいときは、同じバージョン番号は
二度と使えない（PyPIは上書き不可）ので、`colcon_live_tools/__init__.py` の
`__version__` と `CHANGELOG.rst` を先に更新してから同じ手順を繰り返す。

### apt -- ROS公式のapt配信網に乗せる、より大掛かりな取り組み

実は `python3-colcon-common-extensions` のように ROS の apt リポジトリ
(`packages.ros.org`) 経由でも colcon 拡張パッケージは配られている。これは
個人の PPA ではなく、**ROSのビルドファーム**が作っている。この配信網に乗るには
`bloom` というツールと `ros/rosdistro` への登録が必要で、PyPI公開よりもずっと
時間がかかり、自分の裁量だけでは完結しない（ROS側のメンテナのレビュー待ちが入る）。
概要:

1. 前提として、まず上記の PyPI 公開を先に済ませておく（`bloom` はここから拾う）。
2. `pip install -U bloom` で bloom を導入する。
3. `bloom` には ROS パッケージ（ament/catkin）専用の他に、素の pip パッケージ用の
   **`pip` リリーストラック**がある（まさに colcon 自身の拡張パッケージ群がこの
   トラックで配布されている）。これを使ってリリース用リポジトリを用意し、
   `bloom-release --track pip --rosdistro <いずれかの現行distro名> colcon-live-tools`
   のように実行すると、PyPI上のソース配布物から Debian パッケージング一式
   （`python3-colcon-live-tools` という名前になるはず）を自動生成してくれる。
4. `bloom-release` は最後に `ros/rosdistro` への Pull Request 作成を促す。
   ここは ROS 側のメンテナによるレビュー・マージ待ちになる（早くて数日、
   場合によっては数週間かかる。判断に迷ったら ROS Discourse の
   Release カテゴリで質問するのが確実）。
5. マージされると ROS のビルドファームが対応プラットフォーム向けに `.deb` を
   自動ビルドし、`packages.ros.org` に配置される。以降はユーザー側で ROS の
   apt ソースを設定していれば `sudo apt install python3-colcon-live-tools`
   で入るようになる。
6. 新バージョンを出すたびに、PyPI側のバージョンを上げてから
   `bloom-release` をもう一度実行する必要がある（自動追従はしない）。

つまり pip/PyPI は完全に自分の裁量で今日中にでも進められるが、apt (ROS公式配信網)
は ROS コミュニティ側の承認プロセスに乗る必要があり、継続的なメンテナンス
コミットメントも増える。まずは PyPI で公開して実際に使ってもらい、
需要が見えてから apt (bloom/rosdistro) に進むのが現実的だと思う。

（個人の PPA (Launchpad) を使う手もあるが、ROSのドキュメントが案内する
`python3-colcon-*` という名前にはならず、ROSのapt利用者に自動的には届かないので、
bloom の経路がある以上あまり優先度は高くない。）

## 実装メモ: 他のハンドラの出力を壊さないための工夫

ビルド中、`console_start_end` や `console_stderr` など他の有効なイベントハンドラも同時に
標準出力/標準エラーに書き込む。素朴に「カーソルをN行上げて消してから再描画」を実装すると、
再描画の合間に他のハンドラが行を書き込んだ場合にその行を誤って消してしまう（実際にこれで
`Failed <<< pkg_fail ...` の行が消えるバグを発見し、修正済み）。これを避けるため、
`sys.stdout`/`sys.stderr` の `write` を colcon 標準の `status` ハンドラと同じ手法でフックし、
どこから書き込まれてもライブ表示領域を書き込み前に必ず消してから本来の書き込みを行う、
という方式にしている（`live_status.py` 内の `_ScreenWriter`）。
