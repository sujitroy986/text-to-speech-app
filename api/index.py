import os
import io
import asyncio
from flask import Flask, request, jsonify, send_file, render_template

template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
app = Flask(__name__, template_folder=template_dir)

VOICE_MAP = {
    "hi-IN-MadhurNeural": "hi-IN-MadhurNeural",
    "hi-IN-SwaraNeural": "hi-IN-SwaraNeural",
    "en-IN-PrabhatNeural": "en-IN-PrabhatNeural",
    "en-IN-NeerjaNeural": "en-IN-NeerjaNeural",
    # Backward compatibility keys
    "hi_male": "hi-IN-MadhurNeural",
    "hi_female": "hi-IN-SwaraNeural",
    "en_male": "en-IN-PrabhatNeural",
    "en_female": "en-IN-NeerjaNeural",
}

async def synthesize_speech(text: str, voice: str, rate: str) -> bytes:
    import edge_tts
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    buffer = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buffer.extend(chunk["data"])
    return bytes(buffer)

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
    voice_param = data.get("voice", "hi-IN-MadhurNeural")
    speed_param = data.get("speed", "+0%")

    if not text:
        return jsonify({"error": "No text provided"}), 400

    selected_voice = VOICE_MAP.get(voice_param, "hi-IN-MadhurNeural")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            audio_bytes = loop.run_until_complete(
                synthesize_speech(text, selected_voice, speed_param)
            )
        finally:
            loop.close()

        if not audio_bytes:
            return jsonify({"error": "Empty audio stream returned from synthesizer."}), 500

        return send_file(
            io.BytesIO(audio_bytes),
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="speech.mp3"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)