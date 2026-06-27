"""Generate TrueOdds launcher + splash assets at high resolution.

Produces (under app/assets/icon/):
  icon.png        1024x1024  full teal rounded square + white mark (legacy/iOS/web)
  foreground.png  1024x1024  transparent, mark centred in the adaptive safe zone
  splash.png      1024x1024  transparent white mark (for flutter_native_splash)

Run:  python tool/make_icons.py
"""
from PIL import Image, ImageDraw
import os

TEAL = (14, 165, 164, 255)        # #0EA5A4 brand
WHITE = (255, 255, 255, 255)
S = 1024

OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "icon")
os.makedirs(OUT, exist_ok=True)


def draw_mark(d, cx, cy, scale):
    """Rising bars + a trend line with nodes, centred on (cx, cy)."""
    # bar geometry
    n = 4
    bw = int(70 * scale)
    gap = int(34 * scale)
    heights = [120, 190, 250, 320]
    total_w = n * bw + (n - 1) * gap
    x0 = cx - total_w // 2
    base = cy + int(170 * scale)
    tops = []
    for i in range(n):
        x = x0 + i * (bw + gap)
        h = int(heights[i] * scale)
        top = base - h
        d.rounded_rectangle([x, top, x + bw, base],
                            radius=int(16 * scale), fill=WHITE)
        tops.append((x + bw // 2, top))
    # trend line rising across the bar tops, lifted above them
    line = [(x, y - int(70 * scale)) for (x, y) in tops]
    d.line(line, fill=WHITE, width=int(22 * scale), joint="curve")
    # nodes on the trend line
    r = int(26 * scale)
    for (x, y) in line:
        d.ellipse([x - r, y - r, x + r, y + r], fill=WHITE)


def icon_full():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, S, S], radius=int(S * 0.22), fill=TEAL)
    draw_mark(d, S // 2, S // 2, 1.0)
    img.save(os.path.join(OUT, "icon.png"))


def foreground():
    # adaptive foreground: mark sits in the centre ~60% safe zone -> scale down
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    draw_mark(d, S // 2, S // 2, 0.62)
    img.save(os.path.join(OUT, "foreground.png"))


def splash():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    draw_mark(d, S // 2, S // 2, 0.8)
    img.save(os.path.join(OUT, "splash.png"))


icon_full()
foreground()
splash()
print("Wrote icon.png, foreground.png, splash.png to", os.path.abspath(OUT))
