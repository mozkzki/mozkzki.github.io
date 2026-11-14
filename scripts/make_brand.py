#!/usr/bin/env python3
"""ロゴの印から、ファビコン・ホーム画面のアイコン・共有画像(OGP)を作る。

  python3 scripts/make_brand.py

印や掲載アプリを変えたときに手元(Mac)で流して、できたファイルを commit する。
画像にするのに Google Chrome を、ico にするのに Pillow を使う。Actions では流さない。

印は「もずくの m」(m の 3 本の脚を海藻の糸にしたもの)。屋号の由来がもずくなので。
見出しの文字では、mozksoft の z も海藻の揺れにする(templates/index.html の WAVY_Z と同じ形)。
"""
import base64
import json
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

INK = "#1d1d1f"
PAPER = "#f5f5f7"
DARK_BG = "#161618"
M_PATH = ("M28 75C22 66 34 58 28 47a11 11 0 0 1 22 0C56 56 44 66 50 75"
          "M50 47a11 11 0 0 1 22 0C78 56 66 66 72 75")
Z_PATH = "M8 15C16 5 23 25 31 15S46 5 52 15L8 57C16 47 23 67 31 57S46 47 52 57"


def mark(tile, stroke, rounded=True):
    rx = ' rx="22.5"' if rounded else ""
    return (f'<rect width="100" height="100"{rx} fill="{tile}"/>'
            f'<path d="{M_PATH}" fill="none" stroke="{stroke}" stroke-width="8.5" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')


def favicon_svg():
    # タブがライトなら黒い四角、ダークなら白い四角に反転させる。見出しの印もこの 1 枚を使う
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
<style>
  .tile {{ fill: {INK}; }} .m {{ stroke: #ffffff; }}
  @media (prefers-color-scheme: dark) {{ .tile {{ fill: {PAPER}; }} .m {{ stroke: {DARK_BG}; }} }}
</style>
<rect class="tile" width="100" height="100" rx="22.5"/>
<path class="m" d="{M_PATH}" fill="none" stroke-width="8.5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
'''


def render(html, width, height):
    """HTML を Chrome で開いて、width × height の PNG にする。"""
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "page.html"
        out = Path(tmp) / "out.png"
        page.write_text(html)
        subprocess.run([
            CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
            "--force-device-scale-factor=1", f"--window-size={width},{height}",
            "--default-background-color=00000000", f"--screenshot={out}", page.as_uri(),
        ], check=True, capture_output=True)
        return Image.open(out).convert("RGBA").crop((0, 0, width, height))


def svg_page(svg, size):
    return (f'<!doctype html><body style="margin:0;background:transparent">'
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="{size}" height="{size}" '
            f'style="display:block">{svg}</svg>')


def og_page():
    apps = json.loads((ROOT / "data" / "apps.json").read_text())
    icons = "".join(
        f'<img src="data:image/jpeg;base64,{base64.b64encode((ROOT / a["icon"]).read_bytes()).decode()}">'
        for a in apps
    )
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
  body {{ margin: 0; width: 1200px; height: 630px; background: {DARK_BG}; color: {PAPER};
         display: grid; place-content: center; justify-items: center; gap: 64px;
         font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif; }}
  .lock {{ display: flex; align-items: center; gap: 32px; font-size: 104px; font-weight: 800; letter-spacing: -0.02em; line-height: 1; }}
  .lock svg.mark {{ width: 128px; height: 128px; display: block; }}
  .z {{ width: .56em; height: .69em; vertical-align: -.07em; }}
  .icons {{ display: flex; gap: 14px; }}
  .icons img {{ width: 64px; height: 64px; border-radius: 22.5%; box-shadow: 0 0 0 1px rgba(255,255,255,.16); display: block; }}
</style></head><body>
  <div class="lock">
    <svg class="mark" viewBox="0 0 100 100">{mark(PAPER, DARK_BG)}</svg>
    <span>mo<svg class="z" viewBox="0 0 60 70"><path d="{Z_PATH}" fill="none" stroke="{PAPER}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/></svg>ksoft</span>
  </div>
  <div class="icons">{icons}</div>
</body></html>'''


def main():
    (ROOT / "favicon.svg").write_text(favicon_svg())

    # 古いブラウザ向け。ライトのタブ想定の黒い四角
    ico = render(svg_page(mark(INK, "#ffffff"), 64), 64, 64)
    ico.save(ROOT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])

    # ホーム画面に追加したとき。iOS が角を丸めるので、四角いまま塗りつぶす
    touch = render(svg_page(mark(INK, "#ffffff", rounded=False), 180), 180, 180).convert("RGB")
    touch.save(ROOT / "apple-touch-icon.png")

    og = render(og_page(), 1200, 630).convert("RGB")
    buf = BytesIO()
    og.save(buf, "PNG", optimize=True)
    (ROOT / "assets" / "og.png").write_bytes(buf.getvalue())

    for f in ("favicon.svg", "favicon.ico", "apple-touch-icon.png", "assets/og.png"):
        print(f"wrote {f} ({(ROOT / f).stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
