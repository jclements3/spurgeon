#!/usr/bin/env python3
"""Generate MP3 for Openness (18) via Google Cloud TTS."""

import sys
from pathlib import Path

from google.cloud import texttospeech


def main():
    if len(sys.argv) < 2:
        print("Usage: generate_18.py <API_KEY>")
        sys.exit(1)

    api_key = sys.argv[1]

    ssml_path = Path(__file__).resolve().parent.parent / "ssml" / "18_Openness.ssml"
    output_path = Path(__file__).resolve().parent.parent / "mp3" / "18_Openness.mp3"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ssml_content = ssml_path.read_text(encoding="utf-8")

    client = texttospeech.TextToSpeechClient(
        client_options={"api_key": api_key}
    )

    synthesis_input = texttospeech.SynthesisInput(ssml=ssml_content)

    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name="en-US-Wavenet-D",
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
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
