import os
import io
import re
import urllib.parse
import requests
from flask import Flask, request, jsonify, send_file, render_template

template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
app = Flask(__name__, template_folder=template_dir)

def is_hindi(text: str) -> bool:
    return bool(re.search(r'[\u0900-\u097F]', text))

def synthesize_polly_male(text_chunk: str, speed_val: float) -> bytes:
    clean_text = text_chunk.strip()
    if not clean_text:
        return b""

    # Strip out any stray XML/SSML tags so nothing extra is spoken out loud
    clean_text = re.sub(r'<[^>]+>', '', clean_text)

    is_hi = is_hindi(clean_text)
    
    # Aditi handles Hindi fluently; Matthew/Brian handles English
    voice_id = "Aditi" if is_hi else "Matthew"

    # Primary: Amazon Polly Neural speech endpoint (expects clean, raw text)
    endpoint = "https://streamlabs.com/polly/speak"
    payload = {
        "voice": voice_id,
        "text": clean_text
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://streamlabs.com/"
    }

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=15)
        if res.status_code == 200:
            data = res.json()
            speak_url = data.get("speak_url")
            if speak_url:
                audio_res = requests.get(speak_url, headers=headers, timeout=15)
                if audio_res.status_code == 200 and len(audio_res.content) > 300:
                    return audio_res.content
    except Exception:
        pass

    # Secondary fallback with plain clean text
    try:
        enc_text = urllib.parse.quote(clean_text)
        fallback_url = f"https://api.streamelements.com/kappa/v2/speech?voice=Brian&text={enc_text}"
        res_fb = requests.get(fallback_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
        if res_fb.status_code == 200 and len(res_fb.content) > 300:
            return res_fb.content
    except Exception:
        pass

    raise RuntimeError("Speech service temporarily busy. Please retry.")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/convert", methods=["POST"])
def convert():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    speed = float(data.get("speed", 1.0))

    if not text:
        return jsonify({"error": "No text provided."}), 400

    try:
        audio_bytes = synthesize_polly_male(text, speed)
        return send_file(
            io.BytesIO(audio_bytes),
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="natural_male_speech.mp3"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)