#!/usr/bin/env python3
"""Builds the public catalog the app downloads. This repo holds FREE lessons only.

Source
  lessons/<id>/…   FREE lessons, unzipped (manifest.json at its root; "store": {"free": true})

Outputs (dist/public/, published with GitHub Pages)
  catalog.json, thumbs/<id>.png, packages/<id>-v<N>.zip
Paid lessons are intentionally not handled here: the build fails if a lesson is marked paid.
"""
import datetime, hashlib, json, os, shutil, sys, zipfile
sys.path.insert(0, os.path.dirname(__file__))
from validate_lesson_package import validate  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")


def zip_dir(src, dest):
    """Deterministic ZIP (same input -> same bytes -> stable sha256), manifest.json first."""
    files = []
    for base, _, names in os.walk(src):
        for n in names:
            if n == ".DS_Store" or base.endswith("__MACOSX"):
                continue
            files.append(os.path.relpath(os.path.join(base, n), src).replace(os.sep, "/"))
    files.sort(key=lambda f: (f != "manifest.json", f))
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in files:
            zi = zipfile.ZipInfo(rel, date_time=(2024, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            with open(os.path.join(src, rel), "rb") as f:
                z.writestr(zi, f.read())


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    problems, lessons = [], []
    shutil.rmtree(DIST, ignore_errors=True)
    for d in ("public/thumbs", "public/packages"):
        os.makedirs(os.path.join(DIST, d))

    folder = os.path.join(ROOT, "lessons")
    for lid in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        src = os.path.join(folder, lid)
        if lid.startswith(".") or not os.path.isdir(src):
            continue
        mpath = os.path.join(src, "manifest.json")
        if not os.path.exists(mpath):
            problems.append(f"lessons/{lid}: manifest.json missing"); continue
        m = json.load(open(mpath, encoding="utf-8"))
        if m.get("id") != lid:
            problems.append(f"lessons/{lid}: folder name must equal manifest id '{m.get('id')}'"); continue
        if not (m.get("store") or {}).get("free", False):
            problems.append(f"lessons/{lid}: this lesson is not marked free. Paid lessons do not belong in this public repo"); continue
        version = int(m.get("version", 1))
        zname = f"{lid}-v{version}.zip"
        zdest = os.path.join(DIST, "public/packages", zname)
        zip_dir(src, zdest)
        errors, warnings = validate(zdest)
        for w in warnings: print(f"  warning [{lid}]: {w}")
        if errors:
            problems += [f"{lid}: {e}" for e in errors]; continue
        thumb_rel = m.get("thumbnail") or m["colorReference"]
        ext = os.path.splitext(thumb_rel)[1].lower() or ".png"
        shutil.copy(os.path.join(src, thumb_rel), os.path.join(DIST, "public/thumbs", lid + ext))
        lessons.append({"id": lid, "version": version, "title": m["title"], "category": m["category"].lower(), "level": m["level"].lower(),
                        "tags": m.get("tags", []), "free": True, "productID": None, "thumbnail": f"thumbs/{lid}{ext}",
                        "assetPackID": None, "package": f"packages/{zname}", "sha256": sha256(zdest), "bytes": os.path.getsize(zdest)})

    if problems:
        print("\nBUILD FAILED:")
        for p in problems: print("  -", p)
        return 1

    catalog = {"schema": 1, "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "lessons": lessons, "bundles": []}
    json.dump(catalog, open(os.path.join(DIST, "public/catalog.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"OK: {len(lessons)} free lesson(s) -> dist/public")
    return 0


if __name__ == "__main__":
    sys.exit(main())
