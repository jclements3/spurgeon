#!/bin/bash
# Generate all 50 prayer MP3s using ElevenLabs with Daniel voice (British, deep, calm).
#
# Usage:
#   ./generate_all_elevenlabs.sh YOUR_API_KEY [PARALLEL_JOBS] [VOICE_ID]
#
# Default voice: Daniel (onwK4e9ZLuTAKqWW03F9)
# To use your cloned voice instead, pass the voice_id as the 3rd argument.

set -euo pipefail

API_KEY="${1:?Usage: $0 <API_KEY> [PARALLEL_JOBS] [VOICE_ID]}"
JOBS="${2:-4}"
VOICE_ID="${3:-}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SSML_DIR="$SCRIPT_DIR/../ssml"
MP3_DIR="$SCRIPT_DIR/../mp3"

mkdir -p "$MP3_DIR"

echo "Generating 50 MP3s ($JOBS parallel jobs)..."
echo "Output: $MP3_DIR/"

for ssml in "$SSML_DIR"/*.ssml; do
    base=$(basename "$ssml" .ssml)
    if [ -n "$VOICE_ID" ]; then
        echo "python3 $SCRIPT_DIR/generate_elevenlabs.py $API_KEY $ssml $MP3_DIR/${base}.mp3 $VOICE_ID"
    else
        echo "python3 $SCRIPT_DIR/generate_elevenlabs.py $API_KEY $ssml $MP3_DIR/${base}.mp3"
    fi
done | xargs -P "$JOBS" -I {} bash -c '{}'

echo ""
echo "Done. $(ls "$MP3_DIR"/*.mp3 2>/dev/null | wc -l) MP3s generated in $MP3_DIR/"
