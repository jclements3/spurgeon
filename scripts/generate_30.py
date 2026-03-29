#!/usr/bin/env python3
"""Generate MP3 for The Wonders Of Calvary using Google Cloud TTS."""

import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_30.py <API_KEY>")
        sys.exit(1)

    api_key = sys.argv[1]

    ssml_path = Path(__file__).resolve().parent.parent / "ssml" / "30_TheWondersOfCalvary.ssml"
    output_path = Path(__file__).resolve().parent.parent / "output" / "30_TheWondersOfCalvary.mp3"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ssml_text = ssml_path.read_text(encoding="utf-8")

    import requests

    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
    payload = {
        "input": {"ssml": ssml_text},
        "voice": {
            "languageCode": "en-GB",
            "name": "en-GB-Neural2-D",
            "ssmlGender": "MALE",
        },
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": 1.0,
            "pitch": 0.0,
        },
    }

    response = requests.post(url, json=payload)
    response.raise_for_status()

    import base64

    audio_content = base64.b64decode(response.json()["audioContent"])
    output_path.write_bytes(audio_content)
    print(f"Wrote {len(audio_content)} bytes to {output_path}")


if __name__ == "__main__":
    main()
