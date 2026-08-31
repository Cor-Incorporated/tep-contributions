# 貢献ガイド / Contributing guide

## 提出できる方 / Who can contribute

ご自身のリポジトリ（または提出する権利のあるリポジトリ）の開発者の方。

## 公開ドア（本人 PR）/ Public door

1. 対象リポジトリで `grift report` を実行（v2 は grift-cli 0.6.0 以降）
2. `grift contribute --privacy aggregate|named-public --door public-pr --out .grift/contribution.json` で payload を組み、**全文を確認**
3. このリポジトリに PR:
   - **payload ファイル**: `payloads/2026/<submission-id>.json`（`grift contribute` の出力をそのまま・手編集不可）
   - **meta sidecar**: 同じ場所へ `<submission-id>.meta.json` を追加: `{"id":"<submission-id>","sha256":"<sha256>","received_at":"<ISO8601>","door":"pr"}`。`manifest.jsonl` は main CI の single writer が生成するため PR では編集しない
   - クレジット希望者のみ payload に `attribution: "表示名"` を追加（任意・64文字以内・メール/URL 禁止）
   - ブランチ名: `contrib/<submission-id>`／PR タイトル: `contribution: <submission-id>`

## 非公開ドア / Private door

payload ファイルをフォーム（または README の連絡先メール）へ添付送付。当社が代理 PR を開き manifest の `door` を `"private"` にします。**あなたの GitHub アカウントと提出は紐付きません。**

## ルール / Rules

- CI が schema（legacy `tep-contribution-v1` と公開 `tep-contribution-v2`）・sha256・needle sweep（メール形式・actors・パス・repo 名・`@`）を検証します。**識別情報を含む PR は機械的に fail します**
- v2 の `aggregate` / `named-public` は profile 別 digest・source replay・closed measurement を検証します。`named-public` は project/account に拘束した本人 authority と public account evidence/coverage が必要です
- `masked` / `raw` は controlled 専用のため、この公開 intake では hard error です
- 手編集された payload は sha256/スキーマ検証で落ちます
- 1 リポジトリ 1 最新提出（更新は新しい PR で）

## 撤回 / Withdrawal

自 payload 削除の PR、または README の連絡先への依頼。

## 質問 / Questions

issue にて（日本語 / English どちらでも）。
