#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/transcribe.sh "/path/to/file.mp3" [model]
#
# Examples:
#   ./scripts/transcribe.sh "$HOME/Downloads/myfile.mp3" large
#   ./scripts/transcribe.sh "$HOME/Downloads/myfile.mp3" small.en

AUDIO="${1:-}"
MODEL="${2:-large}"
OUTDIR="${HOME}/Desktop/Transcripts"

if [[ -z "${AUDIO}" ]]; then
  echo "ERROR: missing audio file path."
  echo "Usage: $0 \"/path/to/file.mp3\" [model]"
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ERROR: ffmpeg not found on PATH. Run: ffmpeg -version"
  exit 1
fi

mkdir -p "${OUTDIR}"

BASENAME="$(basename "${AUDIO}")"
STEM="${BASENAME%.*}"

# Max-accuracy leaning settings for CPU:
# - large model (or pass small.en for speed)
# - temperature 0
# - beam search
whisper "${AUDIO}" \
  --model "${MODEL}" \
  --language en \
  --task transcribe \
  --device cpu \
  --fp16 False \
  --temperature 0 \
  --beam_size 5 \
  --output_format srt \
  --output_dir "${OUTDIR}"

# Convert SRT to a readable text file with blank lines between subtitle blocks
sed -E '/^[0-9]+$/d; /^[0-9]{2}:[0-9]{2}:[0-9]{2},[0-9]{3} --> /d' \
  "${OUTDIR}/${STEM}.srt" | awk 'NF{print;next}{print ""}' \
  > "${OUTDIR}/${STEM}.txt"

echo "DONE:"
echo "  ${OUTDIR}/${STEM}.srt"
echo "  ${OUTDIR}/${STEM}.txt"
