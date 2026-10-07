# mcfunctionの共通イディオム

Asset／TheSkyBlessingの実装・レビューで使う、コマンドの意味に基づく選択肢。Minecraft 1.20.4を前提とする。コード例のstorage・score名は説明用で、実装時には対象の宣言・公開範囲・後始末に合わせる。個別APIの契約は提供repoのナレッジで確認する。

| 実装したいこと・レビュー対象 | 参照先 |
| --- | --- |
| NBT配列の要素を補う／空枠を作る | [一致しない要素も書込みで作られる](#一致しない要素も書込みで作られる) |
| NBTのフラグがtrueかを判定する | [存在と真偽を区別する](#存在と真偽を区別する) |
| NBTの変化を検知する／未設定と0を区別する | [代入結果で変更を検知する](#代入結果で変更を検知する)、[既定値を残す](#既定値を残す) |
| 小数をコマンド結果で受け渡す／NBTの整数を減らす | [整数化を挟む演算](#整数化を挟む演算) |
| 少なくともN体いるか／scoreが設定されているか | [件数を上限で打ち切る](#件数を上限で打ち切る)、[全int範囲でscoreの存在を調べる](#全int範囲でscoreの存在を調べる) |
| 移動の慣性を消す／移動前後の位置を使う | [実行位置を移動前の値として保持する](#実行位置を移動前の値として保持する) |
| ベクトル・方向・角度を計算する | [実行位置と向きを計算に使う](#実行位置と向きを計算に使う) |
| ブロック・モデル・文字や画像を表示する | [display三種を表示内容から選ぶ](#display三種を表示内容から選ぶ) |
| 同値の再設定・0・空配列を削除してよいか | [値が変わらなくても操作には意味がある](#値が変わらなくても操作には意味がある) |

## 一致しない要素も書込みで作られる

NBTのリスト内compoundを条件で選ぶpathは、読取りと書込みで役割が違う。`data modify ... set` の途中にある `[{...}]` は、一致する要素がなければ条件のcompoundを作り、その先へ書き込む。既存リスト内の要素を補完したいときの選択肢になる。

```mcfunction
data modify storage example:work Items set value []
data modify storage example:work Items[{Slot:103b}].Slot set value 0b
# 結果: [{Slot:0b}]。条件のSlot:103bで作り、書込みで0bへ変える。
```

したがって「append元がなくて失敗した→リストは空のまま→Items[0]の条件は偽」とは限らない。後続のfiltered pathへの書込みも追う。検索条件が一意でなければ複数の一致要素が更新され得るため、常に1要素へのupsertとして使わない。既存要素だけを変えたい場合は、書込みの前に存在を判定する。

[本体inventory/set](../TheSkyBlessing/TheSkyBlessing/data/api/functions/inventory/set.mcfunction) は、入力にないslotにもSlotだけの要素を作り、作業shulkerを介して空のアイテムへ変換し、`loot replace` で元の枠を消す。一般のNBTリストの要素生成と、このAPI固有の空枠への変換を区別する。[空配列での実測とAPIの検証](../TheSkyBlessing/docs/verification/mp-xpbar-and-grave.md)を参照。

## 存在と真偽を区別する

NBTのフラグがtrueであることを条件にする場合は、`if data ... {Flag:true}` と値を照合する。`if data ... Flag` は存在の判定なので、falseが保存されていても成立する。

```mcfunction
execute if data storage example:work {ShouldFinish:true} run function example:finish
```

書込み側がtrueしか設定しない実装でも、判定側でtrueを照合すれば条件をその場で読める。値にかかわらず設定済みかを知りたい場合には、存在判定を使う。フラグの真偽と、値の欠損を分岐の意図に合わせて区別する。

## 代入結果で変更を検知する

比較対象のNBTを代入で更新してよい場合は、`data modify ... set from` の成功値を変更検知に使える。同値では変更が起こらないことを利用する。

```mcfunction
execute store success storage example:work Changed byte 1 run data modify storage example:work Old set from storage example:work New
```

これは比較と更新を一緒に行う。比較前のOldが必要なら別に保持する。また、参照元不在などの失敗も成功値0になるので、0を同値と解釈するには入力の存在・型を保証するか、欠損を別分岐で扱う。

実例は本体の[装着音のUUID比較](../TheSkyBlessing/TheSkyBlessing/data/player_manager/functions/play_equip_sound/validate.mcfunction)と[DataCacheのTime更新](../TheSkyBlessing/TheSkyBlessing/data/api/functions/data_get/_restore_or_fetch.mcfunction)。前者はUUIDを持たない通常アイテム、後者は同tick内のIsDirtyも扱う。成功値を使う代入を、冗長なコピーや純粋な比較として整理しない。

## 既定値を残す

「値がなければ既定値」「値があれば0も有効」としたい場合は、先に既定値を置き、存在判定をstoreより前にする。

```mcfunction
scoreboard players set #value Example -16
execute if data storage example:work Value store result score #value Example run data get storage example:work Value
```

getが失敗した結果をstoreする処理と、storeへ進まない処理は異なる。条件をstoreの後ろへ移すと、失敗結果で既定値を上書きし得る。0・負数・欠損のどれを番兵値にするかは有効値域から決める。[cooldownの比較](../TheSkyBlessing/TheSkyBlessing/data/asset_manager/functions/artifact/cooldown/common/compare_cooldown.mcfunction)の-16は、この仕組みを使うAPI固有の既定値である。

## 整数化を挟む演算

### 小数の受け渡しと単位変換

コマンド結果はintなので、`store ... double` だけでは小数を保持できない。取得時に倍率S、保存時に逆数1/Sを掛けると、固定小数点として受け渡せる。

```mcfunction
execute store result storage example:work X double 0.0001 run data get storage example:work SourceX 10000
```

倍率は、必要精度と中間のintの範囲から選ぶ。負数の丸めや上限を含めた値域を確認し、乗除が相殺されるという理由で削除しない。実例は[Smoke Bombの座標](../Asset/Asset/data/asset/functions/object/2003.smoke_bomb/tick/tp.mcfunction)。

保存倍率が逆数と違う場合は、固定小数点の復元に加えて単位変換や倍率計算をしている可能性がある。[slide_move](../TheSkyBlessing/TheSkyBlessing/data/lib/functions/slide_move/.mcfunction)の10000と0.00005は半分の距離、[rotate_display](../TheSkyBlessing/TheSkyBlessing/data/lib/functions/rotate_display/core/marker.mcfunction)の10000と0.000001745は度からラジアンへの近似換算を含む。積だけでなく整数化の位置を保って読む。

### 1未満の倍率で非負の整数を減らす

正の整数nについて `n-1 <= k*n < n` が成り立ち、浮動小数点でもnへ丸め戻らない係数kを使うと、intへの変換でn-1になる。0は0のままなので、NBT内の非負カウンタをscoreへ往復させずに減らせる。

```mcfunction
execute store result storage example:work Remaining int 0.9999999999 run data get storage example:work Remaining 1
```

正の整数・係数・値域をセットで採用する。Minecraft 1.20.4ではgetの倍率適用後はfloor、storeのint変換は0方向への切り捨てなので、負数では係数をgetとstoreの間で移せない。-1にこの係数を掛けると前者は-1、後者は0になる。両段へ係数を掛けると整数化も二回入る。実例と番兵値の扱いは[Assetのカウンタ](../Asset/docs/knowledge/runtime-and-tools.md#nbtの整数カウンタを1未満の倍率で減らす)を参照。

丸めの根拠はMinecraft Java 1.20.4の公式server jarと [Mojang公式server mappings](https://piston-data.mojang.com/v1/objects/c1cafe916dd8b58ed1fe0564fc8f786885224e62/server.txt) の照合。`DataCommands` の数値取得は乗算後に `Mth.floor(double)`、`ExecuteCommand` のint保存は乗算後にJVMの `d2i` を使う。配布メタデータとjarのハッシュを照合したバイトコード調査に基づく。各利用例の寿命をゲーム内で検証した結果とは区別する。

## 件数を上限で打ち切る

正確な総数ではなく「N体以上か」だけが必要なら、`limit=N` のselectorで件数を取得し、Nとの一致を判定できる。取得値は `min(実数,N)` になる。

```mcfunction
execute store result storage example:work Count int 1 if entity @e[tag=ExampleTarget,distance=..32,limit=10]
execute if data storage example:work {Count:10} run return 0
return 1
```

この例は10体未満なら1を返す。limitだけを外すと11体以上が一致しなくなり、意味が変わる。対象の種類・探索範囲と、上限・比較値を一組で扱う。関数の結果にcleanupの成功値を流用せず、判定結果を明示する。[Silver Turret](../Asset/Asset/data/asset/functions/mob/0421.silver_turret/tick/check_count.mcfunction)が実例。

## 全int範囲でscoreの存在を調べる

`if score <対象> <objective> matches -2147483648..2147483647` は、objectiveが定義済みなら、参照できるscoreがあるかを調べる形になる。0や負数も設定済みとして扱いたいときに使える。

| 対象のscore | if | unless |
| --- | --- | --- |
| 設定済み（0・負数を含む） | 成立 | 不成立 |
| 未設定・参照できない | 不成立 | 成立 |

全範囲だから常にtrueとは限らない。一方、`unless` を生存中の通常個体の継続条件として読むのも逆である。この判定自体は一般的な生死判定ではなく、scoreの初期化・破棄の契約と組み合わせて使う。未定義objectiveのエラーを「未設定score」の分岐として利用しない。本体Objectの具体的な用途は[dispatch後のField保存](../TheSkyBlessing/docs/knowledge/asset-runtime.md#tick-と実行-context)を参照。

## 実行位置を移動前の値として保持する

関数内で実行者をtpしても、呼出時の実行位置が自動で追従するわけではない。同じ文脈の `~ ~ ~` は移動前の位置、`at @s` で取り直した位置は移動後の位置として使い分けられる。移動元と移動先の演出や、元の位置へ戻す処理に利用できる。

移動の慣性を消し、視点移動の慣性を残す既存イディオムは次の往復である（目的はユーザー確認済み）。本人の位置・次元を実行文脈として開始し、同じ条件・文脈で二行を実行する。

```mcfunction
tp @s 0 0 0
tp @s ~ ~ ~
```

途中で `at @s` を挟むと戻り先を失う。`tp @s @s` は視点の慣性リセットも許容する場面の別の選択肢で、単純な短縮形ではない。実例は[Blade of Whirlwind](../Asset/Asset/data/asset/functions/artifact/0745.blade_of_whirlwind/trigger/3.main.mcfunction)と[チュートリアル転移](../TheSkyBlessing/TheSkyBlessing/data/world_manager/functions/area/00-08.tutorial-tp_gate.mcfunction)。

## 実行位置と向きを計算に使う

`positioned`・`rotated`・`facing` の連鎖は、entityの移動ではなくベクトル・角度・判定位置を計算する手段になる。新規の方向計算でも、scoreboardへの座標の出し入れと演算を増やす前に、既存の公開幾何APIと同種の構成を確認する。

レビューでは実行者、位置、向き、次元を別々に追い、連鎖全体で得るベクトルや角度を式にする。原点への移動や巨大な後退距離を、実体を移動させる命令や演出上の距離と決めつけない。途中の `at @s`、係数の変更、facingの差替えは計算を変える。

方向の合成・追尾・回転は[Assetの幾何例](../Asset/docs/knowledge/runtime-and-tools.md#execute幾何学で表示の回転を作る)、内積による判定・反射・滑り移動は[本体の幾何部品](../TheSkyBlessing/docs/knowledge/runtime-components.md#幾何移動rom結果の受け渡し方が違う部品)に式とAPI条件がある。共有markerを使う場合は借用区間と復元も契約に含める。

## display三種を表示内容から選ぶ

Minecraft 1.20.4では、表示するデータに合わせて次の三種を選ぶ。三種とも表示用entityであり、見た目を拡大しても物理的な当たり判定は生まれない。クリックの検出や攻撃の命中判定は別に用意する。

| 種類 | 選ぶ場面 | 主な入力と注意点 |
| --- | --- | --- |
| `block_display` | ブロックの見た目やブロック状態を使う演出 | `block_state` の `Name`・`Properties`。実ブロックの設置やblock entityの再現にはならない |
| `item_display` | アイテムモデルやCustomModelDataで指定する立体モデル | `item` に1.20.4のItemStack形式を渡す。`item_display` フィールドはモデルJSONの表示変換を選ぶ値で、entityの種類とは区別する |
| `text_display` | 名前・数値・文章、フォントの字形で表す画像 | `text` のTextComponent。`font` で演出画像も表示できる。文字の配置・背景・不透明度は専用フィールドで指定する |

表示内容を変える入力と、位置・回転・拡大縮小を変える `transformation` は分けて選ぶ。`billboard` は視点への追従を指定する。`width`・`height` は描画を省略する判定用の箱で、当たり判定の大きさではない。種別を変えるとモデルの原点や表示変換も変わるため、同じtransformationを移すだけで同じ位置・大きさになるとは扱わない。

実例はAssetの [氷の表示](../Asset/Asset/data/asset/functions/object/2158.haruclaire_death/summon/.mcfunction)、[標識モデル](../Asset/Asset/data/asset/functions/object/1012.traffic_sign/summon/m.mcfunction)、[フォントを使った斬撃](../Asset/Asset/data/asset/functions/object/1187.dimension_slash/summon/m.mcfunction)。本体の [墓](../TheSkyBlessing/TheSkyBlessing/data/player_manager/functions/grave/build/m.mcfunction) はitem_displayで外形、text_displayで名前、interactionで操作の受付を分担する。選択基準は形状と必要な操作から決め、三種の処理負荷に未計測の順位を付けない。

### 光量と、面の向きによる陰影を分ける

`brightness:{block:15,sky:15}` は描画に渡すブロック光・天空光を最大にする。未指定時はentityの位置の光量を使う。これは周囲を照らす光源の設置ではなく、モデルの陰影を消す設定でもない。

Minecraft 1.20.4の標準シェーダーでは、text_displayとitem／block_displayで次の違いがある。

| 描画対象 | 光量の扱い | 面の向きによる陰影 |
| --- | --- | --- |
| 通常のitem／block_displayのモデル | 環境光またはbrightnessの指定を使う | 通常のモデル描画では法線と光の方向から陰影を付ける。光量を最大にしても、面や向きで暗く見えることがある。モデルと描画経路にも依存する |
| text_displayの文字・フォント画像、`see_through:false` | 環境光またはbrightnessの指定を使う | モデルのような法線による陰影計算がなく、表示面の向きだけで同じ陰影は付かない |
| text_displayの文字・フォント画像、`see_through:true` | この描画経路ではライトマップを参照しない | 法線による陰影計算も行わない。ただし遮蔽の扱いも変わり、ブロック越しに見える |

向きを変えても画像の色を一定に見せたい平面の演出では、フォント画像をtext_displayで描き、`see_through:false` と最大brightnessを使う構成が候補になる。立体モデルを使う場合は、brightnessだけで全面を同じ明るさにできるとは考えない。text_displayも通常表示では環境光を受けるため、「文字だから常に最大光量」とも扱わない。

根拠は、ハッシュを公式配布情報と照合した [1.20.4クライアントJAR](https://piston-data.mojang.com/v1/objects/fd19469fed4a4b4c15b2d5133985f0e3e7816a8a/client.jar) と [公式マッピング](https://piston-data.mojang.com/v1/objects/be76ecc174ea25580bdc9bf335481a5192d9f3b7/client.txt)。DisplayRendererの光量選択、TextDisplayRendererの描画モード、`rendertype_text`／`rendertype_text_intensity` と各 `see_through`、`rendertype_entity_solid`／`rendertype_entity_cutout` の頂点シェーダーを照合した。shaderを差し替えるパックやModには、この標準描画の結果をそのまま適用しない。

三種の入力・表示専用の性質・共通フィールドは [Mojangの導入時仕様](https://www.minecraft.net/en-us/article/minecraft-snapshot-23w06a) と上記の1.20.4実装を照合した。補間の開始方法など、その後に変更された仕様を導入時の記事だけから転記しない。向きを扱う本体APIの契約は、依存先TheSkyBlessingの `docs/knowledge/runtime-components.md`「displayのRotationと見た目の向きを分ける」を参照する。

## 値が変わらなくても操作には意味がある

最終的なNBTやscoreが同じでも、途中の操作が描画・イベント・遅延評価を起こす場合がある。次の処理を新規実装の選択肢にするときは対象別の条件を読み、レビューでは「値が同じだから削除できる」と判断しない。

| 必要な処理 | 既存の手段と詳細 |
| --- | --- |
| 装備内容を保ったまま手持ちを振る | [Mobのitem replace](../Asset/docs/knowledge/mob.md#装備の変更と見た目を分ける) |
| LootTableを今評価してItemsを得る | [Containerの空のidentity modifier](../TheSkyBlessing/docs/knowledge/world-components.md#container構築用の指定を-block-の内容物へ変換する) |
| 上限に応じた金ハート量を反映する | [absorptionの付与と解除](../TheSkyBlessing/docs/knowledge/runtime-components.md#金ハートの量を-attribute-と効果の付与解除で設定する) |
| item entityのMotion変更を描画へ反映する | [damage 0とFireの対象別制約](../TheSkyBlessing/docs/knowledge/runtime-components.md#墓と-lostitems所有者の保存内容と回収の窓口) |

これらは同じ内部機構とは限らず、別のentityやバージョンで相互に交換可能という保証でもない。
