"""Core transcription logic using OpenAI Whisper."""

import os
import json
import torch
import whisper
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Callable, Dict, Any
from datetime import datetime


@dataclass
class TranscriptionSegment:
    """A single segment of transcription with timing."""
    id: int
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    """Result of a transcription operation."""
    audio_path: str
    text: str
    segments: List[TranscriptionSegment] = field(default_factory=list)
    language: str = ""
    duration: float = 0.0
    model_name: str = ""
    completed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_srt(self) -> str:
        """Convert transcription to SRT subtitle format."""
        lines = []
        for seg in self.segments:
            start_time = self._format_timestamp_srt(seg.start)
            end_time = self._format_timestamp_srt(seg.end)
            lines.append(f"{seg.id}")
            lines.append(f"{start_time} --> {end_time}")
            lines.append(seg.text.strip())
            lines.append("")
        return "\n".join(lines)

    def to_vtt(self) -> str:
        """Convert transcription to WebVTT format."""
        lines = ["WEBVTT", ""]
        for seg in self.segments:
            start_time = self._format_timestamp_vtt(seg.start)
            end_time = self._format_timestamp_vtt(seg.end)
            lines.append(f"{start_time} --> {end_time}")
            lines.append(seg.text.strip())
            lines.append("")
        return "\n".join(lines)

    def _format_timestamp_srt(self, seconds: float) -> str:
        """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _format_timestamp_vtt(self, seconds: float) -> str:
        """Format seconds as VTT timestamp (HH:MM:SS.mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


class WhisperTranscriber:
    """Whisper-based audio transcription with batch processing and progress tracking."""

    AVAILABLE_MODELS = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]
    SUPPORTED_FORMATS = [".mp3", ".wav", ".m4a", ".flac", ".ogg", ".wma", ".aac", ".mp4", ".webm"]

    def __init__(
        self,
        model: str = "large",
        device: str = "auto",
        output_dir: str = "./output",
        language: Optional[str] = None,
        beam_size: int = 5,
        temperature: float = 0.0
    ):
        """
        Initialize the transcriber.

        Args:
            model: Whisper model name (tiny, base, small, medium, large, large-v2, large-v3)
            device: Device to use ('auto', 'cpu', 'cuda', 'mps')
            output_dir: Directory for output files
            language: Language code (e.g., 'en') or None for auto-detection
            beam_size: Beam search size for decoding
            temperature: Temperature for sampling (0 for deterministic)
        """
        self.model_name = model
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.language = language
        self.beam_size = beam_size
        self.temperature = temperature

        # Determine device
        if device == "auto":
            if torch.cuda.is_available():
                self.device = "cuda"
            elif torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"
        else:
            self.device = device

        self._model = None

    @property
    def model(self):
        """Lazy load the Whisper model."""
        if self._model is None:
            self._model = whisper.load_model(self.model_name, device=self.device)
        return self._model

    def transcribe(
        self,
        audio_path: str,
        output_formats: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> TranscriptionResult:
        """
        Transcribe a single audio file.

        Args:
            audio_path: Path to the audio file
            output_formats: List of output formats ('txt', 'srt', 'vtt', 'json')
            progress_callback: Callback function(progress: float, message: str)

        Returns:
            TranscriptionResult with text and segments
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if audio_path.suffix.lower() not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {audio_path.suffix}")

        if output_formats is None:
            output_formats = ["txt", "srt"]

        if progress_callback:
            progress_callback(0.0, "Loading model...")

        # Ensure model is loaded
        _ = self.model

        if progress_callback:
            progress_callback(0.1, "Transcribing audio...")

        # Transcription options
        options = {
            "beam_size": self.beam_size,
            "temperature": self.temperature,
            "fp16": self.device != "cpu",
            "task": "transcribe",
            # Anti-hallucination settings
            "condition_on_previous_text": False,  # Prevents repetition loops
            "compression_ratio_threshold": 2.4,   # Filter out repetitive segments
            "logprob_threshold": -1.0,            # Filter low-confidence outputs
            "no_speech_threshold": 0.6,           # Better silence detection
        }

        if self.language:
            options["language"] = self.language

        # Run transcription
        result = self.model.transcribe(str(audio_path), **options)

        if progress_callback:
            progress_callback(0.8, "Processing results...")

        # Build segments
        segments = []
        for i, seg in enumerate(result.get("segments", []), start=1):
            segments.append(TranscriptionSegment(
                id=i,
                start=seg["start"],
                end=seg["end"],
                text=seg["text"]
            ))

        # Calculate duration from segments
        duration = segments[-1].end if segments else 0.0

        transcription = TranscriptionResult(
            audio_path=str(audio_path),
            text=result["text"].strip(),
            segments=segments,
            language=result.get("language", self.language or "unknown"),
            duration=duration,
            model_name=self.model_name,
            completed_at=datetime.now().isoformat()
        )

        # Save output files
        stem = audio_path.stem

        if "txt" in output_formats:
            txt_path = self.output_dir / f"{stem}.txt"
            txt_path.write_text(transcription.text)

        if "srt" in output_formats:
            srt_path = self.output_dir / f"{stem}.srt"
            srt_path.write_text(transcription.to_srt())

        if "vtt" in output_formats:
            vtt_path = self.output_dir / f"{stem}.vtt"
            vtt_path.write_text(transcription.to_vtt())

        if "json" in output_formats:
            json_path = self.output_dir / f"{stem}.json"
            json_path.write_text(json.dumps(transcription.to_dict(), indent=2))

        if progress_callback:
            progress_callback(1.0, "Complete")

        return transcription

    def transcribe_batch(
        self,
        audio_paths: List[str],
        output_formats: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, int, float, str], None]] = None
    ) -> List[TranscriptionResult]:
        """
        Transcribe multiple audio files.

        Args:
            audio_paths: List of paths to audio files
            output_formats: List of output formats
            progress_callback: Callback function(file_index, total_files, progress, message)

        Returns:
            List of TranscriptionResult objects
        """
        results = []
        total = len(audio_paths)

        for i, path in enumerate(audio_paths):
            def single_callback(progress: float, message: str):
                if progress_callback:
                    progress_callback(i, total, progress, message)

            try:
                result = self.transcribe(path, output_formats, single_callback)
                results.append(result)
            except Exception as e:
                # Create error result
                results.append(TranscriptionResult(
                    audio_path=str(path),
                    text=f"Error: {str(e)}",
                    model_name=self.model_name,
                    completed_at=datetime.now().isoformat()
                ))

        return results

    @classmethod
    def get_supported_formats(cls) -> List[str]:
        """Get list of supported audio formats."""
        return cls.SUPPORTED_FORMATS.copy()

    @classmethod
    def get_available_models(cls) -> List[str]:
        """Get list of available Whisper models."""
        return cls.AVAILABLE_MODELS.copy()

    def get_device_info(self) -> Dict[str, Any]:
        """Get information about the current device configuration."""
        return {
            "device": self.device,
            "cuda_available": torch.cuda.is_available(),
            "mps_available": torch.backends.mps.is_available(),
            "model": self.model_name
        }
