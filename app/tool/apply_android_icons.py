"""Write TrueOdds launcher icons straight into android/.../res (concept A).

Bypasses flutter_launcher_icons (the Flutter toolchain hangs in some shells).
Generates legacy, round, and adaptive (foreground + colour) icons at every
density, plus the adaptive XML and background colour resource.

Run:  python tool/apply_android_icons.py
"""
from PIL import Image, ImageDraw
import os

TEAL = (14, 165, 164, 255)
WHITE = (255, 255, 255, 255)
HEX_BG = "#0EA5A4"

HERE = os.path.dirname(__file__)
RES = os.path.normpath(os.path.join(HERE, "..", "android", "app", "src", "main", "res"))

LEGACY = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
FOREGROUND = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}


def draw_mark(d, cx, cy, scale, color=WHITE):
    n, bw, gap = 4, int(70 * scale), int(34 * scale)
    heights = [120, 190, 250, 320]
    tw = n * bw + (n - 1) * gap
    x0 = cx - tw // 2
    base = cy + int(170 * scale)
    tops = []
    for i in range(n):
        x = x0 + i * (bw + gap)
        top = base - int(heights[i] * scale)
        d.rounded_rectangle([x, top, x + bw, base], radius=int(16 * scale), fill=color)
        tops.append((x + bw // 2, top))
    line = [(x, y - int(70 * scale)) for (x, y) in tops]
    d.line(line, fill=color, width=int(22 * scale), joint="curve")
    r = int(26 * scale)
    for (x, y) in line:
        d.ellipse([x - r, y - r, x + r, y + r], fill=color)


def master_full(size=1024):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size, size], radius=int(size * 0.22), fill=TEAL)
    draw_mark(d, size // 2, size // 2, size / 1024)
    return img


def master_round(size=1024):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, size, size], fill=TEAL)
    draw_mark(d, size // 2, size // 2, size / 1024)
    return img


def master_fg(size=1024):
    # bigger mark so it reads well inside the adaptive safe zone
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    draw_mark(d, size // 2, size // 2, 1.35 * size / 1024)
    return img


full, rnd, fg = master_full(), master_round(), master_fg()


def save(img, density, name):
    folder = os.path.join(RES, f"mipmap-{density}")
    os.makedirs(folder, exist_ok=True)
    img.save(os.path.join(folder, name))


for density, px in LEGACY.items():
    save(full.resize((px, px), Image.LANCZOS), density, "ic_launcher.png")
    save(rnd.resize((px, px), Image.LANCZOS), density, "ic_launcher_round.png")
for density, px in FOREGROUND.items():
    save(fg.resize((px, px), Image.LANCZOS), density, "ic_launcher_foreground.png")

# adaptive icon XML (API 26+)
adaptive = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background"/>
    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>
</adaptive-icon>
"""
anydpi = os.path.join(RES, "mipmap-anydpi-v26")
os.makedirs(anydpi, exist_ok=True)
for fn in ("ic_launcher.xml", "ic_launcher_round.xml"):
    with open(os.path.join(anydpi, fn), "w", encoding="utf-8") as f:
        f.write(adaptive)

# background colour resource
vals = os.path.join(RES, "values")
os.makedirs(vals, exist_ok=True)
with open(os.path.join(vals, "ic_launcher_background.xml"), "w", encoding="utf-8") as f:
    f.write('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
            f'    <color name="ic_launcher_background">{HEX_BG}</color>\n</resources>\n')

print("Applied launcher icons (legacy + round + adaptive) to", RES)
