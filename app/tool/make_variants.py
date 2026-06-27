"""Generate TrueOdds app-icon concepts for review (512px previews)."""
from PIL import Image, ImageDraw, ImageFont
import os

TEAL = (14, 165, 164, 255)
DARK = (11, 18, 32, 255)
WHITE = (255, 255, 255, 255)
S = 512
R = int(S * 0.22)

OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "icon", "concepts")
os.makedirs(OUT, exist_ok=True)


def font(sz):
    for p in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\Arialbd.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def bg(color=TEAL):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, S, S], radius=R, fill=color)
    return img, d


def a_bars():
    """Rising bars + trend line (the current icon)."""
    img, d = bg()
    n, bw, gap = 4, 35, 17
    heights = [60, 95, 125, 160]
    tw = n * bw + (n - 1) * gap
    x0 = S // 2 - tw // 2
    base = S // 2 + 85
    tops = []
    for i in range(n):
        x = x0 + i * (bw + gap)
        top = base - heights[i]
        d.rounded_rectangle([x, top, x + bw, base], radius=8, fill=WHITE)
        tops.append((x + bw // 2, top))
    line = [(x, y - 35) for (x, y) in tops]
    d.line(line, fill=WHITE, width=11, joint="curve")
    for (x, y) in line:
        d.ellipse([x - 13, y - 13, x + 13, y + 13], fill=WHITE)
    img.save(os.path.join(OUT, "a_bars.png"))


def b_monogram():
    """Bold 'T' wordmark feel."""
    img, d = bg()
    f = font(300)
    txt = "T"
    bbox = d.textbbox((0, 0), txt, font=f)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text((S // 2 - w // 2 - bbox[0], S // 2 - h // 2 - bbox[1]), txt,
           font=f, fill=WHITE)
    img.save(os.path.join(OUT, "b_monogram.png"))


def c_check():
    """Checkmark = honest / verified, with a small bar base."""
    img, d = bg()
    # checkmark
    pts = [(S * 0.30, S * 0.52), (S * 0.44, S * 0.66), (S * 0.72, S * 0.34)]
    d.line(pts, fill=WHITE, width=34, joint="curve")
    # round the ends
    for (x, y) in (pts[0], pts[2]):
        d.ellipse([x - 17, y - 17, x + 17, y + 17], fill=WHITE)
    img.save(os.path.join(OUT, "c_check.png"))


def d_target():
    """Concentric rings = accuracy / 'true' odds."""
    img, d = bg()
    cx, cy = S // 2, S // 2
    for rad, wdt in ((150, 26), (95, 24)):
        d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=WHITE, width=wdt)
    d.ellipse([cx - 34, cy - 34, cx + 34, cy + 34], fill=WHITE)
    img.save(os.path.join(OUT, "d_target.png"))


def e_bars_dark():
    """Bars on a dark background (alternative palette)."""
    img, d = bg(DARK)
    n, bw, gap = 4, 35, 17
    heights = [60, 95, 125, 160]
    tw = n * bw + (n - 1) * gap
    x0 = S // 2 - tw // 2
    base = S // 2 + 85
    tops = []
    for i in range(n):
        x = x0 + i * (bw + gap)
        top = base - heights[i]
        d.rounded_rectangle([x, top, x + bw, base], radius=8, fill=TEAL)
        tops.append((x + bw // 2, top))
    line = [(x, y - 35) for (x, y) in tops]
    d.line(line, fill=WHITE, width=11, joint="curve")
    for (x, y) in line:
        d.ellipse([x - 13, y - 13, x + 13, y + 13], fill=WHITE)
    img.save(os.path.join(OUT, "e_bars_dark.png"))


a_bars()
b_monogram()
c_check()
d_target()
e_bars_dark()
print("Wrote concepts to", os.path.abspath(OUT))
