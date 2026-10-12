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

def synthesize_indian_male(text: str, speed: str) -> bytes:
    """
    Dedicated Indian Male Voice Synthesizer.
    Auto-detects Hindi (MadhurNeural) vs Indian English (PrabhatNeural).
    """
    is_hi = is_devanagari(text)
    male_voice = "hi-IN-MadhurNeural" if is_hi else "en-IN-PrabhatNeural"
    
    rate_map = {"0.75": "-25%", "1.0": "+0%", "1.25": "+25%", "1.5": "+50%"}
    rate_val = rate_map.get(str(speed), "+0%")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    # Pipeline A: StreamElements High-Quality Neural Proxy
    try:
        encoded_query = urllib.parse.quote(text)
        url = f"https://api.streamelements.com/kappa/v2/speech?voice={male_voice}&text={encoded_query}"
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code == 200 and len(resp.content) > 600:
            return resp.content
    except Exception:
        pass

    # Pipeline B: Public Neural API Mirror
    try:
        backup_url = "https://tts.cyzon.us/api/tts"
        payload = {"text": text, "voice": male_voice, "rate": rate_val}
        resp2 = requests.post(backup_url, json=payload, headers=headers, timeout=12)
        if resp2.status_code == 200 and len(resp2.content) > 600:
            return resp2.content
    except Exception:
        pass

    # Pipeline C: Edge-TTS local fallback (when running on localhost)
    try:
        import asyncio
        import edge_tts

        async def _local_edge():
            communicate = edge_tts.Communicate(text=text, voice=male_voice, rate=rate_val)
            buf = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.extend(chunk["data"])
            return bytes(buf)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            edge_audio = loop.run_until_complete(_local_edge())
            if edge_audio and len(edge_audio) > 600:
                return edge_audio
        finally:
            loop.close()
    except Exception:
        pass

    # Pipeline D: Regional Indian Endpoint
    try:
        lang_code = "hi" if is_hi else "en-IN"
        chunk_clean = text[:240].strip()
        google_url = f"https://translate.google.co.in/translate_tts?ie=UTF-8&q={urllib.parse.quote(chunk_clean)}&tl={lang_code}&total=1&idx=0&textlen={len(chunk_clean)}&client=tw-ob"
        resp3 = requests.get(google_url, headers=headers, timeout=10)
        if resp3.status_code == 200 and len(resp3.content) > 400:
            return resp3.content
    except Exception:
        pass

    return b""

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
    speed = str(data.get("speed", "1.0"))

    if not text:
        return jsonify({"error": "Please enter text or upload a document."}), 400

    try:
        audio_data = synthesize_indian_male(text, speed=speed)
        if not audio_data:
            return jsonify({"error": "Unable to synthesize speech. Please try again."}), 500

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