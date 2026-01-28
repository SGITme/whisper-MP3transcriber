# Whisper MP3 Transcriber

A full-featured audio transcription service powered by OpenAI's Whisper. Includes a web interface, CLI tool, and folder watcher for automatic transcription.

## Features

- **Web Interface** - Drag-and-drop file upload with real-time progress
- **CLI Tool** - Batch transcribe files from the command line
- **Folder Watch** - Automatically transcribe files dropped into a folder
- **Multiple Models** - Choose from tiny (fast) to large (accurate)
- **Output Formats** - Export as TXT, SRT, VTT, or JSON
- **GPU Support** - Auto-detects CUDA/MPS for faster processing

## Installation

### Prerequisites

- Python 3.9+
- ffmpeg (required by Whisper)

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows (with Chocolatey)
choco install ffmpeg
```

### Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/whisper-MP3transcriber.git
cd whisper-MP3transcriber

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

**Note:** The first run will download the Whisper model (~3GB for `large`). Use `tiny` or `base` for faster downloads and testing.

## Quick Start

### Web UI

```bash
python run.py
```

Open http://localhost:8000 in your browser.

### CLI

```bash
# Transcribe a single file
python run.py --cli audio.mp3

# Transcribe multiple files
python run.py --cli *.mp3

# Use a faster model
python run.py --cli audio.mp3 --model small

# Custom output directory
python run.py --cli audio.mp3 --output ~/transcripts
```

### Folder Watch

```bash
# Watch the default ./watch folder
python run.py --watch ./watch

# Watch a custom folder
python run.py --watch ~/Desktop/ToTranscribe
```

Drop audio files into the watched folder and transcriptions will appear in `./output`.

## Configuration Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--port` | `-p` | 8000 | Web server port |
| `--host` | | 127.0.0.1 | Web server host |
| `--model` | `-m` | large | Whisper model (tiny/base/small/medium/large/large-v2/large-v3) |
| `--output` | `-o` | ./output | Output directory |
| `--format` | `-f` | txt,srt | Output formats (comma-separated) |
| `--language` | `-l` | auto | Language code (e.g., 'en', 'es', 'fr') |

## API Reference

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Web UI |
| POST | `/api/transcribe` | Upload and transcribe file |
| POST | `/api/transcribe/batch` | Upload multiple files |
| GET | `/api/jobs` | List all jobs |
| GET | `/api/jobs/{id}` | Get job status |
| GET | `/api/jobs/{id}/download/{format}` | Download result |
| DELETE | `/api/jobs/{id}` | Delete job |
| GET | `/api/models` | List available models |
| GET | `/api/formats` | List supported formats |
| POST | `/api/watch/start` | Start folder watcher |
| POST | `/api/watch/stop` | Stop folder watcher |
| GET | `/api/watch/status` | Watcher status |
| WS | `/ws` | WebSocket for real-time updates |

### Example: Upload via curl

```bash
curl -X POST "http://localhost:8000/api/transcribe" \
  -F "file=@audio.mp3" \
  -F "model=large" \
  -F "output_formats=txt,srt"
```

## Output Formats

### TXT (Plain Text)
Clean transcript without timestamps.

### SRT (SubRip Subtitle)
```
1
00:00:00,000 --> 00:00:05,240
Hello, welcome to the podcast.

2
00:00:05,240 --> 00:00:10,480
Today we're discussing transcription.
```

### VTT (WebVTT)
```
WEBVTT

00:00:00.000 --> 00:00:05.240
Hello, welcome to the podcast.

00:00:05.240 --> 00:00:10.480
Today we're discussing transcription.
```

### JSON
Full structured output with segments, timestamps, and metadata.

## Whisper Models

| Model | Size | Speed | Quality | VRAM |
|-------|------|-------|---------|------|
| tiny | 39M | Fastest | Lower | ~1GB |
| base | 74M | Fast | OK | ~1GB |
| small | 244M | Medium | Good | ~2GB |
| medium | 769M | Slow | Better | ~5GB |
| large | 1550M | Slowest | Best | ~10GB |

**Recommendations:**
- Quick transcription: `tiny` or `base`
- Balance of speed/quality: `small`
- Best accuracy: `large` (default)

## Python Module Usage

```python
from app.transcriber import WhisperTranscriber

# Initialize
transcriber = WhisperTranscriber(
    model="large",
    output_dir="./output",
    language="en"
)

# Single file
result = transcriber.transcribe("audio.mp3", output_formats=["txt", "srt"])
print(result.text)

# Batch processing
results = transcriber.transcribe_batch(
    ["file1.mp3", "file2.mp3"],
    output_formats=["txt"]
)

# With progress callback
def on_progress(progress, message):
    print(f"{progress*100:.0f}% - {message}")

result = transcriber.transcribe("audio.mp3", progress_callback=on_progress)
```

## Troubleshooting

### "No module named 'whisper'"
```bash
pip install openai-whisper
```

### "ffmpeg not found"
Install ffmpeg (see Installation section).

### Out of memory
Use a smaller model:
```bash
python run.py --cli audio.mp3 --model tiny
```

### Slow on CPU
Whisper is CPU-intensive. For faster processing:
- Use a smaller model (`tiny`, `base`, `small`)
- Use GPU if available (CUDA or Apple Silicon MPS)

### Model download hangs
Models are cached in `~/.cache/whisper/`. Delete and retry if corrupted:
```bash
rm -rf ~/.cache/whisper/
python run.py --cli test.mp3 --model tiny
```

## Legacy Shell Script

The original shell script is preserved at `scripts/transcribe.sh`:

```bash
./scripts/transcribe.sh /path/to/audio.mp3 large
```

## Project Structure

```
whisper-MP3transcriber/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI application
│   ├── transcriber.py   # Core transcription logic
│   ├── watcher.py       # Folder monitoring
│   └── static/
│       ├── index.html   # Web UI
│       ├── style.css
│       └── app.js
├── scripts/
│   └── transcribe.sh    # Legacy shell script
├── output/              # Transcription outputs
├── watch/               # Watched folder
├── run.py               # Entry point
├── requirements.txt
├── README.md
└── .gitignore
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

MIT License - See LICENSE file for details.

## Acknowledgments

- [OpenAI Whisper](https://github.com/openai/whisper) - Speech recognition model
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [Watchdog](https://github.com/gorakhargosh/watchdog) - File system monitoring
