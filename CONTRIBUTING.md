# 貢献ガイド / Contributing guide

## 提出できる方 / Who can contribute

ご自身のリポジトリ（または提出する権利のあるリポジトリ）の開発者の方。

## 公開ドア（本人 PR）/ Public door

1. 対象リポジトリで `grift report` を実行（grift-cli 0.5.5 以降）
2. `grift contribute --out .grift/contribution.json` で payload を組み、**全文を確認**
3. このリポジトリに PR:
   - **payload ファイル**: `payloads/2026/<submission-id>.json`（`grift contribute` の出力をそのまま・手編集不可）
   - **manifest.jsonl に1行追記**: `{"id":"<submission-id>","sha256":"<sha256>","received_at":"<ISO8601>","door":"pr"}`
   - クレジット希望者のみ payload に `attribution: "表示名"` を追加（任意・64文字以内・メール/URL 禁止）
   - ブランチ名: `contrib/<submission-id>`／PR タイトル: `contribution: <submission-id>`

## 非公開ドア / Private door

payload ファイルをフォーム（または README の連絡先メール）へ添付送付。当社が代理 PR を開き manifest の `door` を `"private"` にします。**あなたの GitHub アカウントと提出は紐付きません。**

## ルール / Rules

- CI が schema（`tep-contribution-v1`）・sha256・needle sweep（メール形式・actors・パス・repo 名・`@`）を検証します。**識別情報を含む PR は機械的に fail します**
- 手編集された payload は sha256/スキーマ検証で落ちます
- 1 リポジトリ 1 最新提出（更新は新しい PR で）

## 撤回 / Withdrawal

自 payload 削除の PR、または README の連絡先への依頼。

## 質問 / Questions

issue にて（日本語 / English どちらでも）。
