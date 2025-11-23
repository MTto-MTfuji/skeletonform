# Skeleton Form Analysis

Skeleton Form Analysis は、動画から骨格を抽出してフォームチェックを支援する FastAPI アプリケーションです。動画をアップロードすると MediaPipe Pose が骨格ポイントを検出し、骨格のみの動画とオーバーレイ動画を生成します。

## 主な機能
- 動画アップロードによる骨格抽出（骨格のみ / オーバーレイ動画を生成）
- 進捗表示付きアップロード UI（モバイル・タブレット対応、カメラ撮影にも対応）
- 解析結果のダウンロード機能
- お問い合わせフォーム（SMTP 経由で通知）
- 自動クリーンアップ（アップロード / 結果ファイルを一定時間後に削除）

## 必要要件
- Python 3.11+
- 仮想環境（推奨）
- OpenCV, MediaPipe, FastAPI, Uvicorn など（`requirements.txt` を参照）

## セットアップ
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```


- PC とスマホを同じネットワークに接続し、`http://<PCのIP>:8000` にアクセスすればスマホからもテスト可能です。

## 今後の改善アイデア
- 解析時間 / 失敗率などのログを蓄積してダッシュボード化
- S3 など外部ストレージと署名付き URL を活用して結果を共有
- 解析ジョブをキューイングして高負荷時も安定させる（Celery など）
- Render / Railway などへのデプロイ、およびオートスケール対応

## ライセンス
MIT License

