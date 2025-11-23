import cv2
import mediapipe as mp
import numpy as np
import os
import shutil
import uuid
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from fastapi import FastAPI, Request, File, UploadFile, BackgroundTasks, Form
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import HTTPException

app = FastAPI(title="Skeleton Form Analysis")

# メール設定（環境変数から取得。未設定の場合は後続処理で検知）
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# アップロード制限
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "200"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
UPLOAD_RETENTION_SECONDS = int(os.getenv("UPLOAD_RETENTION_SECONDS", "600"))
RESULT_RETENTION_SECONDS = int(os.getenv("RESULT_RETENTION_SECONDS", "600"))

# ディレクトリ設定
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
RESULT_DIR = BASE_DIR / "static" / "results"
TEMPLATES_DIR = BASE_DIR / "templates"

# ディレクトリ作成
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# 静的ファイルとテンプレートの設定
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# MediaPipe設定
mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose

# 描画スタイル設定
# 線の色: 緑 (0, 255, 0), 太さ: 4
# 点の色: 白 (255, 255, 255), 半径: 4
connection_spec = mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=4)
landmark_spec = mp_drawing.DrawingSpec(color=(255, 255, 255), thickness=4, circle_radius=4)

def is_allowed_extension(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS

def save_upload_file(upload_file: UploadFile, destination: Path) -> int:
    """
    アップロードファイルを保存しつつ、サイズ上限をチェックする
    """
    upload_file.file.seek(0)
    bytes_written = 0
    chunk_size = 1024 * 1024  # 1MB
    with open(destination, "wb") as buffer:
        while True:
            chunk = upload_file.file.read(chunk_size)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > MAX_UPLOAD_SIZE_BYTES:
                buffer.close()
                destination.unlink(missing_ok=True)
                raise ValueError(f"最大{MAX_UPLOAD_SIZE_MB}MBまでアップロード可能です。")
            buffer.write(chunk)
    upload_file.file.seek(0)
    return bytes_written

def cleanup_old_files(directory: Path, max_age_seconds: int = 600):
    """
    指定されたディレクトリ内の古いファイルを削除する
    デフォルト: 10分 (600秒) 以上前のファイルを削除
    """
    try:
        current_time = time.time()
        for file_path in directory.iterdir():
            if file_path.is_file():
                # 最終更新日時または作成日時を確認
                file_age = current_time - file_path.stat().st_mtime
                if file_age > max_age_seconds:
                    try:
                        os.remove(file_path)
                        print(f"Deleted old file: {file_path}")
                    except Exception as e:
                        print(f"Error deleting file {file_path}: {e}")
    except Exception as e:
        print(f"Error during cleanup: {e}")

@app.on_event("startup")
async def startup_cleanup():
    cleanup_old_files(UPLOAD_DIR, UPLOAD_RETENTION_SECONDS)
    cleanup_old_files(RESULT_DIR, RESULT_RETENTION_SECONDS)

def process_video(input_path: Path, output_skeleton_path: Path, output_overlay_path: Path):
    """
    動画を処理して骨格のみ動画とオーバーレイ動画を生成する
    """
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError("Failed to open video file")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    # FPSが取得できない場合のフォールバック
    if fps <= 0:
        fps = 30.0

    fourcc = cv2.VideoWriter_fourcc(*'avc1') # H.264

    # Writer初期化
    out_skeleton = cv2.VideoWriter(str(output_skeleton_path), fourcc, fps, (width, height))
    out_overlay = cv2.VideoWriter(str(output_overlay_path), fourcc, fps, (width, height))

    # MediaPipe Pose初期化
    with mp_pose.Pose(
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        model_complexity=2 # 高精度モデル
    ) as pose:
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            # 処理用にコピー
            image = frame.copy()
            # MediaPipeはRGB入力を期待
            image.flags.writeable = False
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = pose.process(image)

            # 描画準備
            image.flags.writeable = True
            
            # 1. 骨格のみフレーム（黒背景）
            skeleton_frame = np.zeros((height, width, 3), dtype=np.uint8)
            
            # 2. オーバーレイフレーム（元画像ベース）
            overlay_frame = frame.copy()

            if results.pose_landmarks:
                # 骨格のみ描画
                mp_drawing.draw_landmarks(
                    skeleton_frame,
                    results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=landmark_spec,
                    connection_drawing_spec=connection_spec
                )
                
                # オーバーレイ描画
                mp_drawing.draw_landmarks(
                    overlay_frame,
                    results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=landmark_spec,
                    connection_drawing_spec=connection_spec
                )

            # 書き込み
            out_skeleton.write(skeleton_frame)
            out_overlay.write(overlay_frame)

    cap.release()
    out_skeleton.release()
    out_overlay.release()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})

@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})

@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    return templates.TemplateResponse("terms.html", {"request": request})

@app.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request})

@app.post("/contact", response_class=HTMLResponse)
async def contact_submit(
    request: Request,
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    email: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...)
):
    try:
        # メール本文の作成
        email_body = f"""
【お問い合わせがありました】

■お名前:
{name}

■メールアドレス:
{email}

■件名:
{subject}

■お問い合わせ内容:
{message}
        """

        # SMTP設定
        if not SMTP_USER or not SMTP_PASSWORD:
            return templates.TemplateResponse("contact.html", {
                "request": request,
                "error": "お問い合わせを送信できません。SMTP設定を確認してください。"
            })

        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = SMTP_USER
        msg['Subject'] = f"【お問い合わせ】{subject}"
        
        # メール本文
        msg.attach(MIMEText(email_body, 'plain'))
        
        # SMTPサーバーへの接続と送信
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()

        print("--------------------------------------------------")
        print("【メール送信完了】")
        print(f"To: {SMTP_USER}")
        print("--------------------------------------------------")

        return templates.TemplateResponse("contact.html", {
            "request": request,
            "success": True
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse("contact.html", {
            "request": request,
            "error": f"送信中にエラーが発生しました: {str(e)}"
        })

@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    # ファイル検証
    if not file.content_type or not file.content_type.startswith("video/"):
        return templates.TemplateResponse("upload.html", {
            "request": request, 
            "error": "動画ファイルのみアップロード可能です。"
        })
    if not file.filename or not is_allowed_extension(file.filename):
        return templates.TemplateResponse("upload.html", {
            "request": request,
            "error": "対応形式は MP4 / MOV / M4V / AVI / MKV のみです。"
        })

    # 一意なID生成
    process_id = str(uuid.uuid4())
    filename = f"{process_id}_{file.filename}"
    input_path = UPLOAD_DIR / filename
    
    # ファイル保存 + サイズチェック
    try:
        save_upload_file(file, input_path)
    except ValueError as size_error:
        return templates.TemplateResponse("upload.html", {
            "request": request,
            "error": str(size_error)
        })
    except Exception as save_error:
        if input_path.exists():
            input_path.unlink()
        return templates.TemplateResponse("upload.html", {
            "request": request,
            "error": f"アップロードに失敗しました: {save_error}"
        })

    # 出力ファイルパス設定
    skeleton_filename = f"skeleton_{process_id}.mp4"
    overlay_filename = f"overlay_{process_id}.mp4"
    
    skeleton_path = RESULT_DIR / skeleton_filename
    overlay_path = RESULT_DIR / overlay_filename

    try:
        # 解析実行（同期的に実行して完了を待つ）
        process_video(input_path, skeleton_path, overlay_path)
        
        # バックグラウンドタスク: 入力動画は即削除
        background_tasks.add_task(os.remove, input_path)
        
        # 古いファイルのクリーンアップ
        background_tasks.add_task(cleanup_old_files, UPLOAD_DIR, UPLOAD_RETENTION_SECONDS)
        background_tasks.add_task(cleanup_old_files, RESULT_DIR, RESULT_RETENTION_SECONDS)
        
        return templates.TemplateResponse("result.html", {
            "request": request,
            "skeleton_video": f"results/{skeleton_filename}",
            "overlay_video": f"results/{overlay_filename}",
            "filename": file.filename
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        # エラー時も入力ファイルは削除を試みる
        if input_path.exists():
            os.remove(input_path)
            
        return templates.TemplateResponse("upload.html", {
            "request": request, 
            "error": f"解析中にエラーが発生しました: {str(e)}"
        })

@app.get("/download/{filename}")
async def download_video(filename: str):
    file_path = RESULT_DIR / filename
    if file_path.exists():
        return FileResponse(path=file_path, filename=filename, media_type='video/mp4')
    raise HTTPException(status_code=404, detail="File not found")

if __name__ == "__main__":
    import uvicorn
    import webbrowser
    
    # ブラウザを自動的に開く
    webbrowser.open("http://127.0.0.1:8000")
    
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
