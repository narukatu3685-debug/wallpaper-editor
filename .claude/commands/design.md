---
description: 詳細設計（DB設計・API仕様・画面フロー、AI自走）
---

# /design — 詳細設計

## 目的

承認済みの要件と、確定した UI/UX 仕様（`ui-spec.md`）を踏まえて、DB設計・API仕様・画面フローを設計する。この工程は人間の承認なしで AI が自走してよいが、要件の範囲を超える判断が必要になったら `/requirements` に立ち返る。

## 開始時に行うこと（ゲートチェック）

1. `docs/01-requirements/user-stories.md` / `feature-list.md` の承認記録欄が `承認済み` であることを確認する。
2. `docs/02-prototype/review-feedback.md` のレビュー記録欄で「次工程へ進んでよいか」が `はい` になっていること、および `docs/02-prototype/ui-spec.md` が存在することを確認する。
   - いずれか欠けていれば着手せず、不足している工程に戻るよう伝えて停止する。
3. `docs/00-status.md` の「詳細設計」行を `進行中` に更新する。

## 設計作業

- `docs/03-design/db-design.md`: ER図（mermaid可）とテーブル定義。各テーブルが対応する機能IDを明記する。
- `docs/03-design/api-spec.md`: エンドポイント一覧（パス・メソッド・入出力・エラー）。
- `docs/03-design/screen-flow.md`: 画面遷移・ワイヤーフレーム・シーケンス図など。
  - **末尾に「UI/UX仕様（ui-spec.md）の反映状況」表を必ず含める**（指摘ID／内容／設計での反映先／状態）。`ui-spec.md` の「未確定」項目をここで確定させた場合も、この表に載せる。
- `ui-spec.md` の内容は必須の入力であり、勝手に変えない。変える必要が生じた場合は理由を成果物に明記し、影響が大きければ `docs/03-design/questions.md` で確認する。
- 判断に迷う点（要件の範囲を超えそうな仕様判断など）は `docs/03-design/questions.md` に書き出して停止する（書式・運用は `CLAUDE.md` 参照）。範囲外の新機能が必要そうなら `/requirements` に立ち返ることを提案する。

## 完了時に行うこと

- `docs/00-status.md` の「詳細設計」行を `完了` に更新する。
- `docs/audit.md` に追記する。
- 完了報告（`CLAUDE.md` のフォーマット）。次のアクションは「`/implement` に進めます」の一択。

## 入出力

- 入力: 承認済みの要件定義 ＋ デモレビュー完了（`ui-spec.md`, `review-feedback.md`）
- 出力: `docs/03-design/db-design.md`, `api-spec.md`, `screen-flow.md`（RV-xx の反映先を明記）
