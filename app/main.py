"""FastAPI web application for Whisper transcription service."""

import os
import uuid
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .transcriber import WhisperTranscriber, TranscriptionResult


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TranscriptionJob(BaseModel):
    id: str
    filename: str
    status: JobStatus
    progress: float = 0.0
    message: str = ""
    created_at: str
    completed_at: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    output_formats: List[str] = ["txt", "srt"]


class TranscribeRequest(BaseModel):
    model: str = "large"
    output_formats: List[str] = ["txt", "srt"]
    language: Optional[str] = None


# Application state
app = FastAPI(title="Whisper Transcriber", version="1.0.0")
jobs: Dict[str, TranscriptionJob] = {}
transcriber: Optional[WhisperTranscriber] = None
watcher_active = False
connected_clients: List[WebSocket] = []

# Paths
BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
WATCH_DIR = BASE_DIR / "watch"
STATIC_DIR = Path(__file__).parent / "static"

# Ensure directories exist
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
WATCH_DIR.mkdir(exist_ok=True)


def get_transcriber(model: str = "large", language: Optional[str] = None) -> WhisperTranscriber:
    """Get or create transcriber instance."""
    global transcriber
    if transcriber is None or transcriber.model_name != model:
        transcriber = WhisperTranscriber(
            model=model,
            output_dir=str(OUTPUT_DIR),
            language=language
        )
    return transcriber


async def broadcast_job_update(job: TranscriptionJob):
    """Send job update to all connected WebSocket clients."""
    message = job.model_dump()
    disconnected = []
    for client in connected_clients:
        try:
            await client.send_json(message)
        except:
            disconnected.append(client)
    for client in disconnected:
        connected_clients.remove(client)


def process_transcription(job_id: str, file_path: Path, model: str, output_formats: List[str], language: Optional[str]):
    """Background task to process transcription."""
    job = jobs.get(job_id)
    if not job:
        return

    try:
        job.status = JobStatus.PROCESSING
        job.message = "Loading model..."

        def progress_callback(progress: float, message: str):
            job.progress = progress
            job.message = message
            # Note: Can't use async broadcast here, updates will be polled

        t = get_transcriber(model, language)
        result = t.transcribe(str(file_path), output_formats, progress_callback)

        job.status = JobStatus.COMPLETED
        job.progress = 1.0
        job.message = "Complete"
        job.completed_at = datetime.now().isoformat()
        job.result = result.to_dict()

    except Exception as e:
        job.status = JobStatus.FAILED
        job.error = str(e)
        job.message = f"Error: {str(e)}"

    finally:
        # Clean up uploaded file
        try:
            file_path.unlink()
        except:
            pass


# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def root():
    """Serve the web UI."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/models")
async def list_models():
    """List available Whisper models."""
    return {
        "models": WhisperTranscriber.get_available_models(),
        "default": "large"
    }


@app.get("/api/formats")
async def list_formats():
    """List supported audio formats."""
    return {
        "audio_formats": WhisperTranscriber.get_supported_formats(),
        "output_formats": ["txt", "srt", "vtt", "json"]
    }


@app.get("/api/device")
async def get_device_info():
    """Get device/hardware information."""
    t = get_transcriber()
    return t.get_device_info()


@app.post("/api/transcribe")
async def transcribe_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    model: str = "large",
    output_formats: str = "txt,srt",
    language: Optional[str] = None
):
    """Upload and transcribe a single file."""
    # Validate file extension
    ext = Path(file.filename).suffix.lower()
    if ext not in WhisperTranscriber.get_supported_formats():
        raise HTTPException(400, f"Unsupported format: {ext}")

    # Parse output formats
    formats = [f.strip() for f in output_formats.split(",")]

    # Save uploaded file
    job_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{job_id}{ext}"

    content = await file.read()
    file_path.write_bytes(content)

    # Create job
    job = TranscriptionJob(
        id=job_id,
        filename=file.filename,
        status=JobStatus.PENDING,
        created_at=datetime.now().isoformat(),
        output_formats=formats
    )
    jobs[job_id] = job

    # Start background transcription
    background_tasks.add_task(
        process_transcription,
        job_id, file_path, model, formats, language
    )

    return {"job_id": job_id, "status": job.status}


@app.post("/api/transcribe/batch")
async def transcribe_batch(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    model: str = "large",
    output_formats: str = "txt,srt",
    language: Optional[str] = None
):
    """Upload and transcribe multiple files."""
    formats = [f.strip() for f in output_formats.split(",")]
    job_ids = []

    for file in files:
        ext = Path(file.filename).suffix.lower()
        if ext not in WhisperTranscriber.get_supported_formats():
            continue  # Skip unsupported files

        job_id = str(uuid.uuid4())
        file_path = UPLOAD_DIR / f"{job_id}{ext}"

        content = await file.read()
        file_path.write_bytes(content)

        job = TranscriptionJob(
            id=job_id,
            filename=file.filename,
            status=JobStatus.PENDING,
            created_at=datetime.now().isoformat(),
            output_formats=formats
        )
        jobs[job_id] = job
        job_ids.append(job_id)

        background_tasks.add_task(
            process_transcription,
            job_id, file_path, model, formats, language
        )

    return {"job_ids": job_ids, "count": len(job_ids)}


@app.get("/api/jobs")
async def list_jobs():
    """List all transcription jobs."""
    return {"jobs": [job.model_dump() for job in jobs.values()]}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    """Get status of a specific job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job.model_dump()


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    """Cancel or delete a job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    if job.status == JobStatus.PROCESSING:
        job.status = JobStatus.CANCELLED

    del jobs[job_id]
    return {"status": "deleted"}


@app.get("/api/jobs/{job_id}/download/{format}")
async def download_result(job_id: str, format: str):
    """Download transcription result in specified format."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(400, "Job not completed")

    # Get the stem from original filename
    stem = Path(job.filename).stem

    # Find the output file
    output_file = OUTPUT_DIR / f"{stem}.{format}"
    if not output_file.exists():
        raise HTTPException(404, f"Output file not found: {format}")

    return FileResponse(
        output_file,
        filename=f"{stem}.{format}",
        media_type="application/octet-stream"
    )


@app.post("/api/watch/start")
async def start_watcher():
    """Start folder watching."""
    global watcher_active
    from .watcher import start_watching
    start_watching(str(WATCH_DIR), str(OUTPUT_DIR))
    watcher_active = True
    return {"status": "started", "path": str(WATCH_DIR)}


@app.post("/api/watch/stop")
async def stop_watcher():
    """Stop folder watching."""
    global watcher_active
    from .watcher import stop_watching
    stop_watching()
    watcher_active = False
    return {"status": "stopped"}


@app.get("/api/watch/status")
async def watcher_status():
    """Get watcher status."""
    return {
        "active": watcher_active,
        "path": str(WATCH_DIR)
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time job updates."""
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            # Send periodic updates
            for job in jobs.values():
                if job.status == JobStatus.PROCESSING:
                    await websocket.send_json(job.model_dump())
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
