import os
import io
import re
import asyncio
from flask import Flask, request, jsonify, send_file, render_template

template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
app = Flask(__name__, template_folder=template_dir)

def is_hindi(text: str) -> bool:
    return bool(re.search(r'[\u0900-\u097F]', text))

def synthesize_male_edge(text_chunk: str, speed_val: str) -> bytes:
    import edge_tts

    # Auto-detect Hindi vs Indian English
    is_hi = is_hindi(text_chunk)
    voice_name = "hi-IN-MadhurNeural" if is_hi else "en-IN-PrabhatNeural"

    rate_map = {
        "0.75": "-25%",
        "0.90": "-10%",
        "0.95": "-5%",
        "1.0": "+0%",
        "1.25": "+25%",
        "1.50": "+50%"
    }
    rate_str = rate_map.get(str(speed_val), "+0%")

    async def _generate():
        comm = edge_tts.Communicate(text_chunk.strip(), voice=voice_name, rate=rate_str)
        buffer = bytearray()
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                buffer.extend(chunk["data"])
        return bytes(buffer)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_generate())
    finally:
        loop.close()

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
        audio_bytes = synthesize_male_edge(text, speed)
        if not audio_bytes:
            return jsonify({"error": "Failed to synthesize speech."}), 500

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