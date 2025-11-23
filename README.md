# Skeleton Form Analysis

Skeleton Form Analysis は、動画から骨格を抽出してフォームチェックを支援する FastAPI アプリケーションです。動画をアップロードすると MediaPipe Pose が骨格ポイントを検出し、骨格のみの動画とオーバーレイ動画を生成します。

## 主な機能
- 動画アップロードによる骨格抽出（骨格のみ / オーバーレイ動画を生成）
- 進捗表示付きアップロード UI（モバイル・タブレット対応、カメラ撮影にも対応）
- 解析結果のダウンロード機能
- お問い合わせフォーム（SMTP 経由で通知）
- 自動クリーンアップ（アップロード / 結果ファイルを一定時間後に削除）

## 必要要件
- Python 3.10 以上（mediapipe の公式対応バージョン）
- 仮想環境（推奨）
- OpenCV, MediaPipe, FastAPI など（`requirements.txt` 参照）

