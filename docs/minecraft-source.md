# Minecraftのソースとreports

バニラの挙動を推測で決めず、対象版のコードとデータで確かめるための手順。Minecraft: Java Editionのclient jarを公式マッピングの名前でJavaソースに展開し、serverのデータ生成機能が出すreportsと併せて、版ごとにローカルへ置く。

この文書が扱うのは、生成と読み方、主なクラスの入口、根拠としての書き方である。読んで得た結論はここに書き足さず、[保存先と読み方](knowledge-maintenance.md#保存先と読み方) に従って共通イディオムか対象repoのナレッジへ置く。

## 読む場面

共通イディオムや対象repoのナレッジに説明がない挙動、または説明の根拠を確かめたい挙動を扱うときに読む。例えば次の判断である。

- コマンドの構文・解釈・実行。`execute` の分岐や `store` の型変換、`data modify`、selectorの並び順や `dx`、`tp` の相対座標など
- NBT pathの解決、entityやblockが保存するNBTの項目
- tickの中の処理順、ダメージ・Effect・属性の計算
- 描画、フォントと文字幅、モデル、display entityの表示（client側の処理）
- 登録されているID、コマンドの構文木、バニラのloot table・tag・advancement

ソースから分かるのはバニラの処理であり、TheSkyBlessingやAssetのデータパック、TSB-ResourcePackのフォントやモデルによる上書きは含まない。実機で起きることを確かめる必要がある場合は、[機能検証](runtime-verification.md) のシナリオで実測する。

## 生成する

DevSpaceで次を実行する。`<版>` には対象の版を書く。現在の対象は [AGENTS.md](../AGENTS.md#環境変更時の確認) の版（1.20.4）である。

```sh
python3 scripts/minecraft/source.py <版>
```

最後に出力先のパスを表示する。初回はMojangと配布元から取得し、展開とreportsの生成に数分かかる。生成済みの版はネットワークにも接続せず、すぐに終わる。取得するファイル、固定したツールとその版、再実行時の扱いは [スクリプトの冒頭](../scripts/minecraft/source.py) にある。扱えるのは1.18以降の版で、Linux・macOS（DevContainerを含む）で実行する。

生成はゲームのファイルを使うため、サーバーの起動と同じくMinecraft EULAへの同意を求める。`ACCEPT_EULA=true` か `.runtime/eula.txt` の `eula=true` があればよい。生成済みの版を読むだけなら要らない。利用者が同意していない場合、AIは自分で設定せず、利用者に依頼する。

Javaの選び方はスクリプトの冒頭にある。必要なJavaは版によって異なり、1.20.5〜1.21.xは21、26.1以降は25になる。DevContainerにはJava 17しかないため、それより新しい版を生成するには、別にJavaを用意して `--java` で渡す。

## 出力の構成

実行したスクリプトがあるチェックアウトの `.cache/minecraft/` に置く。Git管理外のローカル領域である。DevSpaceのworktreeにあるスクリプトを実行すると、そのworktreeの下へ取得し直すため、共有の生成物を使うときはDevSpace本体のスクリプトを実行するか、`DEVSPACE_ROOT` にDevSpace本体を指定する。

| パス | 内容 |
| --- | --- |
| `<版>/src/` | Javaソースと、client jarの `assets/`（シェーダーを含む）・`data/` |
| `<版>/reports/` | `commands.json`（コマンドの構文木）、`registries.json`（登録ID）、`blocks.json`（ブロックの状態）など |
| `<版>/source.json` | 生成に使った版の定義・ファイル・ツールのハッシュとオプション |
| `downloads/`・`libraries/`・`tools/` | 取得したjarとマッピング、型の解決に使うライブラリ、固定したツール。版をまたいで共有する |

1.20.4では、`1.20.4/` が約120MB、共有の3つが合わせて約90MBになる。server jarは、サーバー用に取得済みの `.cache/server-1.20.4.jar` を使う。不要になった版は `.cache/minecraft/<版>/` ごと消してよく、次に実行したときに作り直される。

ソースはclient jarから作るため、ゲームの処理と描画の両方を含む。1.20.4のclient jarには、専用サーバーのクラス（`net.minecraft.server.dedicated`・`net.minecraft.server.rcon` など）も含まれる。1.20.4で主に読むクラスは次のとおりである。パスは `src/` からの相対パスで、別の版ではクラス名や配置が変わることがある。

| 調べること | クラス |
| --- | --- |
| `execute` の分岐と `store` | `net/minecraft/server/commands/ExecuteCommand.java` |
| `data` コマンド | `net/minecraft/server/commands/data/DataCommands.java` |
| NBT pathの解決と書込み | `net/minecraft/commands/arguments/NbtPathArgument.java` |
| selectorの解析・オプション・選択 | `net/minecraft/commands/arguments/selector/` の `EntitySelectorParser`・`EntitySelector`、`options/EntitySelectorOptions` |
| functionとmacroの展開、functionの呼出し・`execute` の分岐・`return` の実行順 | `net/minecraft/commands/functions/`、`net/minecraft/commands/execution/`、`net/minecraft/server/ServerFunctionManager.java` |
| tickの処理順 | `net/minecraft/server/MinecraftServer.java` の `tickServer`・`tickChildren`、`net/minecraft/server/level/ServerLevel.java` の `tick`。専用サーバーは `net/minecraft/server/dedicated/DedicatedServer.java` の `tickChildren` で、ワールドのtickの後にコンソールの入力を処理する |
| ダメージの計算 | `net/minecraft/world/entity/LivingEntity.java` の `hurt`・`actuallyHurt`、`net/minecraft/world/damagesource/CombatRules.java` |
| 属性 | `net/minecraft/world/entity/ai/attributes/AttributeInstance.java` |
| display entity | `net/minecraft/world/entity/Display.java` |
| 文字幅とテキストの分割 | `net/minecraft/client/gui/Font.java`、`net/minecraft/client/StringSplitter.java` |

それ以外のコマンドは `net/minecraft/server/commands/` にある。多くは `<名前>Command.java` だが、`EffectCommands` のような複数形や、`xp` を登録する `ExperienceCommand` のような例外がある。見つからなければ `grep -rl 'literal("<名前>")' net/minecraft/server/commands` で探す。`LivingEntity.java` のように数千行あるファイルは、先にgrepで位置を探し、行範囲を指定して読む。

デコンパイルした結果なので、元のソースと同じではない。コメントは残らず、定数は値に展開されていることがある。公式マッピングで名前を戻す版（1.21.xまで）では、引数名が `$$0` のような番号になり、局所変数名は型から付けた名前になる。難読化せずに配布される26.1以降では、元の名前が残る。コンパイルできる形であることも保証しない。

## 複数の版を扱う

現行コードについての判断は、対象版（1.20.4）で確かめた結果で行う。ほかの版は、版移行を検討するときの比較に使う。版ごとに別のディレクトリへ生成するため、両方を生成して同じクラスを比べられる。例えば `diff -r .cache/minecraft/1.20.4/src/net/minecraft/server/commands .cache/minecraft/<新しい版>/src/net/minecraft/server/commands` のように、調べる範囲を絞って比べる。名前が変わったクラスは、`reports/` やコマンド名から対応を探す。26.1以降と比べるときは、引数名の違いが多くの宣言に差分として出るため、`diff -r` ではなく、`reports/commands.json` の差分で対象を絞ってから、比べるメソッドを両方の版で開いて読む。マッピングを配布しない版のうち、難読化されていない版はそのまま展開し、難読化されている版は生成を止める。

## 根拠として書くとき

デコンパイルしたコードと公式マッピングは再配布できない。マッピングの先頭には、開発目的での利用は認めるが、そのままの形で再配布してはならないと書かれている。ゲームのファイルの利用は [Minecraft EULA](https://www.minecraft.net/eula) に従う。そのため、生成物をrepoに追加せず、ナレッジ・Issue・PRにもコードを転記しない。取得するツールのVineflowerはApache-2.0、AutoRenamingToolはLGPL-2.1で、各環境で取得するだけで同梱はしない。

根拠は、ノートや文書の本文に「Minecraft 1.20.4 の `net.minecraft.server.commands.ExecuteCommand` の `storeData`」のように、版・クラス・メソッドで書く。次の点を守る。

- `.cache/minecraft/` のパスや行番号は書かない。他の人は開けず、行番号はデコンパイラと設定で変わる。ノートの `related`・`paths` やリンクにも入れない。
- ラムダは、それを含むメソッドの名前で示す。
- 判断に必要な条件や値は、コードを貼らずに文章で説明する。
- どの版で確かめたかを書き、別の版にも当てはまると断定しない。確認範囲には「デコンパイル結果で確認した。実機では確かめていない」のように、実測との区別を書く。
- 配布されたjarそのものを示すときは、Mojangのpiston-dataの公式URLを使う。
