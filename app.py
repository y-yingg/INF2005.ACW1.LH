# app.py
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from PIL import Image
import base64
import io
import os

from stego import (
    encode_image_with_key,
    decode_image_with_key,
    make_difference_image,
    pil_to_png_bytes,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB
CORS(app, resources={r"/api/*": {"origins": ["https://y-yingg.github.io"]}})

# ---------- Data URL helper ----------
def to_data_url(mime: str, b: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(b).decode('ascii')}"

# ---------- Preview helpers ----------
def to_preview_jpeg(img: Image.Image, max_w=480, quality=70) -> str:
    """Small JPEG preview (lossy OK). Returns data URL."""
    w, h = img.size
    if w > max_w:
        img = img.resize((max_w, int(h * max_w / w)), Image.BILINEAR)
    bio = io.BytesIO()
    img.convert("RGB").save(bio, format="JPEG", quality=quality, optimize=True)
    return to_data_url("image/jpeg", bio.getvalue())

def to_preview_png_nearest(img: Image.Image, max_w=480) -> str:
    """Lossless PNG preview with NEAREST scaling (keeps diff pixels sharp)."""
    w, h = img.size
    if w > max_w:
        img = img.resize((max_w, int(h * max_w / w)), Image.NEAREST)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    return to_data_url("image/png", bio.getvalue())

# ========== ENCODE ==========
@app.post("/api/encode")
def api_encode():
    try:
        # 1) COVER (required)
        cover_file = request.files.get("cover")
        if not cover_file:
            return jsonify({"error": "Please choose a cover image."}), 400
        try:
            cover_img = Image.open(cover_file.stream).convert("RGB")
        except Exception as e:
            return jsonify({"error": f"Invalid cover image: {e}"}), 400

        # 2) KEY
        key = (request.form.get("key") or "").strip()
        if not key:
            return jsonify({"error": "Secret key is required."}), 400

        # 3) LSB
        try:
            lsb = int(request.form.get("lsb", "1"))
        except ValueError:
            return jsonify({"error": "Invalid LSB value."}), 400
        if not (1 <= lsb <= 8):
            return jsonify({"error": "LSBs must be between 1 and 8."}), 400

        # 4) PAYLOAD (file or text)
        payload_src = (request.form.get("payload_src") or "file").lower()
        payload_bytes: bytes
        payload_name: str

        if payload_src == "text":
            text = request.form.get("payload_text", "")
            if text == "":
                return jsonify({"error": "Enter the text payload."}), 400
            payload_bytes = text.encode("utf-8")
            payload_name = ""  # empty filename => text payload in old header format
        else:
            payload_file = request.files.get("payload")
            if not payload_file:
                return jsonify({"error": "Please choose a payload file."}), 400
            payload_bytes = payload_file.read()
            payload_name = secure_filename(payload_file.filename or "payload.bin")

        # 5) Optional anchor -> compose into key as "@x,y" for compatibility
        use_anchor = (request.form.get("use_anchor") or "").lower() == "yes"
        key_full = key
        if use_anchor:
            ax = (request.form.get("anchor_x") or "").strip()
            ay = (request.form.get("anchor_y") or "").strip()
            if not ax or not ay:
                return jsonify({"error": "Provide both X and Y for the anchor, or turn it off."}), 400
            try:
                ax_i = int(ax)
                ay_i = int(ay)
                if ax_i < 0 or ay_i < 0:
                    raise ValueError
            except ValueError:
                return jsonify({"error": "Anchor X/Y must be non-negative integers."}), 400
            key_full = f"{key}@{ax_i},{ay_i}"

        # 6) ENCODE
        encoded_img, orig_arr, enc_arr = encode_image_with_key(
            cover_img, payload_bytes, payload_name, key_full, lsb
        )
        diff_img = make_difference_image(orig_arr, enc_arr, lsb)

        # 7) Previews and full encoded image
        cover_preview = to_preview_jpeg(cover_img)             # small JPEG
        diff_preview = to_preview_png_nearest(diff_img)        # small PNG (NEAREST)
        encoded_png_b64 = base64.b64encode(pil_to_png_bytes(encoded_img)).decode("ascii")

        return jsonify({
            "cover_preview": cover_preview,
            "diff_preview": diff_preview,
            "encoded": f"data:image/png;base64,{encoded_png_b64}",
            "download_name": f"encoded_{payload_name or 'text'}.png"
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RequestEntityTooLarge:
        return jsonify({"error": "File too large (over server limit)."}), 413
    except Exception:
        app.logger.exception("Encode failed")
        return jsonify({"error": "Internal server error"}), 500

# ========== BASIC ==========
@app.get("/")
def home():
    return "Stego API is running. Use POST /api/encode", 200

@app.get("/api/healthz")
def healthz():
    return {"status": "ok"}, 200

# ========== DECODE ==========
def _decode_from_request():
    """Load encoded image + key, run decode, and try to render payload as image."""
    encoded = request.files.get("encoded")
    key = (request.form.get("key") or "").strip()
    if not encoded or not key:
        raise ValueError("Missing encoded image or key")

    enc_img = Image.open(encoded.stream).convert("RGB")
    meta, payload = decode_image_with_key(enc_img, key)

    decoded_img_preview_url = None
    try:
        pimg = Image.open(io.BytesIO(payload))
        decoded_img_preview_url = to_preview_jpeg(pimg)  # returns data URL
    except Exception:
        pass

    return enc_img, meta, payload, decoded_img_preview_url

@app.post("/api/decode")
def api_decode():
    try:
        enc_img, meta, payload, decoded_img_preview_url = _decode_from_request()

        # Small preview of the *input* encoded image
        enc_preview_url = to_preview_jpeg(enc_img)

        # Build meta text
        is_file = (meta.get("payload_type", 1) == 1)
        meta_lines = [
            "Decoded meta:",
            f"  Type: {'file' if is_file else 'text'}",
            f"  Name: {meta.get('name')!r}",
            f"  Size: {meta.get('size')} bytes",
            f"  Start XY (hint): {meta.get('start_xy')}",
            f"  Channel mask: {meta.get('channel_mask'):03b}",
        ]
        meta_text = "\n".join(meta_lines)

        resp = {
            "meta_text": meta_text,
            "encoded_preview": enc_preview_url,
            "download_name": f"decoded_{meta.get('name') or 'payload.bin'}",
            "payload_type": "file" if is_file else "text",
        }

        if decoded_img_preview_url is not None:
            resp["decoded_preview"] = decoded_img_preview_url
        else:
            if not is_file:
                try:
                    resp["decoded_text"] = payload.decode("utf-8")
                except UnicodeDecodeError:
                    # Not valid UTF-8; user can still download raw bytes
                    pass

        return jsonify(resp)

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RequestEntityTooLarge:
        return jsonify({"error": "File too large (over server limit)."}), 413
    except Exception:
        app.logger.exception("Decode failed")
        return jsonify({"error": "Internal server error"}), 500

@app.post("/api/decode/download")
def api_decode_download():
    """Re-run decode and stream the raw decoded payload as a file attachment."""
    try:
        _enc_img, meta, payload, _ = _decode_from_request()
        return send_file(
            io.BytesIO(payload),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=f"decoded_{meta.get('name') or 'payload.bin'}",
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RequestEntityTooLarge:
        return jsonify({"error": "File too large (over server limit)."}), 413
    except Exception:
        app.logger.exception("Decode download failed")
        return jsonify({"error": "Internal server error"}), 500
