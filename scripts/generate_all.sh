#!/bin/bash
# Generate all 50 MP3s from SSML files using Google Cloud TTS.
# Usage: ./generate_all.sh YOUR_GOOGLE_TTS_API_KEY
# Or to limit parallelism: ./generate_all.sh YOUR_KEY 4

set -euo pipefail

API_KEY="${1:?Usage: $0 <GOOGLE_TTS_API_KEY> [PARALLEL_JOBS]}"
JOBS="${2:-8}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Generating 50 MP3s with $JOBS parallel jobs..."

for i in $(seq -w 1 50); do
    echo "python3 $SCRIPT_DIR/generate_${i}.py $API_KEY"
done | xargs -P "$JOBS" -I {} bash -c '{}'

echo "Done. Check for MP3 files in the output directory."
