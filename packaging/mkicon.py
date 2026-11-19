# Sondugrande's icon in the house style of the author's other applications:
# one Septambres Neau glyph, one colour on one colour, macOS rounded tile.
# The glyph is the font's "g", a square: SoundGrain's red handle of a
# trajectory, in SoundGrain's red on the grey of its drawing surface.
#
#   python3 packaging/mkicon.py            (needs Pillow, the font, and iconutil on macOS)
#
# The generated files are committed; the font is not part of this repository.
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

FONT = os.path.expanduser("~/Library/Fonts/Septambres Neau.ttf")
GLYPH, FG, BG = "g", "#b82020", "#1e1e1e"
HERE = os.path.dirname(os.path.abspath(__file__))


def icon(size=1024, full=False):
    k = 4                                    # draw big, scale down: smooth edges
    W = size * k
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = 0 if full else round(W * 100 / 1024)  # macOS grid: 824 of 1024, radius ~185
    d.rounded_rectangle([m, m, W - m - 1, W - m - 1], radius=0 if full else round(W * 185 / 1024), fill=BG)
    font = ImageFont.truetype(FONT, round(W * 0.62))
    box = d.textbbox((0, 0), GLYPH, font=font)
    gw, gh = box[2] - box[0], box[3] - box[1]
    scale = (W - 2 * m) * 0.44 / max(gw, gh)    # every glyph fills the same share of the tile
    font = ImageFont.truetype(FONT, round(W * 0.62 * scale))
    box = d.textbbox((0, 0), GLYPH, font=font)
    gw, gh = box[2] - box[0], box[3] - box[1]
    d.text(((W - gw) / 2 - box[0], (W - gh) / 2 - box[1]), GLYPH, font=font, fill=FG)
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    big = icon(1024)
    big.save(os.path.join(HERE, "Sondugrande.png"))
    icon(256).save(os.path.join(HERE, "..", "docs", "icon.png"))
    big.save(os.path.join(HERE, "Sondugrande.ico"), sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    if sys.platform == "darwin":
        iconset = os.path.join(HERE, "Sondugrande.iconset")
        os.makedirs(iconset, exist_ok=True)
        for s in (16, 32, 128, 256, 512):
            icon(s).save(os.path.join(iconset, "icon_%dx%d.png" % (s, s)))
            icon(s * 2).save(os.path.join(iconset, "icon_%dx%d@2x.png" % (s, s)))
        subprocess.check_call(["iconutil", "-c", "icns", iconset, "-o", os.path.join(HERE, "Sondugrande.icns")])
        for name in os.listdir(iconset):
            os.remove(os.path.join(iconset, name))
        os.rmdir(iconset)
