"""
Generate a single prayer MP3 using ElevenLabs with a cloned voice.
Usage: python generate_elevenlabs.py API_KEY VOICE_ID SSML_FILE OUTPUT_MP3

ElevenLabs supports: <break>, <phoneme>, <emphasis>, <sub>, <say-as>, <p>, <s>
ElevenLabs does NOT support: <prosody> (rate/pitch/volume handled by voice settings instead)

This script strips <prosody> wrappers and sends the inner SSML content,
using ElevenLabs voice settings for stability/similarity/speed control.
"""
import requests, sys, re, os, time

DANIEL_VOICE_ID = "onwK4e9ZLuTAKqWW03F9"  # British, deep, calm

if len(sys.argv) < 4:
    print("Usage: python generate_elevenlabs.py API_KEY SSML_FILE OUTPUT.mp3 [VOICE_ID]")
    print(f"Default voice: Daniel ({DANIEL_VOICE_ID})")
    sys.exit(1)

api_key = sys.argv[1]
ssml_file = sys.argv[2]
output_mp3 = sys.argv[3]
voice_id = sys.argv[4] if len(sys.argv) > 4 else DANIEL_VOICE_ID

with open(ssml_file, "r") as f:
    ssml_text = f.read()

# ElevenLabs doesn't support <prosody> — strip the wrapper but keep inner content
# The slow/soft/low-pitch effect is achieved via voice_settings instead
ssml_text = re.sub(r'<prosody[^>]*>', '', ssml_text)
ssml_text = ssml_text.replace('</prosody>', '')

url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
headers = {
    "xi-api-key": api_key,
    "Content-Type": "application/json",
}

payload = {
    "text": ssml_text,
    "model_id": "eleven_multilingual_v2",
    "voice_settings": {
        "stability": 0.75,          # higher = more consistent, calmer
        "similarity_boost": 0.85,    # high similarity to source voice
        "style": 0.15,               # low style exaggeration for reverent tone
        "use_speaker_boost": True,
        "speed": 0.85,               # slightly slower than normal
    },
}

max_retries = 5
for attempt in range(max_retries):
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 429:
        wait = 2 ** (attempt + 1)  # 2, 4, 8, 16, 32 seconds
        print(f"Rate limited on {os.path.basename(ssml_file)}, waiting {wait}s (attempt {attempt+1}/{max_retries})")
        time.sleep(wait)
        continue
    response.raise_for_status()
    break
else:
    print(f"FAILED after {max_retries} retries: {os.path.basename(ssml_file)}")
    sys.exit(1)

os.makedirs(os.path.dirname(output_mp3) or ".", exist_ok=True)
with open(output_mp3, "wb") as f:
    f.write(response.content)

print(f"Saved {output_mp3}")
