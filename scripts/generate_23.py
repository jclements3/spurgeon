import requests, base64, json, sys

SSML_FILE = "../ssml/23_SpiritualHelps.ssml"

with open(SSML_FILE, "r") as f:
    ssml_text = f.read()

api_key = sys.argv[1] if len(sys.argv) > 1 else None
if not api_key:
    print("Usage: python generate_23.py YOUR_GOOGLE_TTS_API_KEY")
    print("Or paste the SSML into https://ttsmp3.com")
    sys.exit(1)

payload = {
    "input": {"ssml": ssml_text},
    "voice": {"languageCode": "en-GB", "name": "en-GB-Neural2-D", "ssmlGender": "MALE"},
    "audioConfig": {"audioEncoding": "MP3", "speakingRate": 0.9, "pitch": -2.0}
}

url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
response = requests.post(url, json=payload)
response.raise_for_status()

output_file = "23_SpiritualHelps.mp3"
with open(output_file, "wb") as f:
    f.write(base64.b64decode(response.json()["audioContent"]))
print(f"Saved {output_file}")
