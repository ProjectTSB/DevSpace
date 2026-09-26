# 再実行できる機能検証

実サーバーで確認する機能は、入力・前提・期待値を対象repoのJSONシナリオに置く。DevSpaceの共通runnerが使い捨てworld、Minecraft 1.20.4、プロトコルクライアント、結果保存と終了処理を担当する。

```sh
# DevSpaceルートで実行。絶対パスも使える。
sh scripts/verify.sh Asset/tests/scenarios/dual-rhythm.json
```

現在の対応環境はLinux / DevContainer。Python 3、Node.js、npm、Java 17、通常環境でのEULA同意設定が必要。通常のsetupで取得したrepoと、ローカル設定の参照先を使う。world指定は引き継がず、新規worldを `.runtime/verification-runs/run-*/.runtime/world` に作る。通常worldを置換・コピー・編集しない。検証は同時に1件とし、OSのファイルロックでrunnerと依存インストールを直列化する。

既定の最大ヒープは4GB。接続先はloopback、MinecraftとRCONのポートは実行ごとに選ぶ。確保と起動の間に別プロセスがポートを使った場合は起動失敗として記録される。認証なしのテストクライアントとRCONはこの検証サーバーだけに設定し、通常のserver.propertiesは変更しない。これは常設の複数サーバー開発環境ではない。

プロトコルクライアントの依存は `scripts/verification/package-lock.json` で固定し、`.cache/verification-client` に `npm ci --ignore-scripts` で準備する。jarと既存リソースパックはキャッシュを再利用する。クライアントはテクスチャを描画せず、リソースパックを辞退する。見た目の合格判定には使えない。

## シナリオを書く

シナリオは信頼するローカルコードとして扱う。`name`、`scope`、`players`、`steps` を指定する。`scope` には初期化方法と確認対象・対象外を書く。状態を直接設定するfixtureと、その状態からの機能実行を区別する。

```json
{
  "name": "storage-example",
  "scope": "console storage round trip; no player or gameplay check",
  "players": [],
  "steps": [
    {
      "name": "write and observe",
      "commands": [
        "data modify storage devspace_verify:example Value set value 7",
        "data get storage devspace_verify:example Value"
      ],
      "expect": ["following contents: 7"]
    }
  ]
}
```

`commands` は順番にRCONで実行し、そのstepの応答だけに対して `expect` の正規表現をすべて検査する。期待値はコードから自動生成せず、仕様・API契約から決める。検証対象のmodifier値や有効タグを直接設定してから同じ値を読む試験を、機能の成功と扱わない。

`{"name":"advance duration","ticks":300}` は凍結状態から`tick step` で指定tick数を進め、gametimeの実測差が指定値に一致するまで待つ。実時間300/20秒をsleepする方式ではない。`first_join` の明示呼出しや信仰タグの設定は必要な場合だけfixtureに書き、成功条件にも対象状態を入れる。通常ログインを試す場合は別のシナリオとして扱う。

シナリオは対象のAsset／本体repoに保存する。DevSpaceのコミットだけでは共有されない。シナリオのパスやシェルの開始位置から参照repoが自動選択される仕組みではない。worktreeの検証はDevSpace側で通常設定の `ASSET_PATH` / `THE_SKY_BLESSING_PATH` 等を対象に揃え、シナリオも同じ作業コピーから渡す。参照先を変える前に通常サーバーを停止し、実行後は `result.json` の `repositories` に記録されたpathを照合する。検証中の参照コードは編集せず、終了後に必要なら元の参照設定へ戻す。

## 結果と失敗を残す

各試行は別ディレクトリに保存する。`result.json` は開始時と各step前後・終了時に更新され、失敗したstepでも入力と取得済みの応答が残る。成功は全stepの期待値一致、サーバーの正常終了と全dimension保存、検証中の参照repoの状態不変を確認した場合だけ返す。

- `scenario.json`: 実行した前提・入力・期待値のコピー。
- `result.json`: 対象repoのpath・branch・HEAD・status・追跡／未追跡ファイルのハッシュ、各stepの実測値、エラー、停止方法、終了コード。
- `*.patch` と `*.changes.tar.gz`: 各repoのHEADからの差分と、変更・未追跡ファイルの内容。削除の情報はpatchとmanifestに残る。再現の基準となるHEADも保持し、共有するシナリオと実装は対象repoに保存する。tarを既存作業ツリーへ無条件に上書きしない。
- `server.log`、`clients.log`、`dependencies.log`: 起動・接続・インストールの観測。テスト用worldと設定も同じローカル領域に残る。

失敗を修正して再試行するときは前のresult.jsonを関連付ける。

```sh
sh scripts/verify.sh Asset/tests/scenarios/dual-rhythm.json \
  --retry-of .runtime/verification-runs/run-xxxx/result.json
```

`stop`で終了しない場合だけ、runnerが作ったプロセスグループへTERM、最後にKILLを送る。強制終了した試行は成功にせず、既存worldや別プロセスのロックは削除しない。ログ・worldは失敗後も削除しない。外部からrunner自体をSIGKILLした場合はfinallyを実行できないため、`running` の結果を合格と読まず、記録PIDの実プロセスを確認する。

失敗時の条件・観測・再試行で変えた条件・確認できた範囲は実行記録に残す。複数条件を同時に変えて直った場合は原因を一つに断定しない。完了時は [ナレッジの採用基準](knowledge-maintenance.md#更新時に残すもの) で再利用できる結論を選び、対象repoの既存の該当節へ統合する。sourcesとの同時更新や、試行ごとの成否・未検証項目の一覧の転記は不要。結論を支える確認範囲と証拠への参照だけを必要に応じて残す。
