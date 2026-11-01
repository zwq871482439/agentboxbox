"""Generate boxbox app icons from source-a.jpg (方案 A, Grok Bot 生成).

Usage: python assets/icon/make_icons.py   (needs Pillow)
Crops the white margin, makes everything outside the rounded square transparent,
then exports PNG sizes, favicon.ico, boxbox.ico and apple-touch-icon.png.
"""
import os
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "source-a.jpg")
# measured bounds of the dark rounded square in the 1024 source
BOX = (47, 43, 977, 975)   # 2px inset to drop the white JPG fringe
RADIUS = 0.19              # corner radius as a share of the side
PNG_SIZES = [1024, 512, 256, 192, 128, 64, 48, 32, 16]
FAVICON = [16, 32, 48]
APP_ICO = [16, 24, 32, 48, 64, 128, 256]


def master() -> Image.Image:
    im = Image.open(SRC).convert("RGB").crop(BOX).resize((1024, 1024), Image.LANCZOS)
    ss = 4
    m = Image.new("L", (1024 * ss, 1024 * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, 1024 * ss - 1, 1024 * ss - 1),
                                        radius=int(1024 * ss * RADIUS), fill=255)
    m = m.resize((1024, 1024), Image.LANCZOS)
    out = im.convert("RGBA")
    out.putalpha(m)
    return out


def scaled(m: Image.Image, n: int) -> Image.Image:
    if n >= 128:
        return m.resize((n, n), Image.LANCZOS)
    # small sizes: step down with BOX filter (area average) then light sharpen
    im = m.resize((n * 4, n * 4), Image.LANCZOS).resize((n, n), Image.BOX)
    if n <= 32:
        rgb = im.convert("RGB").filter(ImageFilter.UnsharpMask(radius=0.6, percent=80, threshold=1))
        rgb.putalpha(im.getchannel("A"))
        im = rgb
    return im


def main():
    m = master()
    imgs = {n: scaled(m, n) for n in sorted(set(PNG_SIZES + FAVICON + APP_ICO + [180]))}
    for n in PNG_SIZES:
        imgs[n].save(os.path.join(HERE, "icon-%d.png" % n), optimize=True)
    imgs[180].save(os.path.join(HERE, "apple-touch-icon.png"), optimize=True)
    imgs[48].save(os.path.join(HERE, "favicon.ico"), sizes=[(n, n) for n in FAVICON],
                  append_images=[imgs[n] for n in FAVICON])
    imgs[256].save(os.path.join(HERE, "boxbox.ico"), sizes=[(n, n) for n in APP_ICO],
                   append_images=[imgs[n] for n in APP_ICO])
    print("ok", HERE)


if __name__ == "__main__":
    main()
