# grift-contributions — TEP Report / 参照分布への opt-in 提出 int TEP Report / opt-in contribution intake

**日本語 | [English](README.en.md)**

## これは何か（What this is）

`grift contribute` で組み立てた提出 payload を受け付ける公開リポジトリです。提出は **完全に任意（opt-in）** で、CLI は何も送信しません — あなたが payload を確認し、ご自身で PR を出すことで初めて提出になります。

This public repository receives opt-in contribution payloads built by
`grift contribute`. Submission is entirely voluntary; the CLI never sends
anything — you review the payload and open the PR yourself.

## 提出の流れ（How to submit）

```bash
# 1. 対象リポジトリで repo スコープの report を作る
grift report                      # → .grift/report.{json,md}

# 2. payload を組む（全文が表示され、「この提出は公開リポジトリに載る」ことが明示されます）
grift contribute --out .grift/contribution.json

# 3. payload を確認して、このリポジトリに PR を出す
#    ファイル名: contributions/YYYY/MMDD-HHMM-<hash8>.json（例: contributions/2026/0823-1415-a1b2c3d4.json）
#    ※ payload に repo 名・メール・canonical_id は含まれません
```

## 受け付けられるもの / ならないもの（Accepted / not accepted）

**受け付けられる**: repo スコープの集計値 + context_profile（クラス級）+ 定義版。`tep-contribution-v1` スキーマの JSON 1 ファイル。

**含まれていない（規則で排除）**: canonical_id・actors・メール・パス・repo 名（提出者が付記を選ばない限り）・tenant スコープ値。

## 提出されたデータの扱い（How submissions are used）

- **用途は「TEP Report 集計と参照分布 vNext」に限定**されます（それ以外には使いません）
- 保持期間は次回年次 Report の発行まで。撤回は issue で受け付けます（PR の revert でも構いません）
- 詳細は [grift-cli の norms](https://github.com/Cor-Incorporated/grift-cli/blob/main/docs/norms.md) の保持・削除条項

## 審査について（Review）

- スキーマ検証（`tep-contribution-v1`）を機械的に行います
- **個人が特定できる内容・スキーマ外のデータを含む PR は却下します**
- 分布への算入は MIN_N（n≥30）・immutable 版管理の既存規則に従います
