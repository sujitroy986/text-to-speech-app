import os
import io
import re
import urllib.parse
import requests
from flask import Flask, request, jsonify, send_file, render_template

template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
app = Flask(__name__, template_folder=template_dir)

def is_devanagari(text: str) -> bool:
    """Detects Hindi Devanagari script."""
    return bool(re.search(r'[\u0900-\u097F]', text))

def fetch_male_speech_chunk(sentence: str, is_hi: bool) -> bytes:
    """Fetches high-quality Indian Male neural audio without punctuation errors."""
    clean_text = sentence.strip()
    if not clean_text or len(clean_text) < 2:
        return b""

    male_voice = "hi-IN-MadhurNeural" if is_hi else "en-IN-PrabhatNeural"
    
    # Method 1: Direct Edge TTS (Executes reliably when running locally)
    try:
        import asyncio
        import edge_tts

        async def _run():
            comm = edge_tts.Communicate(clean_text, male_voice)
            buffer = bytearray()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    buffer.extend(chunk["data"])
            return bytes(buffer)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            audio = loop.run_until_complete(_run())
            if audio and len(audio) > 400:
                return audio
        finally:
            loop.close()
    except Exception:
        pass

    # Method 2: Public Neural Mirror for Cloud/Vercel
    try:
        url_mirror = "https://tts.cyzon.us/api/tts"
        payload = {"text": clean_text, "voice": male_voice, "rate": "+0%"}
        res = requests.post(
            url_mirror, 
            json=payload, 
            headers={"User-Agent": "Mozilla/5.0"}, 
            timeout=10
        )
        if res.status_code == 200 and len(res.content) > 400:
            return res.content
    except Exception:
        pass

    # Method 3: Regional Indian Audio Endpoint (Clean phrase delivery)
    try:
        tl_code = "hi" if is_hi else "en-IN"
        params = {
            "ie": "UTF-8",
            "q": clean_text,
            "tl": tl_code,
            "total": "1",
            "idx": "0",
            "textlen": str(len(clean_text)),
            "client": "tw-ob"
        }
        url_fb = "https://translate.google.co.in/translate_tts?" + urllib.parse.urlencode(params)
        res_fb = requests.get(url_fb, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if res_fb.status_code == 200 and len(res_fb.content) > 300:
            return res_fb.content
    except Exception:
        pass

    return b""

def synthesize_entire_document(text: str) -> bytes:
    """Splits document without punctuation capture tokens to avoid 'dot dot dot'."""
    is_hi = is_devanagari(text)
    
    # Split text cleanly on sentences without capturing punctuation into standalone elements
    raw_sentences = re.split(r'[।\.\n\?\!]+', text)
    sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 1]

    combined_audio = bytearray()
    accumulator = ""

    for sentence in sentences:
        if len(accumulator) + len(sentence) < 180:
            accumulator += " " + sentence if accumulator else sentence
        else:
            if accumulator:
                chunk_data = fetch_male_speech_chunk(accumulator, is_hi)
                if chunk_data:
                    combined_audio.extend(chunk_data)
            accumulator = sentence

    if accumulator:
        chunk_data = fetch_male_speech_chunk(accumulator, is_hi)
        if chunk_data:
            combined_audio.extend(chunk_data)

    return bytes(combined_audio)

def extract_document_text(file_storage):
    """Safely extracts document content on Vercel without closed file errors."""
    filename = file_storage.filename.lower()
    raw_bytes = file_storage.read()
    if not raw_bytes:
        return ""

    content = ""
    stream = io.BytesIO(raw_bytes)

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

    # Clean redundant whitespace
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
        return jsonify({"error": "Please enter text or upload a document."}), 400

    try:
        audio_data = synthesize_entire_document(text)
        if not audio_data:
            return jsonify({"error": "Speech generation failed. Please try again."}), 500

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