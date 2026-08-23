# 貢献ガイド / Contributing guide

## 提出できる方 / Who can contribute

ご自身のリポジトリ（または提出する権利のあるリポジトリ）の開発者の方。

## 手順 / Steps

1. 対象リポジトリで `grift report` を実行（`grift-cli` 0.5.5 以降を推奨）
2. `grift contribute --out .grift/contribution.json` で payload を組み、**全文を確認**してください
3. このリポジトリに PR を出してください:
   - **ブランチ名**: `contrib/YYYYMMDD-<hash8>`（例: `contrib/20260823-a1b2c3d4`）
   - **ファイル**: `contributions/YYYY/MMDD-HHMM-<hash8>.json`（payload の sha256 先頭8桁）
   - PR のタイトルは `contribution: <hash8>` のみ（repo 名・個人名は書かないでください）

## ルール / Rules

- **payload は `grift contribute` が生成したものをそのまま**提交してください（手編集はスキーマ検証で落ちます）
- 個人を特定できる情報・repo 名の追記は任意ですが、追記した場合は公になります
- 1 リポジトリ 1 最新提出（更新は新しい PR で。古いものは maintainers が close します）

## 撤回 / Withdrawal

issue を立てるか、ご自身の PR/ファイルの revert PR を出してください。次回の整理サイクルで削除します。

## 質問 / Questions

issue にて（日本語 / English どちらでも）。
