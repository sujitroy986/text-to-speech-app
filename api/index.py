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

    is_hi = is_devanagari(text)
    
    # Authentic Indian Neural Voice Targets
    if gender == "male":
        voice_target = "hi-IN-MadhurNeural" if is_hi else "en-IN-PrabhatNeural"
    else:
        voice_target = "hi-IN-SwaraNeural" if is_hi else "en-IN-NeerjaNeural"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    # 1. Primary Neural Voice Relay
    try:
        encoded_query = urllib.parse.quote(text)
        url = f"https://api.streamelements.com/kappa/v2/speech?voice={voice_target}&text={encoded_query}"
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code == 200 and len(resp.content) > 500:
            return send_file(
                io.BytesIO(resp.content),
                mimetype="audio/mpeg",
                as_attachment=False,
                download_name=f"{voice_target}.mp3"
            )
    except Exception:
        pass

    # 2. Secondary Neural Voice Mirror
    try:
        rate_val = {"0.75": "-25%", "1.0": "+0%", "1.25": "+25%", "1.5": "+50%"}.get(speed, "+0%")
        backup_url = "https://tts.cyzon.us/api/tts"
        payload = {"text": text, "voice": voice_target, "rate": rate_val}
        resp2 = requests.post(backup_url, json=payload, headers=headers, timeout=12)
        if resp2.status_code == 200 and len(resp2.content) > 500:
            return send_file(
                io.BytesIO(resp2.content),
                mimetype="audio/mpeg",
                as_attachment=False,
                download_name=f"{voice_target}.mp3"
            )
    except Exception:
        pass

    # 3. Graceful Regional Failover
    try:
        lang_code = "hi" if is_hi else "en-IN"
        google_url = f"https://translate.google.co.in/translate_tts?ie=UTF-8&q={urllib.parse.quote(text[:250])}&tl={lang_code}&total=1&idx=0&textlen={len(text[:250])}&client=tw-ob"
        resp3 = requests.get(google_url, headers=headers, timeout=10)
        if resp3.status_code == 200 and len(resp3.content) > 500:
            return send_file(
                io.BytesIO(resp3.content),
                mimetype="audio/mpeg",
                as_attachment=False,
                download_name="speech.mp3"
            )
    except Exception as e:
        return jsonify({"error": f"Speech generation error: {str(e)}"}), 500

    return jsonify({"error": "Unable to synthesize speech. Please try again."}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)