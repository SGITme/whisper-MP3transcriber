#!/usr/bin/env python3
"""
Whisper Transcriber - Entry point

Usage:
    python run.py              # Start web server on port 8000
    python run.py --port 3000  # Start on custom port
    python run.py --cli file.mp3  # CLI mode - transcribe a file
    python run.py --watch ./folder  # Watch mode - monitor folder
"""

import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Whisper Transcriber - Audio transcription service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                      Start web UI on http://localhost:8000
  python run.py --port 3000          Start on port 3000
  python run.py --cli audio.mp3      Transcribe single file
  python run.py --cli *.mp3          Transcribe multiple files
  python run.py --watch ./folder     Watch folder for new files
        """
    )

    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8000,
        help="Port for web server (default: 8000)"
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)"
    )

    parser.add_argument(
        "--cli",
        nargs="+",
        metavar="FILE",
        help="CLI mode: transcribe audio file(s)"
    )

    parser.add_argument(
        "--watch",
        metavar="DIR",
        help="Watch mode: monitor directory for new audio files"
    )

    parser.add_argument(
        "--model", "-m",
        default="large",
        choices=["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"],
        help="Whisper model to use (default: large)"
    )

    parser.add_argument(
        "--output", "-o",
        default="./output",
        help="Output directory for transcriptions (default: ./output)"
    )

    parser.add_argument(
        "--format", "-f",
        default="txt,srt",
        help="Output formats, comma-separated (default: txt,srt)"
    )

    parser.add_argument(
        "--language", "-l",
        help="Language code (e.g., 'en'). Auto-detect if not specified"
    )

    args = parser.parse_args()

    # Parse output formats
    output_formats = [f.strip() for f in args.format.split(",")]

    if args.cli:
        # CLI mode - transcribe files
        run_cli(args.cli, args.model, args.output, output_formats, args.language)

    elif args.watch:
        # Watch mode - monitor folder
        run_watch(args.watch, args.model, args.output, output_formats)

    else:
        # Web server mode
        run_server(args.host, args.port)


def run_cli(files, model, output_dir, formats, language):
    """Run in CLI mode to transcribe files."""
    from app.transcriber import WhisperTranscriber

    print(f"Whisper Transcriber CLI")
    print(f"Model: {model}")
    print(f"Output: {output_dir}")
    print(f"Formats: {', '.join(formats)}")
    print()

    transcriber = WhisperTranscriber(
        model=model,
        output_dir=output_dir,
        language=language
    )

    print(f"Device: {transcriber.device}")
    print()

    for filepath in files:
        path = Path(filepath)
        if not path.exists():
            print(f"[ERROR] File not found: {filepath}")
            continue

        if path.suffix.lower() not in transcriber.get_supported_formats():
            print(f"[SKIP] Unsupported format: {filepath}")
            continue

        print(f"[PROCESSING] {path.name}")

        def progress_callback(progress, message):
            bar_len = 30
            filled = int(bar_len * progress)
            bar = "=" * filled + "-" * (bar_len - filled)
            print(f"\r  [{bar}] {progress*100:5.1f}% - {message}", end="", flush=True)

        try:
            result = transcriber.transcribe(str(path), formats, progress_callback)
            print(f"\n[DONE] {path.name}")
            print(f"  Language: {result.language}")
            print(f"  Duration: {result.duration:.1f}s")
            print(f"  Text length: {len(result.text)} chars")
            print()
        except Exception as e:
            print(f"\n[ERROR] {path.name}: {e}")
            print()

    print("Complete.")


def run_watch(watch_dir, model, output_dir, formats):
    """Run in watch mode to monitor a folder."""
    from app.watcher import start_watching

    print(f"Whisper Transcriber - Watch Mode")
    print(f"Watching: {watch_dir}")
    print(f"Model: {model}")
    print(f"Output: {output_dir}")
    print(f"Formats: {', '.join(formats)}")
    print()
    print("Press Ctrl+C to stop")
    print()

    observer = start_watching(
        watch_dir=watch_dir,
        output_dir=output_dir,
        model=model,
        output_formats=formats,
        move_completed=True
    )

    try:
        while observer.is_alive():
            observer.join(timeout=1)
    except KeyboardInterrupt:
        print("\nStopping...")
        from app.watcher import stop_watching
        stop_watching()


def run_server(host, port):
    """Run the web server."""
    import uvicorn

    print(f"Whisper Transcriber Web UI")
    print(f"Starting server at http://{host}:{port}")
    print()

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
