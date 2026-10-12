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

def fetch_male_chunk(chunk_text: str, is_hi: bool) -> bytes:
    """Fetch binary audio chunk for Indian Male voice with regional routing."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    voice_target = "hi-IN-MadhurNeural" if is_hi else "en-IN-PrabhatNeural"
    
    # 1. Primary Neural Proxy
    try:
        encoded = urllib.parse.quote(chunk_text.strip())
        url = f"https://api.streamelements.com/kappa/v2/speech?voice={voice_target}&text={encoded}"
        res = requests.get(url, headers=headers, timeout=12)
        if res.status_code == 200 and len(res.content) > 300:
            return res.content
    except Exception:
        pass

    # 2. Secondary Neural Mirror
    try:
        url_sec = "https://tts.cyzon.us/api/tts"
        res_sec = requests.post(url_sec, json={"text": chunk_text.strip(), "voice": voice_target, "rate": "+0%"}, headers=headers, timeout=10)
        if res_sec.status_code == 200 and len(res_sec.content) > 300:
            return res_sec.content
    except Exception:
        pass

    # 3. Fallback Regional Male Engine
    try:
        tl = "hi" if is_hi else "en-IN"
        params = {
            "ie": "UTF-8",
            "q": chunk_text.strip(),
            "tl": tl,
            "total": "1",
            "idx": "0",
            "textlen": str(len(chunk_text.strip())),
            "client": "tw-ob"
        }
        url_fb = "https://translate.google.co.in/translate_tts?" + urllib.parse.urlencode(params)
        res_fb = requests.get(url_fb, headers=headers, timeout=10)
        if res_fb.status_code == 200 and len(res_fb.content) > 200:
            return res_fb.content
    except Exception:
        pass

    return b""

def synthesize_full_text(text: str) -> bytes:
    """Splits full documents into clean natural sentences and chains the MP3 byte stream."""
    is_hi = is_devanagari(text)
    
    # Split text by sentence terminators
    sentences = re.split(r'([।\.\n\?\!]+)', text)
    full_audio = bytearray()
    current_segment = ""

    for seg in sentences:
        if not seg:
            continue
        if len(current_segment) + len(seg) < 170:
            current_segment += seg
        else:
            if current_segment.strip():
                chunk_bytes = fetch_male_chunk(current_segment.strip(), is_hi)
                if chunk_bytes:
                    full_audio.extend(chunk_bytes)
            current_segment = seg

    if current_segment.strip():
        chunk_bytes = fetch_male_chunk(current_segment.strip(), is_hi)
        if chunk_bytes:
            full_audio.extend(chunk_bytes)

    return bytes(full_audio)

def parse_uploaded_file(file_storage):
    """Safely extracts text using BytesIO to prevent closed stream errors on serverless platforms."""
    filename = file_storage.filename.lower()
    raw_bytes = file_storage.read()
    if not raw_bytes:
        return ""

    content = ""
    byte_stream = io.BytesIO(raw_bytes)

    if filename.endswith(".pdf"):
        import pypdf
        reader = pypdf.PdfReader(byte_stream)
        for page in reader.pages:
            t = page.extract_text()
            if t:
                content += t + "\n"
    elif filename.endswith(".docx"):
        import docx
        doc = docx.Document(byte_stream)
        content = "\n".join([p.text for p in doc.paragraphs if p.text])
    elif filename.endswith(".doc"):
        # Strip binary headers and retain printable characters
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
            return jsonify({"error": "Document contains no readable text or is image-based."}), 400
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