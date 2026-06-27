"""Premium TrueOdds icon concepts: gradient depth, soft shadow, supersampled.

Renders at 4x then downsamples for crisp edges. Writes 512px previews to
assets/icon/concepts/ and a comparison sheet.
"""
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import os

SS = 4                      # supersample factor
S = 512
OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "icon", "concepts")
os.makedirs(OUT, exist_ok=True)

# brand gradient stops
TEAL_HI = (45, 212, 191)    # #2DD4BF light
TEAL_LO = (13, 110, 109)    # #0D6E6D deep
WHITE = (255, 255, 255, 255)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient(size):
    """Diagonal teal gradient."""
    g = Image.new("RGB", (size, size))
    px = g.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)
            px[x, y] = lerp(TEAL_HI, TEAL_LO, t)
    return g.convert("RGBA")


def squircle_mask(size, radius_frac=0.235):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size, size],
                                        radius=int(size * radius_frac), fill=255)
    return m


def base(size):
    """Gradient squircle with a subtle top highlight."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    g = gradient(size)
    img.paste(g, (0, 0), squircle_mask(size))
    # soft top-left highlight for depth
    hl = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse([-size * .3, -size * .5, size * .8, size * .4],
                               fill=(255, 255, 255, 38))
    hl = hl.filter(ImageFilter.GaussianBlur(size * .06))
    img = Image.alpha_composite(img, Image.composite(
        hl, Image.new("RGBA", (size, size), (0, 0, 0, 0)), squircle_mask(size)))
    return img


def with_shadow(glyph, size):
    """Drop a soft shadow under a white glyph layer."""
    sh = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    alpha = glyph.split()[3]
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 90))
    sh.paste(shadow, (0, int(size * .015)), alpha)
    sh = sh.filter(ImageFilter.GaussianBlur(size * .02))
    return sh


def draw_bars(d, size, scale=1.0):
    cx = cy = size // 2
    n, bw, gap = 4, int(70 * scale), int(34 * scale)
    heights = [120, 190, 250, 320]
    tw = n * bw + (n - 1) * gap
    x0 = cx - tw // 2
    bbase = cy + int(175 * scale)
    tops = []
    for i in range(n):
        x = x0 + i * (bw + gap)
        top = bbase - int(heights[i] * scale)
        d.rounded_rectangle([x, top, x + bw, bbase], radius=int(18 * scale), fill=WHITE)
        tops.append((x + bw // 2, top))
    line = [(x, y - int(78 * scale)) for (x, y) in tops]
    d.line(line, fill=WHITE, width=int(26 * scale), joint="curve")
    r = int(28 * scale)
    for (x, y) in line:
        d.ellipse([x - r, y - r, x + r, y + r], fill=WHITE)
    return line


def font(sz):
    for p in (r"C:\Windows\Fonts\arialbd.ttf",):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def render(builder, name, scale=1.0):
    size = S * SS
    img = base(size)
    glyph = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glyph)
    builder(gd, size, scale * SS)
    img = Image.alpha_composite(img, with_shadow(glyph, size))
    img = Image.alpha_composite(img, glyph)
    img = img.resize((S, S), Image.LANCZOS)
    img.save(os.path.join(OUT, name))


def b_bars(d, size, scale):
    draw_bars(d, size, scale)


def b_bars_check(d, size, scale):
    line = draw_bars(d, size, scale)
    # turn the last node into a small check accent above the trend
    x, y = line[-1]
    cs = int(26 * scale)
    pts = [(x - cs, y - int(6 * scale)), (x - int(4 * scale), y + int(10 * scale)),
           (x + int(22 * scale), y - int(26 * scale))]


def b_mono(d, size, scale):
    f = font(int(300 * scale))
    txt = "T"
    bbox = d.textbbox((0, 0), txt, font=f)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text((size // 2 - w // 2 - bbox[0], size // 2 - h // 2 - bbox[1]), txt,
           font=f, fill=WHITE)
    # small rising underline tick
    y = size // 2 + int(150 * scale)
    d.line([(size//2 - int(90*scale), y), (size//2 + int(90*scale), y - int(50*scale))],
           fill=WHITE, width=int(22 * scale), joint="curve")


render(b_bars, "p_bars.png", 1.05)
render(b_mono, "p_mono.png", 1.0)


def sheet():
    names = [("p_bars", "1 · Bars (premium)"), ("p_mono", "2 · Monogram (premium)"),
             ("a_bars", "3 · Bars (flat, old)")]
    th, pad, lab = 200, 26, 36
    sh = Image.new("RGBA", (len(names) * (th + pad) + pad, th + pad * 2 + lab),
                   (245, 245, 247, 255))
    dr = ImageDraw.Draw(sh)
    f = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 22)
    x = pad
    for key, label in names:
        p = os.path.join(OUT, key + ".png")
        if not os.path.exists(p):
            x += th + pad
            continue
        im = Image.open(p).resize((th, th), Image.LANCZOS)
        sh.paste(im, (x, pad), im)
        dr.text((x, pad + th + 8), label, fill=(20, 20, 20, 255), font=f)
        x += th + pad
    sh.convert("RGB").save(os.path.join(OUT, "_premium_sheet.png"))


sheet()
print("Wrote premium concepts + _premium_sheet.png to", os.path.abspath(OUT))
