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

def fetch_male_neural_chunk(text_chunk: str, is_hi: bool) -> bytes:
    """Fetches genuine Indian Male audio chunk via neural mirrors."""
    clean_text = text_chunk.strip()
    if not clean_text or len(clean_text) < 2:
        return b""

    voice_target = "hi-IN-MadhurNeural" if is_hi else "en-IN-PrabhatNeural"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    # Gateway 1: Primary Neural Mirror
    try:
        url_mirror = "https://tts.cyzon.us/api/tts"
        payload = {"text": clean_text, "voice": voice_target, "rate": "+0%"}
        res = requests.post(url_mirror, json=payload, headers=headers, timeout=8)
        if res.status_code == 200 and len(res.content) > 300:
            return res.content
    except Exception:
        pass

    # Gateway 2: Secondary Neural Audio Relay
    try:
        enc = urllib.parse.quote(clean_text)
        url_bridge = f"https://api.streamelements.com/kappa/v2/speech?voice={voice_target}&text={enc}"
        res2 = requests.get(url_bridge, headers=headers, timeout=8)
        if res2.status_code == 200 and len(res2.content) > 300:
            return res2.content
    except Exception:
        pass

    # Gateway 3: Edge-TTS Direct (used during local execution)
    try:
        import asyncio
        import edge_tts

        async def _run():
            comm = edge_tts.Communicate(clean_text, voice_target)
            buf = bytearray()
            async for ch in comm.stream():
                if ch["type"] == "audio":
                    buf.extend(ch["data"])
            return bytes(buf)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            audio_out = loop.run_until_complete(_run())
            if audio_out and len(audio_out) > 300:
                return audio_out
        finally:
            loop.close()
    except Exception:
        pass

    return b""

def extract_document_text(file_storage):
    """Safely extracts document content in memory without closed file issues."""
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

    content = re.sub(r'[ \t]+', ' ', content)
    content = re.sub(r'\n+', '\n', content)
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
        extracted = extract_document_text(f)
        if not extracted:
            return jsonify({"error": "Document contains no readable text or is image-only."}), 400
        return jsonify({"text": extracted})
    except Exception as e:
        return jsonify({"error": f"Failed to extract document: {str(e)}"}), 500

@app.route("/api/convert", methods=["POST"])
def convert_text():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"error": "Please enter or upload text."}), 400

    is_hi = is_hindi(text)
    try:
        audio_chunk = fetch_male_neural_chunk(text, is_hi)
        if not audio_chunk:
            return jsonify({"error": "Failed to synthesize speech chunk."}), 500

        return send_file(
            io.BytesIO(audio_chunk),
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="chunk.mp3"
        )
    except Exception as e:
        return jsonify({"error": f"Synthesis error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)