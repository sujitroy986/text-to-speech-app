import os
import io
import asyncio
from flask import Flask, request, jsonify, send_file, render_template

template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
app = Flask(__name__, template_folder=template_dir)

VOICE_MAP = {
    "hi_male": "hi-IN-MadhurNeural",
    "hi_female": "hi-IN-SwaraNeural",
    "en_male": "en-IN-PrabhatNeural",
    "en_female": "en-IN-NeerjaNeural",
}

RATE_MAP = {
    "0.75x": "-25%",
    "1.0x": "+0%",
    "1.25x": "+25%",
    "1.5x": "+50%"
}

# Fallback mapper for Google TTS if Microsoft Edge blocks cloud IP
GTTS_LANG_MAP = {
    "hi_male": ("hi", "co.in"),
    "hi_female": ("hi", "co.in"),
    "en_male": ("en", "co.in"),
    "en_female": ("en", "co.in")
}

async def synthesize_edge_tts(text: str, voice: str, rate: str) -> bytes:
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    audio_buffer = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_buffer.extend(chunk["data"])
    return bytes(audio_buffer)

def synthesize_gtts_fallback(text: str, voice_key: str, speed_key: str) -> bytes:
    from gtts import gTTS
    lang, tld = GTTS_LANG_MAP.get(voice_key, ("en", "co.in"))
    is_slow = True if speed_key == "0.75x" else False
    
    tts = gTTS(text=text, lang=lang, tld=tld, slow=is_slow)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp.read()

def extract_text_from_file(file_storage):
    filename = file_storage.filename.lower()
    content = ""
    if filename.endswith(".pdf"):
        import pypdf
        reader = pypdf.PdfReader(file_storage.stream)
        for page in reader.pages:
            text = page.extract_text()
            if text:
                content += text + "\n"
    elif filename.endswith(".docx"):
        import docx
        doc = docx.Document(file_storage.stream)
        content = "\n".join([para.text for para in doc.paragraphs if para.text])
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
    file = request.files['file']
    if not file or not file.filename:
        return jsonify({"error": "Empty file selection"}), 400
    
    filename = file.filename.lower()
    if not (filename.endswith('.pdf') or filename.endswith('.docx') or filename.endswith('.doc')):
        return jsonify({"error": "Only PDF, DOC, and DOCX files are supported."}), 400

    try:
        extracted = extract_text_from_file(file)
        if not extracted:
            return jsonify({"error": "No readable text found in document."}), 400
        return jsonify({"text": extracted})
    except Exception as e:
        return jsonify({"error": f"Failed to parse document: {str(e)}"}), 500

@app.route("/api/convert", methods=["POST"])
def convert_text():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    voice_key = data.get("voice", "hi_male").lower()
    speed_key = data.get("speed", "1.0x").lower()

    if not text:
        return jsonify({"error": "No text provided"}), 400

    selected_voice = VOICE_MAP.get(voice_key, VOICE_MAP["hi_male"])
    selected_rate = RATE_MAP.get(speed_key, "+0%")
    audio_data = None

    # 1. Attempt Microsoft Edge Neural Voice
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            audio_data = loop.run_until_complete(
                synthesize_edge_tts(text, selected_voice, selected_rate)
            )
        finally:
            loop.close()
    except Exception:
        # Edge returned 403 or handshake failed on cloud IP -> use fallback
        audio_data = None

    # 2. Seamless Fallback to Indian Voice HTTP Engine if Edge is blocked
    if not audio_data:
        try:
            audio_data = synthesize_gtts_fallback(text, voice_key, speed_key)
        except Exception as e:
            return jsonify({"error": f"Speech engine failed: {str(e)}"}), 500

    if not audio_data:
        return jsonify({"error": "Failed to generate audio."}), 500

    return send_file(
        io.BytesIO(audio_data),
        mimetype="audio/mpeg",
        as_attachment=False,
        download_name="speech.mp3"
    )

if __name__ == "__main__":
    app.run(debug=True, port=5000)