#!/usr/bin/env python3
"""Generate MP3 for Grace Active using Google Cloud TTS."""

import sys
from pathlib import Path

from google.cloud import texttospeech


def main():
    if len(sys.argv) < 2:
        print("Usage: generate_11.py <api-key>", file=sys.stderr)
        sys.exit(1)

    api_key = sys.argv[1]

    ssml_path = Path(__file__).resolve().parent.parent / "ssml" / "11_GraceActive.ssml"
    output_path = ssml_path.parent.parent / "mp3" / "11_GraceActive.mp3"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ssml_content = ssml_path.read_text(encoding="utf-8")

    client = texttospeech.TextToSpeechClient(
        client_options={"api_key": api_key}
    )

    synthesis_input = texttospeech.SynthesisInput(ssml=ssml_content)

    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name="en-US-Neural2-D",
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=1.0,
        pitch=0.0,
    )

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )

    output_path.write_bytes(response.audio_content)
    print(f"Audio written to {output_path}")


if __name__ == "__main__":
    main()
