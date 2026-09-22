r"""Generate desktop/app_icon.ico — the family glasses + a download badge.

Same slate-blue glasses as the Validator / Filler / Size-Import icons so the
apps read as one family; only the badge differs. Here it's a violet disc with a
white download arrow (this app downloads product images).

Re-run only when the icon should change:
    "C:\gv\Scripts\python.exe" desktop\make_icon.py
"""
import os

from PIL import Image, ImageDraw

S = 1024                       # working canvas
FRAME = (43, 90, 158, 255)     # slate blue   — same as the family
DOWNLOAD = (124, 58, 189, 255)  # violet       — "download" badge
LENS = (120, 170, 225, 70)     # faint glass tint
WHITE = (255, 255, 255, 255)

HERE = os.path.dirname(os.path.abspath(__file__))


def rounded(draw, box, r, **kw):
    draw.rounded_rectangle(box, radius=r, **kw)


def build(size=S):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = size / 1024.0
    w = int(58 * u)

    # ---- glasses (unchanged from the family) ----
    top, h = int(340 * u), int(310 * u)
    lens_w = int(350 * u)
    inset = int(96 * u)
    left = (inset, top, inset + lens_w, top + h)
    right = (size - inset - lens_w, top, size - inset, top + h)
    for box in (left, right):
        rounded(d, box, int(85 * u), fill=LENS, outline=FRAME, width=w)

    d.arc((left[2] - int(20 * u), top + int(30 * u),
           right[0] + int(20 * u), top + int(180 * u)),
          start=200, end=340, fill=FRAME, width=w)

    ty = top + int(70 * u)
    d.line((left[0], ty, int(10 * u), ty - int(34 * u)), fill=FRAME, width=w)
    d.line((right[2], ty, size - int(10 * u), ty - int(34 * u)), fill=FRAME, width=w)

    # ---- download badge (same disc position/size as the family) ----
    cx, cy, r = int(720 * u), int(730 * u), int(250 * u)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=DOWNLOAD)

    # white down-arrow: vertical stem + arrowhead + a tray line under it
    stem_w = 46 * u
    d.rectangle((cx - stem_w / 2, cy - 120 * u, cx + stem_w / 2, cy + 30 * u), fill=WHITE)
    d.polygon([(cx - 105 * u, cy + 10 * u), (cx + 105 * u, cy + 10 * u), (cx, cy + 120 * u)],
              fill=WHITE)
    tray_w = 150 * u
    tray_th = 40 * u
    rounded(d, (cx - tray_w, cy + 150 * u, cx + tray_w, cy + 150 * u + tray_th),
            int(tray_th / 2), fill=WHITE)

    return img


def main():
    base = build()
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [base.resize((s, s), Image.LANCZOS) for s in sizes]
    ico = os.path.join(HERE, "app_icon.ico")
    png = os.path.join(HERE, "app_icon.png")
    frames[-1].save(ico, format="ICO", sizes=[(s, s) for s in sizes])
    base.resize((256, 256), Image.LANCZOS).save(png)
    print(f"wrote {ico} and {png}")


if __name__ == "__main__":
    main()
