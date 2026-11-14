#!/usr/bin/env python3
"""iTunes Lookup API からアプリ情報を取り直し、index.html を作り直す。

  python3 scripts/build.py            # 取得 + 生成
  python3 scripts/build.py --offline  # data/apps.json から生成だけ

掲載するアプリと分類は data/catalog.json で手で持つ。
評価・バージョン・アイコン・スクショは API から取るので、手で書かない。
特定商取引法に基づく表記は、mozkzki/apps の各アプリのプライバシーポリシーにある表を集めて作る。
"""
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "catalog.json"
APPS_JSON = ROOT / "data" / "apps.json"
TEMPLATE = ROOT / "templates" / "index.html"
OUT = ROOT / "index.html"
TOKUSHOHO_JSON = ROOT / "data" / "tokushoho.json"
TOKUSHOHO_TEMPLATE = ROOT / "templates" / "tokushoho.html"
TOKUSHOHO_OUT = ROOT / "tokushoho" / "index.html"
ICON_DIR = ROOT / "assets" / "icons"
SHOT_DIR = ROOT / "assets" / "screenshots"

LOOKUP = "https://itunes.apple.com/lookup?id={ids}&country=jp"
ICON_SIZE = "256x256bb.jpg"
STORE_PAGE = "https://apps.apple.com/jp/app/id{id}"
SHOT_WIDTH = 392
FEATURED_SHOTS = 4
POLICY = "https://raw.githubusercontent.com/mozkzki/apps/main/{folder}/privacy_policy/japanese.md"
TOKUSHOHO_HEADING = "## 特定商取引法に基づく表記"


def get(url, tries=3):
    req = urllib.request.Request(url, headers={"User-Agent": "mozksoft-site-build"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError):
            # 429 やタイムアウトは少し待てば通ることが多い
            if attempt == tries - 1:
                raise
            time.sleep(10 * (attempt + 1))


def strip_exif(jpeg):
    """JPEG から EXIF(APP1)を抜く。mzstatic は配信のたびに違う ID を EXIF に入れるので、
    そのまま保存すると中身が同じでも毎回差分が出る。"""
    if jpeg[:2] != b"\xff\xd8":
        return jpeg
    out, i = [jpeg[:2]], 2
    while i + 4 <= len(jpeg) and jpeg[i] == 0xFF:
        marker = jpeg[i + 1]
        if marker == 0xDA:  # SOS 以降は画像データ
            break
        end = i + 2 + int.from_bytes(jpeg[i + 2:i + 4], "big")
        if marker != 0xE1:
            out.append(jpeg[i:end])
        i = end
    out.append(jpeg[i:])
    return b"".join(out)


def resized(url, size):
    # mzstatic の URL は末尾の "<w>x<h>bb.<ext>" を差し替えると別サイズが返る
    return re.sub(r"/[^/]+$", "/" + size, url)


def store_screenshots(app_id):
    """App Store の Web ページにある iPhone のスクショを [(URL の型, 幅, 高さ)] で返す。

    Lookup API の screenshotUrls は 5.5 インチ用の組しか返さず、新しい 6.5 / 6.9 インチ用の組が
    取れないので、ページに埋め込まれたデータから取る。
    """
    try:
        page = get(STORE_PAGE.format(id=app_id)).decode()
    except (urllib.error.URLError, TimeoutError) as err:
        print(f"  App Store のページが取れない({err}): {app_id}")
        return []
    found = re.findall(r'"screenshot":\{[^{}]*?"template":"([^"]+)","width":(\d+),"height":(\d+)', page)
    shots = []
    for template, w, h in found:
        w, h = int(w), int(h)
        # 縦長の比が 1.8 を超えるものが iPhone(iPad は 1.4 前後)
        if h / w > 1.8 and template not in (t for t, _, _ in shots):
            shots.append((template, w, h))
    return shots


def subtitle(track_name, name):
    """App Store 上の名前から、短い名前を除いた残り(本人が付けた副題)を返す。"""
    rest = track_name[len(name):] if track_name.startswith(name) else ""
    return rest.strip(" -:：・").strip("()（）").strip()


def fetch(catalog):
    ids = ",".join(str(a["id"]) for a in catalog["apps"])
    results = {r["trackId"]: r for r in json.loads(get(LOOKUP.format(ids=ids)))["results"]}
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    SHOT_DIR.mkdir(parents=True, exist_ok=True)

    previous = {a["id"]: a for a in json.loads(APPS_JSON.read_text())} if APPS_JSON.exists() else {}
    apps = []
    for entry in catalog["apps"]:
        r = results.get(entry["id"])
        if r is None:
            sys.exit(f"lookup に無い: {entry['id']} {entry['name']}")
        icon = f"assets/icons/{entry['id']}.jpg"
        (ROOT / icon).write_bytes(strip_exif(get(resized(r["artworkUrl512"], ICON_SIZE))))

        shots = []
        if entry.get("featured"):
            sources = store_screenshots(entry["id"])
            kept = previous.get(entry["id"], {}).get("screenshots")
            if not sources and kept:
                # Web ページが取れない日は、前回のスクショをそのまま使う
                shots = kept
            else:
                # 前回分も無ければ、Lookup API の(古い)組を使う
                sources = sources or [
                    (re.sub(r"/[^/]+$", "/{w}x{h}{c}.{f}", u), 1242, 2208) for u in r["screenshotUrls"]
                ]
                images = []
                for i, (template, w, h) in enumerate(sources[:FEATURED_SHOTS]):
                    height = round(SHOT_WIDTH * h / w)
                    url = template.format(w=SHOT_WIDTH, h=height, c="bb", f="jpg")
                    images.append((f"assets/screenshots/{entry['id']}-{i}.jpg", strip_exif(get(url))))
                    shots.append({"src": images[-1][0], "width": SHOT_WIDTH, "height": height})
                # 全部取れてから、前回の画像と入れ替える
                for f in SHOT_DIR.glob(f"{entry['id']}-*.jpg"):
                    f.unlink()
                for path, data in images:
                    (ROOT / path).write_bytes(data)

        apps.append({
            **entry,
            "trackName": r["trackName"],
            # catalog に subtitle を書いたアプリは、それを使う(空にすると出さない)
            "subtitle": entry["subtitle"] if "subtitle" in entry else subtitle(r["trackName"], entry["name"]),
            "url": f"https://apps.apple.com/jp/app/id{entry['id']}",
            "icon": icon,
            "screenshots": shots,
            "averageUserRating": r.get("averageUserRating", 0),
            "userRatingCount": r.get("userRatingCount", 0),
            "version": r["version"],
            "currentVersionReleaseDate": r["currentVersionReleaseDate"],
        })
        print(f"  {entry['name']}: v{r['version']}")

    APPS_JSON.write_text(json.dumps(apps, ensure_ascii=False, indent=2) + "\n")
    return apps


def tokushoho_rows(markdown):
    """プライバシーポリシーの「特定商取引法に基づく表記」の表を [(項目, 内容)] で返す。無ければ []。"""
    if TOKUSHOHO_HEADING not in markdown:
        return []
    rows = []
    for line in markdown.split(TOKUSHOHO_HEADING, 1)[1].splitlines()[1:]:
        if line.startswith("#"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 2 and cells[0] not in ("項目", "") and not set(cells[0]) <= set("-:"):
            rows.append(cells)
    return rows


def fetch_tokushoho(catalog):
    found = []
    for entry in catalog["apps"]:
        rows = tokushoho_rows(get(POLICY.format(folder=entry["folder"])).decode())
        if rows:
            found.append({"id": entry["id"], "name": entry["name"], "rows": rows})
            print(f"  特商法: {entry['name']}")
    TOKUSHOHO_JSON.write_text(json.dumps(found, ensure_ascii=False, indent=2) + "\n")
    return found


def render_tokushoho(entries):
    e = html.escape

    def table(rows):
        body = "\n".join(f"      <tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in rows)
        return f"  <table>\n{body}\n  </table>"

    # 全アプリで同じ行は上に 1 回だけ、違う行はアプリごとに並べる
    first = entries[0]["rows"]
    common = [r for r in first if all(r in x["rows"] for x in entries)]
    per_app = []
    for x in entries:
        rest = [r for r in x["rows"] if r not in common]
        per_app.append(f'  <h2><img class="icon" src="../assets/icons/{x["id"]}.jpg" alt="" width="32" height="32">'
                       f'{e(x["name"])}</h2>\n{table(rest)}')

    TOKUSHOHO_OUT.parent.mkdir(exist_ok=True)
    TOKUSHOHO_OUT.write_text(Template(TOKUSHOHO_TEMPLATE.read_text()).substitute(
        common=table(common),
        per_app="\n".join(per_app),
    ))


def render(catalog, apps):
    e = html.escape
    filters = "\n".join(
        f'      <button type="button" data-filter="{c["key"]}" aria-pressed="false">{e(c["label"])}</button>'
        for c in catalog["categories"]
    )

    featured = []
    for a in (a for a in apps if a.get("featured")):
        shots = "".join(f'<img src="{s["src"]}" alt="" width="{s["width"] // 2}" height="{s["height"] // 2}" loading="lazy">' for s in a["screenshots"])
        rating = ""
        if a["userRatingCount"]:
            rating = (f'<p class="rating"><span aria-hidden="true">★</span> {a["averageUserRating"]:.1f}'
                      f' <span class="count">({a["userRatingCount"]:,}件)</span></p>')
        featured.append(f'''    <a class="featured" href="{a["url"]}" data-category="{a["category"]}">
      <div class="head">
        <img class="icon" src="{a["icon"]}" alt="" width="112" height="112">
        <div>
          <h2>{e(a["name"])}</h2>
          <p class="sub">{e(a["subtitle"])}</p>
          {rating}
        </div>
      </div>
      <div class="shots">{shots}</div>
    </a>''')

    items = []
    for a in (a for a in apps if not a.get("featured")):
        sub = f'<span class="sub">{e(a["subtitle"])}</span>' if a["subtitle"] else ""
        items.append(f'''      <li data-category="{a["category"]}"><a href="{a["url"]}">
        <img class="icon" src="{a["icon"]}" alt="" width="64" height="64" loading="lazy">
        <span><span class="name">{e(a["name"])}</span>{sub}</span>
      </a></li>''')

    page = Template(TEMPLATE.read_text()).substitute(
        filters=filters,
        featured="\n".join(featured),
        items="\n".join(items),
    )
    OUT.write_text(page)


def main():
    catalog = json.loads(CATALOG.read_text())
    if "--offline" in sys.argv:
        apps = json.loads(APPS_JSON.read_text())
        tokushoho = json.loads(TOKUSHOHO_JSON.read_text())
    else:
        apps = fetch(catalog)
        tokushoho = fetch_tokushoho(catalog)
    render(catalog, apps)
    render_tokushoho(tokushoho)
    print(f"wrote {OUT.relative_to(ROOT)}, {TOKUSHOHO_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
