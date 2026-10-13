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

def get_ms_token() -> str:
    """Retrieves an official Microsoft Cognitive session token."""
    url = "https://azure.microsoft.com/en-us/services/cognitive-services/text-to-speech/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=6)
        match = re.search(r'token:\s*"([^"]+)"', res.text)
        if match:
            return match.group(1)
    except Exception:
        pass
    return ""

def synthesize_male_neural(text_chunk: str, speed_val: str) -> bytes:
    """Synthesizes authentic Indian Male speech using HTTPS REST, immune to datacenter bans."""
    is_hi = is_hindi(text_chunk)
    voice_name = "hi-IN-MadhurNeural" if is_hi else "en-IN-PrabhatNeural"
    lang_code = "hi-IN" if is_hi else "en-IN"

    rate_map = {
        "0.75": "-25%",
        "0.90": "-10%",
        "0.95": "-5%",
        "1.0": "+0%",
        "1.25": "+25%",
        "1.50": "+50%"
    }
    rate_str = rate_map.get(str(speed_val), "+0%")
    clean_text = text_chunk.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Method 1: Official Microsoft Cognitive REST Endpoint (Works directly on Vercel)
    token = get_ms_token()
    if token:
        try:
            ssml = f"<speak version='1.0' xml:lang='{lang_code}'><voice name='{voice_name}'><prosody rate='{rate_str}'>{clean_text}</prosody></voice></speak>"
            url = "https://eastus.tts.speech.microsoft.com/cognitiveservices/v1"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            resp = requests.post(url, headers=headers, data=ssml.encode("utf-8"), timeout=12)
            if resp.status_code == 200 and len(resp.content) > 300:
                return resp.content
        except Exception:
            pass

    # Method 2: Public Neural Mirror with explicit Indian Male Voice target
    try:
        url_mirror = "https://tts.cyzon.us/api/tts"
        payload = {"text": text_chunk.strip(), "voice": voice_name, "rate": rate_str}
        r = requests.post(url_mirror, json=payload, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200 and len(r.content) > 300:
            return r.content
    except Exception:
        pass

    # Method 3: StreamElements Neural Male Pipeline
    try:
        enc = urllib.parse.quote(text_chunk.strip())
        url_se = f"https://api.streamelements.com/kappa/v2/speech?voice={voice_name}&text={enc}"
        r_se = requests.get(url_se, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r_se.status_code == 200 and len(r_se.content) > 300:
            return r_se.content
    except Exception:
        pass

    # Method 4: Local Edge-TTS (only triggers when running on localhost)
    try:
        import asyncio
        import edge_tts

        async def _run():
            comm = edge_tts.Communicate(text_chunk.strip(), voice=voice_name, rate=rate_str)
            buf = bytearray()
            async for ch in comm.stream():
                if ch["type"] == "audio":
                    buf.extend(ch["data"])
            return bytes(buf)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()
    except Exception:
        pass

    return b""

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/convert", methods=["POST"])
def convert_text():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    speed = str(data.get("speed", "1.0"))

    if not text:
        return jsonify({"error": "Please enter or import text."}), 400

    try:
        audio_bytes = synthesize_male_neural(text, speed)
        if not audio_bytes:
            return jsonify({"error": "Unable to synthesize speech. Please try again."}), 500

        return send_file(
            io.BytesIO(audio_bytes),
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="indian_male_speech.mp3"
        )
    except Exception as e:
        return jsonify({"error": f"Synthesis error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)