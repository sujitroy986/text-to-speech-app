import os
import io
import re
import asyncio
import urllib.parse
import requests
from flask import Flask, request, jsonify, send_file, render_template

template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
app = Flask(__name__, template_folder=template_dir)

def is_hindi(text: str) -> bool:
    return bool(re.search(r'[\u0900-\u097F]', text))

def synthesize_male_audio(text_chunk: str, speed_val: str) -> bytes:
    clean_text = text_chunk.strip()
    if not clean_text or len(clean_text) < 2:
        return b""

    is_hi = is_hindi(clean_text)
    voice_name = "hi-IN-MadhurNeural" if is_hi else "en-IN-PrabhatNeural"

    rate_map = {
        "0.75": "-25%",
        "0.90": "-10%",
        "0.95": "-5%",
        "1.0": "+0%",
        "1.25": "+25%",
        "1.50": "+50%"
    }
    rate_str = rate_map.get(str(speed_val), "+0%")

    # Engine 1: Edge-TTS Native Python (Reliable locally & with residential/proxied IPs)
    try:
        import edge_tts

        async def _run():
            comm = edge_tts.Communicate(clean_text, voice=voice_name, rate=rate_str)
            buf = bytearray()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    buf.extend(chunk["data"])
            return bytes(buf)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            res_audio = loop.run_until_complete(_run())
            if res_audio and len(res_audio) > 300:
                return res_audio
        finally:
            loop.close()
    except Exception:
        pass

    # Engine 2: StreamElements Indian Male Bridge (Python HTTP server call - NO CORS restriction)
    try:
        enc_text = urllib.parse.quote(clean_text)
        url_se = f"https://api.streamelements.com/kappa/v2/speech?voice={voice_name}&text={enc_text}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        r_se = requests.get(url_se, headers=headers, timeout=12)
        if r_se.status_code == 200 and len(r_se.content) > 300:
            return r_se.content
    except Exception:
        pass

    # Engine 3: Azure Cognitive REST Token Negotiation
    try:
        token_url = "https://azure.microsoft.com/en-us/services/cognitive-services/text-to-speech/"
        tok_res = requests.get(token_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        match = re.search(r'token:\s*"([^"]+)"', tok_res.text)
        if match:
            tok = match.group(1)
            lang_code = "hi-IN" if is_hi else "en-IN"
            escaped = clean_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            ssml = f"<speak version='1.0' xml:lang='{lang_code}'><voice name='{voice_name}'><prosody rate='{rate_str}'>{escaped}</prosody></voice></speak>"
            endpoint = "https://eastus.tts.speech.microsoft.com/cognitiveservices/v1"
            headers_ms = {
                "Authorization": f"Bearer {tok}",
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
                "User-Agent": "Mozilla/5.0"
            }
            res_ms = requests.post(endpoint, headers=headers_ms, data=ssml.encode("utf-8"), timeout=10)
            if res_ms.status_code == 200 and len(res_ms.content) > 300:
                return res_ms.content
    except Exception:
        pass

    return b""

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/convert", methods=["POST"])
def convert():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    speed = str(data.get("speed", "1.0"))

    if not text:
        return jsonify({"error": "No text provided."}), 400

    audio_bytes = synthesize_male_audio(text, speed)
    if not audio_bytes:
        return jsonify({"error": "Speech engine unavailable. Please try again."}), 500

    return send_file(
        io.BytesIO(audio_bytes),
        mimetype="audio/mpeg",
        as_attachment=False,
        download_name="indian_male_speech.mp3"
    )

if __name__ == "__main__":
    app.run(debug=True, port=5000)