# stego.py  — encoder/decoder aligned with the "old" scheme

import io, hashlib, zlib, random
from typing import Tuple, Optional
import numpy as np
from PIL import Image

# ---------- bit helpers ----------
def bytes_to_bits(data: bytes) -> str:
    return ''.join(f'{b:08b}' for b in data)

def bits_to_bytes(bits: str) -> bytes:
    usable = len(bits) - (len(bits) % 8)
    return bytes(int(bits[i:i+8], 2) for i in range(0, usable, 8))

def set_bit_plane(byte_val: int, plane: int, bit_char: str) -> int:
    mask = 1 << plane
    return (byte_val | mask) if bit_char == '1' else (byte_val & ~mask)

def get_bit_plane(byte_val: int, plane: int) -> int:
    return (byte_val >> plane) & 1

# ---------- key → permutations ----------
def sha_int(s: str) -> int:
    return int(hashlib.sha256(s.encode('utf-8')).hexdigest(), 16)

def permutation_from_key(key_seed: str, total: int) -> list[int]:
    rng = random.Random(sha_int(key_seed))
    return rng.sample(range(total), total)

def planes_perm_from_key(key_seed: str) -> list[int]:
    planes = list(range(8))
    rng = random.Random(sha_int(key_seed + "|planes"))
    rng.shuffle(planes)
    return planes

def parse_key_with_anchor(key_str: str):
    """
    Accepts:
      'pass' → (pass, None)
      'pass@N' → (pass, (N,N))
      'pass@X,Y' or 'XxY' or 'X;Y' or 'X Y' or 'X:Y'
    """
    if '@' not in key_str:
        return key_str, None
    base, coord = key_str.split('@', 1)
    coord = coord.strip()
    if not coord:
        return base, None

    seps = [',', 'x', 'X', ';', ' ', ':']
    parts = None
    for sep in seps:
        if sep in coord:
            parts = [p for p in coord.replace(' ', '').split(sep) if p]
            break
    try:
        if parts is None:
            n = int(coord);  assert n >= 0
            return base, (n, n)
        if len(parts) == 1:
            n = int(parts[0]);  assert n >= 0
            return base, (n, n)
        x = int(parts[0]); y = int(parts[1])
        assert x >= 0 and y >= 0
        return base, (x, y)
    except Exception:
        raise ValueError("Invalid key anchor. Use pass@N or pass@X,Y (e.g., secret@64 or secret@120,45).")

# ---------- small headers ----------
BOOT_MAGIC = b"S0"
BOOT_LEN   = 2 + 2 + 1 + 11   # 16 bytes total

def build_boot_header(header_len: int, lsb_count: int) -> bytes:
    if not (1 <= lsb_count <= 8):
        raise ValueError("lsb_count must be 1..8")
    return BOOT_MAGIC + header_len.to_bytes(2, 'big') + bytes([lsb_count]) + bytes(11)

def parse_boot_header(data: bytes) -> Tuple[int,int]:
    if len(data) != BOOT_LEN or data[:2] != BOOT_MAGIC:
        raise ValueError("Boot header magic mismatch (wrong key or not a stego image).")
    header_len = int.from_bytes(data[2:4], 'big')
    lsb_count  = data[4]
    if not (1 <= lsb_count <= 8):
        raise ValueError("Corrupt boot header (invalid lsb_count).")
    return header_len, lsb_count

# MAIN header (after BOOT) — same layout as your old code
HDR_MAGIC   = b"STEG"
HDR_VERSION = 1

def build_header(payload_type: int, payload_name: str, payload: bytes,
                 start_xy: Optional[Tuple[int,int]], channel_mask: int = 0b111) -> bytes:
    name_bytes = (payload_name or "").encode('utf-8')[:255]
    name_len   = len(name_bytes)
    size       = len(payload)
    start_x    = start_xy[0] if start_xy else -1
    start_y    = start_xy[1] if start_xy else -1
    crc        = zlib.crc32(payload) & 0xFFFFFFFF
    parts = [
        HDR_MAGIC,
        bytes([HDR_VERSION]),
        bytes([payload_type]),
        bytes([name_len]),
        size.to_bytes(4, 'big'),
        int(start_x).to_bytes(4, 'big', signed=True),
        int(start_y).to_bytes(4, 'big', signed=True),
        bytes([channel_mask & 0x07]),
        bytes(2),  # reserved
        name_bytes,
        crc.to_bytes(4, 'big'),
    ]
    return b''.join(parts)

def parse_header(data: bytes) -> dict:
    if data[:4] != HDR_MAGIC:
        raise ValueError("Header magic mismatch.")
    version = data[4]
    if version != HDR_VERSION:
        raise ValueError("Unsupported header version.")
    payload_type = data[5]
    name_len = data[6]
    off = 7
    size = int.from_bytes(data[off:off+4], 'big'); off += 4
    start_x = int.from_bytes(data[off:off+4], 'big', signed=True); off += 4
    start_y = int.from_bytes(data[off:off+4], 'big', signed=True); off += 4
    channel_mask = data[off]; off += 1
    off += 2  # reserved
    name = data[off:off+name_len].decode('utf-8', errors='ignore'); off += name_len
    crc  = int.from_bytes(data[off:off+4], 'big'); off += 4
    return {
        "payload_type": payload_type,
        "name": name,
        "size": size,
        "start_xy": (start_x, start_y) if start_x >= 0 and start_y >= 0 else None,
        "channel_mask": channel_mask,
        "crc32": crc,
        "header_len": off
    }

# ---------- core ----------
def encode_image_with_key(img: Image.Image, payload: bytes, payload_name: str,
                          key_full: str, lsb_count: int):
    """Write BOOT in plane 0; MAIN+payload with plane-cycle over k LSBs."""
    base_key, anchor_xy = parse_key_with_anchor(key_full)
    arr = np.array(img.convert("RGB"), dtype=np.uint8)  # (H,W,3)
    H, W, _ = arr.shape
    flat = arr.reshape(-1)

    payload_type = 0 if (payload_name or "") == "" else 1
    main_hdr = build_header(payload_type, payload_name, payload, anchor_xy, channel_mask=0b111)
    boot_hdr = build_boot_header(len(main_hdr), lsb_count)

    boot_bits = bytes_to_bits(boot_hdr)                 # BOOT (plane 0 only)
    main_bits = bytes_to_bits(main_hdr + payload)       # MAIN + payload (k planes)
    need = len(boot_bits) + len(main_bits)
    cap  = flat.size * lsb_count
    if need > cap:
        raise ValueError(f"Payload too large for selected cover object. \nPlease choose a larger cover object.")
        #  raise ValueError(f"Payload too large for select cover object.\n Payload needs {need} bits, capacity is only {cap} bits")

    perm = permutation_from_key(base_key + "|perm", flat.size)
    if anchor_xy and 0 <= anchor_xy[0] < W and 0 <= anchor_xy[1] < H:
        anchor_lin = (anchor_xy[1] * W + anchor_xy[0]) * 3
        try:
            start = perm.index(anchor_lin)
        except ValueError:
            start = sha_int(base_key + "|start") % flat.size
    else:
        start = sha_int(base_key + "|start") % flat.size

    out = flat.copy()

    # 1) BOOT → plane 0
    idx = start
    for b in boot_bits:
        pos = perm[idx]
        out[pos] = set_bit_plane(int(out[pos]), 0, b)
        idx = (idx + 1) % flat.size

    # 2) MAIN+payload → plane cycle over k LSBs
    planes = planes_perm_from_key(base_key)[:lsb_count]
    pi = 0
    for b in main_bits:
        pos = perm[idx]
        out[pos] = set_bit_plane(int(out[pos]), planes[pi], b)
        pi  = (pi + 1) % len(planes)
        idx = (idx + 1) % flat.size

    encoded = out.reshape(arr.shape).astype(np.uint8)
    enc_img = Image.fromarray(encoded, mode="RGB")
    return enc_img, arr, encoded

def decode_image_with_key(img: Image.Image, key_full: str):
    """Read BOOT in plane 0; read MAIN+payload using plane cycle over discovered k."""
    base_key, anchor_xy = parse_key_with_anchor(key_full)
    arr = np.array(img.convert("RGB"), dtype=np.uint8)
    H, W, _ = arr.shape
    flat = arr.reshape(-1)

    perm = permutation_from_key(base_key + "|perm", flat.size)
    if anchor_xy and 0 <= anchor_xy[0] < W and 0 <= anchor_xy[1] < H:
        anchor_lin = (anchor_xy[1] * W + anchor_xy[0]) * 3
        try:
            start = perm.index(anchor_lin)
        except ValueError:
            start = sha_int(base_key + "|start") % flat.size
    else:
        start = sha_int(base_key + "|start") % flat.size

    # 1) BOOT ← plane 0
    idx = start
    boot_bits = []
    for _ in range(BOOT_LEN * 8):
        pos = perm[idx]
        boot_bits.append(str(get_bit_plane(int(flat[pos]), 0)))
        idx = (idx + 1) % flat.size
    boot = bits_to_bytes(''.join(boot_bits))
    header_len, lsb_count = parse_boot_header(boot)

    # 2) MAIN header ← k-plane cycle
    planes = planes_perm_from_key(base_key)[:lsb_count]
    pi = 0
    main_bits = []
    for _ in range(header_len * 8):
        pos = perm[idx]
        main_bits.append(str(get_bit_plane(int(flat[pos]), planes[pi])))
        pi  = (pi + 1) % len(planes)
        idx = (idx + 1) % flat.size
    main_hdr = bits_to_bytes(''.join(main_bits))
    meta = parse_header(main_hdr)

    # 3) PAYLOAD ← same plane cycle
    need_bits = meta["size"] * 8
    payload_bits = []
    for _ in range(need_bits):
        pos = perm[idx]
        payload_bits.append(str(get_bit_plane(int(flat[pos]), planes[pi])))
        pi  = (pi + 1) % len(planes)
        idx = (idx + 1) % flat.size
    payload = bits_to_bytes(''.join(payload_bits))

    # CRC check
    if (zlib.crc32(payload) & 0xFFFFFFFF) != meta["crc32"]:
        raise ValueError("CRC mismatch. Wrong key or corrupted stego image.")

    return meta, payload

# ---------- viz & utils ----------
def make_difference_image(original: np.ndarray, encoded: np.ndarray, k: int) -> Image.Image:
    """Highlight pixels changed in the lowest k planes as red."""
    mask = (1 << k) - 1
    changed = ((original & mask) != (encoded & mask)).any(axis=2)
    vis = original.copy()
    vis[changed] = [255, 0, 0]
    return Image.fromarray(vis)

def pil_to_png_bytes(img: Image.Image) -> bytes:
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    return bio.getvalue()
