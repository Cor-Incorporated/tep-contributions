# tep-contributions — TEP Report / 参照分布への opt-in 提出 int TEP Report / opt-in contribution intake（二枚扉・一つの公開コーパス）

**日本語 | [English](README.en.md)**

## これは何か（What this is）

`grift contribute` で組み立てた提出 payload を受け付ける公開リポジトリです。提出は**完全に任意（opt-in）**で、CLI は何も送信しません。**受け取りは二枚扉・保管は一つの公開コーパス**です:

- **公開ドア（door: pr）**: ご自身で payload を PR として提出（希望者のみ `attribution` フィールドでクレジット表記可）
- **非公開ドア（door: private）**: フォームまたはメールで受領後、当社が代理で PR を開き `door: private` ラベルを付与（**提出者の身元は非公開のまま**）

どちらのドアも payload は同じスキーマ検証を通り、同一コーパスに保管されます。

## 目的拘束 / Purpose restriction

**提出データの用途は「TEP Report 集計と参照分布 vNext」に限定されます。それ以外の目的には使いません。**
特に **チャネル4（Grift SaaS・組織契約）への転用を禁止します**（販売・見積もり・営業への流用を含む）。

## 保持期間と撤回 / Retention & withdrawal

- **保持期間（次回年次 Report の発行まで）は非公開ドアの身元記録に適用されます**
- **payload（公開コーパス）は撤回されない限り恒久保持されます** — 参照分布の第三者再計算（検証可能性）のために公開を維持します
- 撤回方法: (a) ご自身の payload を削除する PR を出す (b) README 末尾の連絡先へ依頼（非公開ドア経由の身元は依頼時も開示されません）

## 提出の流れ（公開ドア / How to submit via the public door）

```bash
grift report                                     # ① repo スコープの report を作る
grift contribute --out .grift/contribution.json  # ② payload を組み・全文を確認
# ③ payload をそのまま PR に出す:
#    ファイル: payloads/2026/<submission-id>.json
#    同じ場所に <id>.meta.json を追加（manifest.jsonl は main で自動生成・編集不要）: {"id":"...","sha256":"...","received_at":"...","door":"pr"}
#    attribution を付ける場合は payload の attribution フィールドに任意の表示名（任意・opt-in）
```

## 非公開ドア（私的提出 / private door）

フォーム（準備中の場合は下記連絡先メール）へ payload ファイルを添付して送付してください。受領後、当社が代理で PR を開き manifest の `door` を `private` とします。**あなたが PR を開かないため、提出者と GitHub アカウントの紐付けは生じません。**

## 受け付け基準（機械検証 / Mechanically enforced）

CI が各 PR に対して実行します（識別情報を含む PR は**機械的に fail**）:

- payload スキーマ検証（`tep-contribution-v1`・repo スコープのみ）
- **needle sweep**: メール形式の文字列・`actors` 配列・パス・repo 名フィールド・`@` を含む一切の文字列

**含まれていない（規則で排除）**: canonical_id・actors・メール・パス・repo 名（`attribution` フィールドへの任意付記を除く）・tenant スコープ値。

## 分布への算入

MIN_N（n≥30）・immutable 版管理の既存規則に従います。

---

## 連絡先（非公開ドア・撤回依頼 / Contact）

- 撤回・非公開提出: `company@cor-jp.com`（メール）
- 質問: このリポジトリの issue（日本語 / English）
