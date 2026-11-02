# proart-lesson — PUBLIC GitHub repo (free lessons only)

The app reads public web files only (no token, nothing to expire). This repo contains **free lessons only**; nothing paid
(no artwork, no listings, no bundles) belongs here.

Catalog address (GitHub Pages): `https://sovathanalun.github.io/proart-lesson/catalog.json`

```
proart-lesson/
├─ lessons/<id>/                    FREE lessons, unzipped (manifest.json at its root, "store": { "free": true })
├─ tools/                           validate_lesson_package.py, build_catalog.py
└─ .github/workflows/pages.yml      builds catalog.json and publishes it with GitHub Pages
```
The build fails if a lesson here is not marked free.

## One-time setup
1. Push this repo to `git@github.com:sovathanalun/proart-lesson.git` (branch `main`).
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. In the app: **Settings → Lesson Store** → `https://sovathanalun.github.io/proart-lesson/`.

## Add a free lesson
Make the package with the lesson prompt (`proart-app/docs/lesson-package/CREATOR_PROMPT.md`), unzip it into `lessons/<id>/`
with `"store": { "free": true }`, then `git push`. The workflow validates it, republishes the catalog, and the app shows **Get**.
Update a lesson by raising `"version"` in its manifest.

## Paid lessons
Not handled in this repo. They will be connected later through the private repo (how the app learns about them is still to be decided).

## Limits
GitHub Pages: about 100 GB/month soft bandwidth, 1 GB site size. Keep zips and thumbnails small. Anything pushed to a public repo stays in its Git history.
