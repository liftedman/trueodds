"""Apply the PREMIUM TrueOdds icon (gradient + shadow, supersampled) everywhere.

Writes:
  assets/icon/icon.png        premium full icon (legacy/iOS/web source)
  assets/icon/foreground.png  white mark, transparent (adaptive foreground)
  assets/icon/background.png   gradient square (adaptive background source)
  assets/icon/splash.png       white mark, transparent (native splash)
  android .../res/mipmap-*     legacy + round + adaptive-foreground PNGs
  android .../res/mipmap-anydpi-v26/*.xml   adaptive icon definition
  android .../res/drawable/ic_launcher_background.xml   gradient background
  web/favicon.png, web/icons/*  PWA icons

Run:  python tool/apply_premium.py
"""
from PIL import Image, ImageDraw, ImageFilter
import numpy as np
import os

SS = 4
TEAL_HI = (45, 212, 191)    # #2DD4BF
TEAL_LO = (13, 110, 109)    # #0D6E6D
WHITE = (255, 255, 255, 255)

HERE = os.path.dirname(__file__)
APP = os.path.normpath(os.path.join(HERE, ".."))
ICON_DIR = os.path.join(APP, "assets", "icon")
RES = os.path.join(APP, "android", "app", "src", "main", "res")
WEB = os.path.join(APP, "web")
os.makedirs(ICON_DIR, exist_ok=True)

LEGACY = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
FOREGROUND = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient(size):
    # diagonal t in [0,1] = (x+y)/(2*size), vectorised
    idx = np.arange(size)
    t = (idx[None, :] + idx[:, None]) / (2.0 * size)  # (size,size)
    hi = np.array(TEAL_HI, dtype=np.float32)
    lo = np.array(TEAL_LO, dtype=np.float32)
    rgb = hi[None, None, :] + (lo - hi)[None, None, :] * t[:, :, None]
    arr = np.dstack([rgb.astype(np.uint8),
                     np.full((size, size), 255, dtype=np.uint8)])
    return Image.fromarray(arr, "RGBA")


def squircle(size, rf=0.235):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size, size],
                                        radius=int(size * rf), fill=255)
    return m


def base_bg(size, mask):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(gradient(size), (0, 0), mask)
    hl = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse([-size * .3, -size * .5, size * .8, size * .4],
                               fill=(255, 255, 255, 38))
    hl = hl.filter(ImageFilter.GaussianBlur(size * .06))
    return Image.alpha_composite(
        img, Image.composite(hl, Image.new("RGBA", (size, size), (0, 0, 0, 0)), mask))


def draw_mark(d, size, scale):
    # scale is relative to a 1024 baseline, so proportions hold at any canvas size
    s = scale * size / 1024.0
    cx = cy = size // 2
    n, bw, gap = 4, int(70 * s), int(34 * s)
    heights = [120, 190, 250, 320]
    tw = n * bw + (n - 1) * gap
    x0 = cx - tw // 2
    bbase = cy + int(175 * s)
    tops = []
    for i in range(n):
        x = x0 + i * (bw + gap)
        top = bbase - int(heights[i] * s)
        d.rounded_rectangle([x, top, x + bw, bbase], radius=int(18 * s), fill=WHITE)
        tops.append((x + bw // 2, top))
    line = [(x, y - int(78 * s)) for (x, y) in tops]
    d.line(line, fill=WHITE, width=int(26 * s), joint="curve")
    r = int(28 * s)
    for (x, y) in line:
        d.ellipse([x - r, y - r, x + r, y + r], fill=WHITE)


def shadow(glyph, size):
    sh = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sh.paste(Image.new("RGBA", (size, size), (0, 0, 0, 90)),
             (0, int(size * .015)), glyph.split()[3])
    return sh.filter(ImageFilter.GaussianBlur(size * .02))


def mark_layer(size, scale):
    g = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw_mark(ImageDraw.Draw(g), size, scale)
    return g


def compose(size, mask, scale):
    img = base_bg(size, mask)
    glyph = mark_layer(size, scale)
    img = Image.alpha_composite(img, shadow(glyph, size))
    return Image.alpha_composite(img, glyph)


def render(out_size, kind, scale):
    """kind: 'square' | 'circle' | 'fg' | 'bg'."""
    size = out_size * SS
    if kind == "square":
        img = compose(size, squircle(size), scale)
    elif kind == "circle":
        m = Image.new("L", (size, size), 0)
        ImageDraw.Draw(m).ellipse([0, 0, size, size], fill=255)
        img = compose(size, m, scale)
    elif kind == "fg":
        img = mark_layer(size, scale)
    elif kind == "bg":
        full = Image.new("L", (size, size), 255)
        img = base_bg(size, full)
    return img.resize((out_size, out_size), Image.LANCZOS)


def save(img, folder, name):
    os.makedirs(folder, exist_ok=True)
    img.save(os.path.join(folder, name))


# ---- source assets ----
render(1024, "square", 1.18).save(os.path.join(ICON_DIR, "icon.png"))
render(1024, "fg", 1.35).save(os.path.join(ICON_DIR, "foreground.png"))
render(1024, "bg", 1.0).save(os.path.join(ICON_DIR, "background.png"))
mk = mark_layer(1024 * SS, 0.9).resize((1024, 1024), Image.LANCZOS)
mk.save(os.path.join(ICON_DIR, "splash.png"))

# ---- android mipmaps ----
for d, px in LEGACY.items():
    save(render(px, "square", 1.18), os.path.join(RES, f"mipmap-{d}"), "ic_launcher.png")
    save(render(px, "circle", 1.18), os.path.join(RES, f"mipmap-{d}"), "ic_launcher_round.png")
for d, px in FOREGROUND.items():
    save(render(px, "fg", 1.35), os.path.join(RES, f"mipmap-{d}"), "ic_launcher_foreground.png")

adaptive = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_launcher_background"/>
    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>
</adaptive-icon>
"""
for fn in ("ic_launcher.xml", "ic_launcher_round.xml"):
    save_path = os.path.join(RES, "mipmap-anydpi-v26")
    os.makedirs(save_path, exist_ok=True)
    with open(os.path.join(save_path, fn), "w", encoding="utf-8") as f:
        f.write(adaptive)

grad_drawable = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">
    <gradient
        android:startColor="#2DD4BF"
        android:endColor="#0D6E6D"
        android:angle="315"
        android:type="linear"/>
</shape>
"""
os.makedirs(os.path.join(RES, "drawable"), exist_ok=True)
with open(os.path.join(RES, "drawable", "ic_launcher_background.xml"), "w",
          encoding="utf-8") as f:
    f.write(grad_drawable)
# remove the old solid-colour resource if present (drawable now supplies the bg)
old_color = os.path.join(RES, "values", "ic_launcher_background.xml")
if os.path.exists(old_color):
    os.remove(old_color)

# ---- web / PWA icons ----
os.makedirs(os.path.join(WEB, "icons"), exist_ok=True)
render(192, "square", 1.18).save(os.path.join(WEB, "icons", "Icon-192.png"))
render(512, "square", 1.18).save(os.path.join(WEB, "icons", "Icon-512.png"))
# maskable: full-bleed gradient (no rounded corners) so the launcher mask is clean
mask_full = Image.new("L", (1024 * SS, 1024 * SS), 255)
maskable = compose(1024 * SS, mask_full, 0.9).resize((1024, 1024), Image.LANCZOS)
maskable.resize((192, 192), Image.LANCZOS).save(os.path.join(WEB, "icons", "Icon-maskable-192.png"))
maskable.resize((512, 512), Image.LANCZOS).save(os.path.join(WEB, "icons", "Icon-maskable-512.png"))
render(64, "square", 1.18).save(os.path.join(WEB, "favicon.png"))

print("Premium icon applied to source assets, android res, and web.")
