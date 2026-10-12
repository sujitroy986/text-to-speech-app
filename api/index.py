import os
import io
import re
import asyncio
from flask import Flask, request, jsonify, send_file, render_template

template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
app = Flask(__name__, template_folder=template_dir)

# Authentic Indian Neural Voices
INDIAN_VOICES = {
    "male": {
        "hi": "hi-IN-MadhurNeural",
        "en": "en-IN-PrabhatNeural"
    },
    "female": {
        "hi": "hi-IN-SwaraNeural",
        "en": "en-IN-NeerjaNeural"
    }
}

RATE_MAP = {
    "0.75": "-25%",
    "1.0": "+0%",
    "1.25": "+25%",
    "1.5": "+50%"
}

def is_hindi(text: str) -> bool:
    """Detect if text contains Devanagari Hindi characters."""
    return bool(re.search(r'[\u0900-\u097F]', text))

async def generate_speech_stream(text: str, voice_name: str, rate_val: str) -> bytes:
    import edge_tts
    communicate = edge_tts.Communicate(text=text, voice=voice_name, rate=rate_val)
    audio_buffer = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_buffer.extend(chunk["data"])
    return bytes(audio_buffer)

def extract_text_from_file(file_storage):
    filename = file_storage.filename.lower()
    content = ""
    if filename.endswith(".pdf"):
        import pypdf
        reader = pypdf.PdfReader(file_storage.stream)
        for page in reader.pages:
            t = page.extract_text()
            if t:
                content += t + "\n"
    elif filename.endswith(".docx"):
        import docx
        doc = docx.Document(file_storage.stream)
        content = "\n".join([p.text for p in doc.paragraphs if p.text])
    elif filename.endswith(".doc"):
        raw = file_storage.read()
        content = "".join([chr(b) for b in raw if 32 <= b <= 126 or b in (10, 13)])
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
        return jsonify({"error": "Empty file selection"}), 400

    fname = f.filename.lower()
    if not (fname.endswith('.pdf') or fname.endswith('.docx') or fname.endswith('.doc')):
        return jsonify({"error": "Only PDF, DOC, and DOCX files are supported."}), 400

    try:
        extracted = extract_text_from_file(f)
        if not extracted:
            return jsonify({"error": "No readable text found in document."}), 400
        return jsonify({"text": extracted})
    except Exception as e:
        return jsonify({"error": f"Failed to parse document: {str(e)}"}), 500

@app.route("/api/convert", methods=["POST"])
def convert_text():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    gender = data.get("voice", "male").lower()
    speed = str(data.get("speed", "1.0"))

    if not text:
        return jsonify({"error": "Please enter text or upload a document."}), 400

    # Auto-detect language script to pick the right Indian neural voice
    lang_key = "hi" if is_hindi(text) else "en"
    voice_name = INDIAN_VOICES.get(gender, INDIAN_VOICES["male"])[lang_key]
    rate_val = RATE_MAP.get(speed, "+0%")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            audio_bytes = loop.run_until_complete(
                generate_speech_stream(text, voice_name, rate_val)
            )
        finally:
            loop.close()

        if not audio_bytes:
            return jsonify({"error": "Synthesizer returned empty stream."}), 500

        return send_file(
            io.BytesIO(audio_bytes),
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name=f"{voice_name}.mp3"
        )
    except Exception as e:
        return jsonify({"error": f"Voice synthesis error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)