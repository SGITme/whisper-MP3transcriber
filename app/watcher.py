"""Folder monitoring service for automatic transcription."""

import os
import time
import shutil
import threading
from pathlib import Path
from typing import Optional, Set

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

from .transcriber import WhisperTranscriber


class TranscriptionHandler(FileSystemEventHandler):
    """Handle file creation events for automatic transcription."""

    def __init__(
        self,
        output_dir: str,
        model: str = "large",
        output_formats: Optional[list] = None,
        move_completed: bool = True
    ):
        self.output_dir = Path(output_dir)
        self.model = model
        self.output_formats = output_formats or ["txt", "srt"]
        self.move_completed = move_completed
        self.transcriber: Optional[WhisperTranscriber] = None
        self.processing: Set[str] = set()
        self.completed_dir: Optional[Path] = None
        self._lock = threading.Lock()

    def _get_transcriber(self) -> WhisperTranscriber:
        """Lazy load transcriber."""
        if self.transcriber is None:
            self.transcriber = WhisperTranscriber(
                model=self.model,
                output_dir=str(self.output_dir)
            )
        return self.transcriber

    def _is_audio_file(self, path: Path) -> bool:
        """Check if file is a supported audio format."""
        return path.suffix.lower() in WhisperTranscriber.get_supported_formats()

    def _is_file_ready(self, path: Path, wait_time: float = 2.0) -> bool:
        """Check if file has finished being written."""
        if not path.exists():
            return False

        # Wait for file to stabilize
        initial_size = path.stat().st_size
        time.sleep(wait_time)

        if not path.exists():
            return False

        return path.stat().st_size == initial_size and initial_size > 0

    def on_created(self, event):
        """Handle file creation event."""
        if event.is_directory:
            return

        path = Path(event.src_path)

        # Skip non-audio files
        if not self._is_audio_file(path):
            return

        # Skip if already processing
        with self._lock:
            if str(path) in self.processing:
                return
            self.processing.add(str(path))

        try:
            self._process_file(path)
        finally:
            with self._lock:
                self.processing.discard(str(path))

    def _process_file(self, path: Path):
        """Process a single audio file."""
        print(f"[Watcher] Detected: {path.name}")

        # Wait for file to be fully written
        if not self._is_file_ready(path):
            print(f"[Watcher] File not ready or removed: {path.name}")
            return

        print(f"[Watcher] Transcribing: {path.name}")

        try:
            transcriber = self._get_transcriber()
            result = transcriber.transcribe(
                str(path),
                output_formats=self.output_formats
            )

            print(f"[Watcher] Completed: {path.name}")
            print(f"[Watcher] Output: {self.output_dir / path.stem}.txt")

            # Move to completed folder if enabled
            if self.move_completed:
                if self.completed_dir is None:
                    self.completed_dir = path.parent / "completed"
                    self.completed_dir.mkdir(exist_ok=True)

                dest = self.completed_dir / path.name
                shutil.move(str(path), str(dest))
                print(f"[Watcher] Moved to: {dest}")

        except Exception as e:
            print(f"[Watcher] Error processing {path.name}: {e}")


# Global watcher state
_observer: Optional[Observer] = None
_handler: Optional[TranscriptionHandler] = None


def start_watching(
    watch_dir: str,
    output_dir: str,
    model: str = "large",
    output_formats: Optional[list] = None,
    move_completed: bool = True
) -> Observer:
    """
    Start watching a folder for new audio files.

    Args:
        watch_dir: Directory to monitor
        output_dir: Directory for output files
        model: Whisper model to use
        output_formats: Output format list
        move_completed: Whether to move completed files

    Returns:
        The Observer instance
    """
    global _observer, _handler

    # Stop existing watcher if any
    stop_watching()

    watch_path = Path(watch_dir)
    watch_path.mkdir(parents=True, exist_ok=True)

    _handler = TranscriptionHandler(
        output_dir=output_dir,
        model=model,
        output_formats=output_formats,
        move_completed=move_completed
    )

    _observer = Observer()
    _observer.schedule(_handler, str(watch_path), recursive=False)
    _observer.start()

    print(f"[Watcher] Started monitoring: {watch_path}")
    print(f"[Watcher] Output directory: {output_dir}")

    return _observer


def stop_watching():
    """Stop the folder watcher."""
    global _observer, _handler

    if _observer is not None:
        _observer.stop()
        _observer.join(timeout=5)
        _observer = None
        _handler = None
        print("[Watcher] Stopped")


def is_watching() -> bool:
    """Check if watcher is active."""
    return _observer is not None and _observer.is_alive()


def get_watch_status() -> dict:
    """Get current watcher status."""
    return {
        "active": is_watching(),
        "handler": _handler is not None
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m app.watcher <watch_dir> [output_dir]")
        sys.exit(1)

    watch_dir = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "./output"

    print(f"Starting watcher on: {watch_dir}")
    print("Press Ctrl+C to stop")

    observer = start_watching(watch_dir, output_dir)

    try:
        while observer.is_alive():
            observer.join(timeout=1)
    except KeyboardInterrupt:
        stop_watching()
