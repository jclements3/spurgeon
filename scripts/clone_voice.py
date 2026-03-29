"""
Clone a voice on ElevenLabs from a voice sample.
Usage: python clone_voice.py YOUR_ELEVENLABS_API_KEY

Prints the voice_id on success — save it for generation.
Free tier: https://elevenlabs.io (sign up for API key)
"""
import requests, sys

api_key = sys.argv[1] if len(sys.argv) > 1 else None
if not api_key:
    print("Usage: python clone_voice.py YOUR_ELEVENLABS_API_KEY")
    print("Sign up free at https://elevenlabs.io to get a key.")
    sys.exit(1)

url = "https://api.elevenlabs.io/v1/voices/add"
headers = {"xi-api-key": api_key}

with open("../jimsvoice.m4a", "rb") as f:
    response = requests.post(
        url,
        headers=headers,
        data={
            "name": "Jim - Devotional",
            "description": "Jim's voice for Spurgeon prayer recordings. Reverent, contemplative tone.",
        },
        files=[("files", ("jimsvoice.m4a", f, "audio/mp4"))],
    )

response.raise_for_status()
voice_id = response.json()["voice_id"]
print(f"Voice cloned successfully!")
print(f"Voice ID: {voice_id}")
print(f"\nSave this ID. Use it with generate_all_elevenlabs.sh:")
print(f"  ./generate_all_elevenlabs.sh {api_key} {voice_id}")
