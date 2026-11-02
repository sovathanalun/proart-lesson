#!/usr/bin/env python3
"""Validate a ProArt lesson package (.zip) exactly the way the app will.

Usage:  python3 validate_lesson_package.py my-lesson.zip [more.zip ...]
Exit code 0 = every package is valid, 1 = at least one problem.
Uses only the standard library; if Pillow is installed it also checks the pixels
(transparency, line colour, coverage). Install it with:  pip3 install pillow
"""
import json, re, struct, sys, zipfile

LANGS = {"en", "km", "zh-Hans", "es"}
CATEGORIES = {"characters", "animals", "nature", "objects"}
LEVELS = {"easy", "medium", "hard"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
HEX_RE = re.compile(r"^#?[0-9A-Fa-f]{6}$")
MAX_UNPACKED = 120 * 1024 * 1024

try:
    from PIL import Image
except ImportError:  # pixel checks are optional
    Image = None


def png_header(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h, depth, ctype = struct.unpack(">IIBB", data[16:26])
    return w, h, depth, ctype


def check_text(errors, label, value, required_en=True):
    if not isinstance(value, dict) or not value:
        errors.append(f"{label} must be an object like {{\"en\": \"...\"}}")
        return
    if required_en and not str(value.get("en", "")).strip():
        errors.append(f"{label}.en is required and must not be empty")
    for k, v in value.items():
        if k not in LANGS:
            errors.append(f"{label} has unsupported language code '{k}' (use {sorted(LANGS)})")
        if not isinstance(v, str):
            errors.append(f"{label}.{k} must be a string")


def validate(path):
    errors, warnings = [], []
    try:
        z = zipfile.ZipFile(path)
    except Exception as e:
        return [f"not a readable ZIP: {e}"], []
    names = z.namelist()
    if sum(i.file_size for i in z.infolist()) > MAX_UNPACKED:
        errors.append("unpacked size is over 120 MB")
    for n in names:
        if n.startswith("/") or ".." in n.split("/"):
            errors.append(f"unsafe path in ZIP: {n}")
    if any(n.startswith("__MACOSX/") or n.endswith(".DS_Store") for n in names):
        warnings.append("remove __MACOSX/ and .DS_Store entries (zip with: zip -r -X -x '*.DS_Store' ...)")

    manifests = [n for n in names if n == "manifest.json" or (n.endswith("/manifest.json") and n.count("/") == 1 and not n.startswith("__MACOSX"))]
    if not manifests:
        return errors + ["manifest.json is missing (it must be at the ZIP root)"], warnings
    mpath = min(manifests, key=len)
    prefix = mpath[: -len("manifest.json")]
    if prefix:
        warnings.append("manifest.json is inside a folder; it works, but put it at the ZIP root")
    try:
        m = json.loads(z.read(mpath))
    except Exception as e:
        return errors + [f"manifest.json is not valid JSON: {e}"], warnings

    if m.get("formatVersion") != 1:
        errors.append("formatVersion must be the number 1")
    pid = m.get("id", "")
    if not isinstance(pid, str) or not ID_RE.match(pid):
        errors.append("id must be lowercase letters, digits and dashes, 2-63 chars, e.g. 'anime-boy-001'")
    if "version" in m and not (isinstance(m["version"], int) and m["version"] >= 1):
        errors.append("version (optional) must be a whole number >= 1; bump it when you change a published lesson")
    check_text(errors, "title", m.get("title"))
    if str(m.get("category", "")).lower() not in CATEGORIES:
        errors.append(f"category must be one of {sorted(CATEGORIES)}")
    if str(m.get("level", "")).lower() not in LEVELS:
        errors.append(f"level must be one of {sorted(LEVELS)}")
    size = m.get("imageSize") or {}
    W, H = size.get("width"), size.get("height")
    if not (isinstance(W, int) and isinstance(H, int) and 64 <= W <= 4096 and 64 <= H <= 4096):
        errors.append("imageSize.width/height must be integers between 64 and 4096")
        W = H = None
    elif max(W, H) < 1536:
        warnings.append("imageSize is small; 2048 on the longest side is recommended for crisp lines")

    steps = m.get("steps")
    if not isinstance(steps, list) or not (2 <= len(steps) <= 10):
        errors.append("steps must be a list of 2-10 entries (3-6 recommended)")
        steps = []
    files = []
    ink_steps = 0
    for i, s in enumerate(steps):
        lab = f"steps[{i}]"
        if not isinstance(s, dict):
            errors.append(f"{lab} must be an object"); continue
        if s.get("role") not in ("construction", "ink"):
            errors.append(f"{lab}.role must be 'construction' or 'ink'")
        ink_steps += s.get("role") == "ink"
        check_text(errors, f"{lab}.title", s.get("title"))
        check_text(errors, f"{lab}.hint", s.get("hint"))
        if isinstance(s.get("hint"), dict) and len(str(s["hint"].get("en", ""))) > 220:
            warnings.append(f"{lab}.hint.en is long (>220 chars); keep hints to one or two short sentences")
        files.append((f"{lab}.image", s.get("image"), "step"))
    if steps and not any(s.get("role") == "ink" for s in steps if isinstance(s, dict)):
        warnings.append("no step has role 'ink'; most lessons end with ink steps")
    files.append(("lineArt", m.get("lineArt"), "lineart"))
    files.append(("colorReference", m.get("colorReference"), "color"))
    if m.get("thumbnail"):
        files.append(("thumbnail", m["thumbnail"], "thumb"))
    else:
        warnings.append("no thumbnail listed (optional, but recommended: 512x512 PNG)")

    if m.get("colorHint") is not None:
        check_text(errors, "colorHint", m["colorHint"])
    pal = m.get("palette", [])
    if not isinstance(pal, list) or any(not isinstance(c, str) or not HEX_RE.match(c) for c in pal):
        errors.append("palette must be a list of hex colours like '#F4A259'")
    elif not (4 <= len(pal) <= 12):
        warnings.append("palette should have 4-12 colours")
    store = m.get("store")
    if store is not None:
        if not isinstance(store, dict):
            errors.append("store must be an object")
        else:
            if store.get("free") is False and not store.get("productID"):
                errors.append("store.productID is required when store.free is false")
            if store.get("productID") and not re.match(r"^[A-Za-z0-9._]+$", store["productID"]):
                errors.append("store.productID may only contain letters, digits, dots and underscores")

    for label, rel, kind in files:
        if not isinstance(rel, str) or not rel:
            errors.append(f"{label} is missing"); continue
        if rel.startswith("/") or ".." in rel:
            errors.append(f"{label}: unsafe path '{rel}'"); continue
        if prefix + rel not in names:
            errors.append(f"{label}: file '{rel}' is listed in the manifest but not in the ZIP"); continue
        data = z.read(prefix + rel)
        if rel.lower().endswith(".png"):
            hdr = png_header(data)
            if not hdr:
                errors.append(f"{rel}: not a valid PNG"); continue
            w, h, depth, ctype = hdr
            if kind != "thumb" and W and (w, h) != (W, H):
                errors.append(f"{rel}: is {w}x{h} but imageSize is {W}x{H} (every image must match)")
            if kind in ("step", "lineart") and ctype not in (4, 6):
                errors.append(f"{rel}: must be a PNG with an alpha channel (transparent background); found colour type {ctype}")
            if depth != 8:
                warnings.append(f"{rel}: bit depth {depth}; 8-bit is recommended")
        elif not rel.lower().endswith((".jpg", ".jpeg")):
            errors.append(f"{rel}: use .png (or .jpg for color/thumbnail)")
        if len(data) > 6 * 1024 * 1024:
            warnings.append(f"{rel} is {len(data)//1024} KB; try to keep each image under ~3 MB")

        if Image is not None and not any(e.startswith(rel) for e in errors):
            try:
                import io
                im = Image.open(io.BytesIO(data))
                if kind in ("step", "lineart"):
                    a = im.convert("RGBA").getchannel("A")
                    hist = a.histogram()
                    total = im.width * im.height
                    opaque = sum(hist[16:]) / total
                    if opaque == 0:
                        errors.append(f"{rel}: image is completely transparent (nothing drawn)")
                    elif opaque > 0.45:
                        errors.append(f"{rel}: {opaque:.0%} of pixels are opaque; guides must be line work on a TRANSPARENT background")
                    elif opaque < 0.0005:
                        warnings.append(f"{rel}: almost nothing is drawn ({opaque:.4%} of pixels)")
                    if kind == "lineart":
                        rgb = im.convert("RGBA")
                        px = [p for p in rgb.resize((256, 256)).getdata() if p[3] > 128]
                        if px and sum(sum(p[:3]) / 3 for p in px) / len(px) > 110:
                            errors.append(f"{rel}: line art must be DARK lines (near #1A1A1A); average line colour is too light")
                if kind == "color":
                    if "A" in im.getbands() and im.getchannel("A").getextrema()[0] < 250:
                        errors.append(f"{rel}: colorReference must be fully opaque (no transparency)")
            except Exception as e:
                errors.append(f"{rel}: could not be decoded ({e})")
    return errors, warnings


def main(argv):
    if not argv:
        print(__doc__); return 1
    bad = False
    for p in argv:
        errors, warnings = validate(p)
        print(f"== {p}")
        for w in warnings: print(f"  warning: {w}")
        for e in errors: print(f"  ERROR:   {e}")
        if errors:
            bad = True
        else:
            print("  OK - the app will accept this package")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
