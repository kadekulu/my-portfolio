# 引き継ぎ資料：Elite Portfolio SNS自動化プロジェクト (2026年5月版)

## 1. プロジェクトの概要
ローカルのイラストフォルダに画像を追加すると、AIが自動でタグ付けと「SNS投稿案（3パターン）」を生成し、Make.com 経由で Google スプレッドシートのキューに登録。そこから Buffer を通じて予約投稿を行うシステム。

## 2. 現在の技術スタックと状況
- **画像処理 (`update_gallery.py`)**:
    - **AIモデル**: Ollama (`minicpm-v`) ※規制が緩くイラスト読み取りに強い。
    - **機能**: ロゴ入れ、AI分析（タグ+投稿案）、Make.com Webhook送信、GitHub Pages公開。
    - **SNSルール (v1.0)**: 目標6文字・上限15文字の極短文、3パターン（余韻・再会・想い）、末尾に `#愛依莉` タグ。
- **管理画面 (`tag_editor.py`)**:
    - FlaskベースのWebアプリ。ビジュアルを確認しながらタグの修正が可能。
    - Ollamaプロセスの自動起動・終了（VRAM解放用）をスイッチで管理。
- **データ管理**: `tags_cache.json` にタグと投稿案を保存。

## 3. 次のタスク：Make.com の構築
- **インポート待ち**: `make_blueprint.json` がデスクトップの `portfolio` フォルダ内に作成済み。
- **スプレッドシート構成**: [ファイル名, 画像URL, 投稿案A, B, C, タグ, 承認, 予約時間, ステータス] の列を持つシートが必要。
- **やりたいこと**:
    1.  Webhook で受け取ったデータをスプレッドシートに追加。
    2.  スプレッドシートで「承認」したものを、予約時間に合わせて Buffer (API制限10個) へ予約。
    3.  投稿後にスプレッドシートにログを残す。

## 4. 重要なファイルパス
- 作業ディレクトリ: `C:\Users\kainn\OneDrive\desktop\illustrationAI\portfolio`
- 設定ファイル: `update_gallery.py`, `tag_editor.py`, `make_blueprint.json`
- Webhook URL: `https://hook.us2.make.com/he8csq0dbyu2t4zoqiiql6myvlzhvw53`
