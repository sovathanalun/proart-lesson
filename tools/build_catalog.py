#!/usr/bin/env python3
"""Builds the public catalog the app downloads. This repo holds FREE lessons only.

Source
  lessons/<id>/…   FREE lessons, unzipped (manifest.json at its root; "store": {"free": true})
  paid-entries/<id>.json + .png   PAID listings only (no artwork), published by the private repo
  paid-entries/<id>.bundle.json   PAID bundles of those lessons, published by the private repo

Outputs (dist/public/, published with GitHub Pages)
  catalog.json, thumbs/<id>.png, packages/<id>-v<N>.zip
Paid lesson artwork never goes in lessons/: the build fails if a lesson there is marked paid.
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

    # Paid listings (no artwork) published here by the private repo's publish_entries.sh.
    entries = os.path.join(ROOT, "paid-entries")
    free_ids = {l["id"] for l in lessons}
    names = sorted(os.listdir(entries)) if os.path.isdir(entries) else []
    for name in names:
        if not name.endswith(".json") or name.endswith(".bundle.json"):
            continue
        e = json.load(open(os.path.join(entries, name), encoding="utf-8"))
        lid = e.get("id")
        if lid in free_ids:
            problems.append(f"paid-entries/{name}: '{lid}' is also a free lesson"); continue
        if e.get("free") or not e.get("productID") or not e.get("assetPackID"):
            problems.append(f"paid-entries/{name}: a paid listing needs free=false, productID and assetPackID"); continue
        thumb = os.path.join(entries, os.path.basename(e.get("thumbnail") or ""))
        if not os.path.isfile(thumb):
            problems.append(f"paid-entries/{name}: thumbnail {e.get('thumbnail')} missing"); continue
        shutil.copy(thumb, os.path.join(DIST, "public/thumbs", os.path.basename(thumb)))
        lessons.append(e)

    # Bundles (<id>.bundle.json): one purchase that unlocks several paid lessons listed above.
    bundles, paid_ids = [], {l["id"] for l in lessons if not l["free"]}
    for name in names:
        if not name.endswith(".bundle.json"):
            continue
        b = json.load(open(os.path.join(entries, name), encoding="utf-8"))
        missing = [i for i in b.get("lessonIDs") or [] if i not in paid_ids]
        if not b.get("id") or not b.get("productID") or not (b.get("title") or {}).get("en") or len(b.get("lessonIDs") or []) < 2 or missing:
            problems.append(f"paid-entries/{name}: a bundle needs id, productID, title.en and 2+ paid lessons; not found: {missing}"); continue
        bundles.append({k: b[k] for k in ("id", "productID", "title", "lessonIDs")})

    if problems:
        print("\nBUILD FAILED:")
        for p in problems: print("  -", p)
        return 1

    catalog = {"schema": 1, "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "lessons": lessons, "bundles": bundles}
    json.dump(catalog, open(os.path.join(DIST, "public/catalog.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    # Privacy policy and support pages the App Store listing links to.
    site = os.path.join(ROOT, "site")
    if os.path.isdir(site):
        shutil.copytree(site, os.path.join(DIST, "public"), dirs_exist_ok=True)
    print(f"OK: {len(free_ids)} free + {len(lessons) - len(free_ids)} paid lesson(s), {len(bundles)} bundle(s) -> dist/public")
    return 0


if __name__ == "__main__":
    sys.exit(main())
