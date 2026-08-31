# tep-contributions — TEP Report / 参照分布への opt-in 提出 int TEP Report / opt-in contribution intake（二枚扉・一つの公開コーパス）

**日本語 | [English](README.en.md)**

## これは何か（What this is）

`grift contribute` で組み立てた提出 payload を受け付ける公開リポジトリです。提出は**完全に任意（opt-in）**で、CLI は何も送信しません。**受け取りは二枚扉・保管は一つの公開コーパス**です:

- **公開ドア（door: pr）**: ご自身で payload を PR として提出（希望者のみ `attribution` フィールドでクレジット表記可）
- **身元非公開ドア（door: private）**: フォームまたはメールで受領後、当社が代理で PR を開き `door: private` ラベルを付与（**提出者の身元は非公開のまま、payload は最終的にこの公開コーパスへ保管されます**）

どちらのドアも payload は同じスキーマ検証を通り、同一コーパスに保管されます。

## 提出プロファイル（tep-contribution-v2 / 2026-08-31〜）

v0.6.0 以降の `grift contribute --privacy` は 4 プロファイルを生成しますが、**この公開 intake が受け付けるのは 2 つの公開プロファイルだけ**です:

| profile | このリポジトリへの提出 | 保持する情報 |
|---|---|---|
| `aggregate` | 可（公開ドア・身元非公開ドア） | bucket 化集計・n・denominator・coverage・missingness・random receipt ID。Actor 行・repo/remote/OID・時刻・source digest なし |
| `named-public` | 可（公開ドア・身元非公開ドア） | provider-neutral な公開 project/account 参照と本人Actor観測。raw email・内部Actor ID・pseudonym なし |
| `masked` | **不可（hard error）** | HMAC pseudonym 付き高精度観測。controlled study 用 sidecar が必要 |
| `raw` | **不可（hard error）** | raw names/emails/OID。研究用 controlled 経路専用 |

`masked` / `raw` は controlled 研究経路の資産です。controlled destination が認可・整備されるまで、この intake は機械的に拒否します（CI が fail します）。raw を取得不能にするのが目的ではなく、**用途とアクセス区分を明示した高精度研究経路**として別途整備します。

## 目的拘束 / Purpose restriction

**提出データの用途は「TEP Report 集計と参照分布 vNext」に限定されます。それ以外の目的には使いません。**
特に **チャネル4（Grift SaaS・組織契約）への転用を禁止します**（販売・見積もり・営業への流用を含む）。

## 保持期間と撤回 / Retention & withdrawal

- **保持期間（次回年次 Report の発行まで）は身元非公開ドアの身元記録に適用されます**
- **payload（公開コーパス）は撤回されない限り恒久保持されます** — 参照分布の第三者再計算（検証可能性）のために公開を維持します
- 撤回方法: (a) ご自身の payload を削除する PR を出す (b) README 末尾の連絡先へ依頼（身元非公開ドア経由の身元は依頼時も開示されません）
- **注意**: Git 履歴・fork の存在により、一度公開された payload は完全には消せません。撤回はこのリポジトリの通常表示から除外するものです

## 提出の流れ（公開ドア / How to submit via the public door）

```bash
grift report                                     # ① repo スコープの report を作る
grift contribute --out .grift/contribution.json  # ② payload を組み・全文を確認
# ③ payload をそのまま PR に出す:
#    ファイル: payloads/2026/<submission-id>.json
#    同じ場所に <id>.meta.json を追加（manifest.jsonl は main で自動生成・編集不要）: {"id":"...","sha256":"...","received_at":"...","door":"pr"}
#    attribution を付ける場合は payload の attribution フィールドに任意の表示名（任意・opt-in）
```

## 身元非公開ドア（私的提出 / private door）

フォーム（準備中の場合は下記連絡先メール）へ payload ファイルを添付して送付してください。受領後、当社が代理で PR を開き manifest の `door` を `private` とします。**あなたが PR を開かないため、提出者と GitHub アカウントの紐付けは生じません。** 「非公開」なのは提出者の身元記録だけで、**payload 自体は最終的にこの公開コーパスへ保管・公開されます。**

## 受け付け基準（機械検証 / Mechanically enforced）

CI が各 PR に対して実行します（識別情報を含む PR は**機械的に fail**）:

- payload スキーマ検証（`tep-contribution-v1` または `tep-contribution-v2` の公開プロファイル・repo スコープのみ。v2 は `aggregate` / `named-public` のみ受理）
- **needle sweep**: メール形式の文字列・v1 `actors` 配列・パス・repo 名フィールド・`@` を含む一切の文字列・git OID 形（40/64 hex）の文字列
- v2 `named-public` の URL/account 参照は provider/host/project/account の閉じた構造のみ許可（raw email と controlled payload は拒否）

**含まれている（注明つき）**: v1 `metrics.provenance.analyzed_commit_sha`（分析時点のコミット SHA）と `analyzed_at`（分析時刻）。**SHA は中身を復元できない不透明値ですが、公開 repo では対象の特定に使えます**（特徴の組合せから推測されるリスクと同旨の開示です）。v2 `aggregate` はこの SHA を含みません。

**含まれていない（規則で排除）**: canonical_id・actors（v1）・メール・パス・repo 名（`attribution` フィールドへの任意付記を除く）・tenant スコープ値・v2 では git OID 全般。

## 分布への算入

MIN_N（n≥30）・immutable 版管理の既存規則に従います。

---

## 連絡先（非公開ドア・撤回依頼 / Contact）

- 撤回・非公開提出: `company@cor-jp.com`（メール）
- 質問: このリポジトリの issue（日本語 / English）
