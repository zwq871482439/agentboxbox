"""Generate boxbox app icons from source-a.jpg (方案 A, Grok Bot 生成).

Usage: python assets/icon/make_icons.py   (needs Pillow)
Crops the white margin, makes everything outside the rounded square transparent,
then exports PNG sizes, favicon.ico, boxbox.ico and apple-touch-icon.png.
Also draws the two tray state badges (boxbox-red.ico / boxbox-running.ico):
the tray loads these .ico files at runtime (ctypes LoadImageW), so they must
exist as files — Pillow is a build-time-only tool here, the exe does not ship it.
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
# 托盘三态（boxbox/tray_win.py 按名字换）：红点 = 核心连不上，绿点 = 有卡在跑
BADGES = {"red": (220, 50, 50), "running": (70, 170, 100)}


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


def badge(m: Image.Image, color) -> Image.Image:
    """在右上角画一颗带白边的小圆点，比例照托盘 16px 栅格（直径约 6/16 边长）。"""
    im = m.copy()
    d = ImageDraw.Draw(im)
    u = im.width // 16
    d.ellipse((10 * u, 0, 16 * u, 6 * u), fill=tuple(color) + (255,),
              outline=(255, 255, 255, 255), width=u // 2 or 1)
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
    for name, color in BADGES.items():
        b = {n: scaled(badge(m, color), n) for n in APP_ICO}
        b[256].save(os.path.join(HERE, "boxbox-%s.ico" % name), sizes=[(n, n) for n in APP_ICO],
                    append_images=[b[n] for n in APP_ICO])
    print("ok", HERE)


if __name__ == "__main__":
    main()
