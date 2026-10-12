import os
import io
import re
import urllib.parse
import requests
from flask import Flask, request, jsonify, send_file, render_template

template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
app = Flask(__name__, template_folder=template_dir)

def is_devanagari(text: str) -> bool:
    return bool(re.search(r'[\u0900-\u097F]', text))

def get_ms_auth_token():
    """Fetches an official ephemeral authorization token from Microsoft."""
    url = "https://azure.microsoft.com/en-us/services/cognitive-services/text-to-speech/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        match = re.search(r'token:\s*"([^"]+)"', r.text)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None

def synthesize_ms_neural_male(chunk_text: str, is_hi: bool) -> bytes:
    """Synthesizes authentic Indian Male speech (Madhur for Hindi, Prabhat for English)."""
    voice_name = "hi-IN-MadhurNeural" if is_hi else "en-IN-PrabhatNeural"
    lang_code = "hi-IN" if is_hi else "en-IN"

    # 1. Official Microsoft Cognitive HTTPS Endpoint
    token = get_ms_auth_token()
    if token:
        try:
            ssml = f"<speak version='1.0' xml:lang='{lang_code}'><voice name='{voice_name}'><prosody rate='+0%'>{chunk_text}</prosody></voice></speak>"
            url = "https://eastus.tts.speech.microsoft.com/cognitiveservices/v1"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            res = requests.post(url, headers=headers, data=ssml.encode("utf-8"), timeout=15)
            if res.status_code == 200 and len(res.content) > 500:
                return res.content
        except Exception:
            pass

    # 2. High-performance public Neural Male Bridge
    try:
        encoded = urllib.parse.quote(chunk_text)
        url_bridge = f"https://api.streamelements.com/kappa/v2/speech?voice={voice_name}&text={encoded}"
        res2 = requests.get(url_bridge, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
        if res2.status_code == 200 and len(res2.content) > 500:
            return res2.content
    except Exception:
        pass

    # 3. Direct Edge TTS fallback (works reliably in local dev)
    try:
        import asyncio
        import edge_tts

        async def _run():
            comm = edge_tts.Communicate(chunk_text, voice_name)
            b = bytearray()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    b.extend(chunk["data"])
            return bytes(b)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            audio_out = loop.run_until_complete(_run())
            if audio_out and len(audio_out) > 500:
                return audio_out
        finally:
            loop.close()
    except Exception:
        pass

    return b""

def synthesize_full_text(text: str) -> bytes:
    is_hi = is_devanagari(text)
    sentences = re.split(r'([।\.\n\?\!]+)', text)
    full_audio = bytearray()
    buffer = ""

    for s in sentences:
        if not s:
            continue
        if len(buffer) + len(s) < 170:
            buffer += s
        else:
            if buffer.strip():
                part = synthesize_ms_neural_male(buffer.strip(), is_hi)
                if part:
                    full_audio.extend(part)
            buffer = s

    if buffer.strip():
        part = synthesize_ms_neural_male(buffer.strip(), is_hi)
        if part:
            full_audio.extend(part)

    return bytes(full_audio)

def parse_uploaded_file(file_storage):
    filename = file_storage.filename.lower()
    raw_bytes = file_storage.read()
    if not raw_bytes:
        return ""

    stream = io.BytesIO(raw_bytes)
    content = ""

    if filename.endswith(".pdf"):
        import pypdf
        reader = pypdf.PdfReader(stream)
        for page in reader.pages:
            t = page.extract_text()
            if t:
                content += t + "\n"
    elif filename.endswith(".docx"):
        import docx
        doc = docx.Document(stream)
        content = "\n".join([p.text for p in doc.paragraphs if p.text])
    elif filename.endswith(".doc"):
        content = "".join([chr(b) for b in raw_bytes if 32 <= b <= 126 or b in (10, 13)])

    return content.strip()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/extract-text", methods=["POST"])
def extract_text():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files['file']
    if not f or not f.filename:
        return jsonify({"error": "Empty file provided."}), 400

    fname = f.filename.lower()
    if not (fname.endswith('.pdf') or fname.endswith('.docx') or fname.endswith('.doc')):
        return jsonify({"error": "Only PDF, DOC, and DOCX files are supported."}), 400

    try:
        extracted = parse_uploaded_file(f)
        if not extracted:
            return jsonify({"error": "Document contains no readable text or is image-only."}), 400
        return jsonify({"text": extracted})
    except Exception as e:
        return jsonify({"error": f"Failed to extract document text: {str(e)}"}), 500

@app.route("/api/convert", methods=["POST"])
def convert_text():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"error": "Please enter text or upload a document."}), 400

    try:
        audio_data = synthesize_full_text(text)
        if not audio_data:
            return jsonify({"error": "Failed to synthesize speech. Please try again."}), 500

        return send_file(
            io.BytesIO(audio_data),
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="indian_male_speech.mp3"
        )
    except Exception as e:
        return jsonify({"error": f"Speech conversion failed: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)