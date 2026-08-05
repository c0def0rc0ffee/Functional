"""Generate the three home icons as combined disc+glyph PNGs.

Each PNG has:
  * an alpha~80 white disc (so colordiffuse tints it semi-strong)
  * an alpha=255 white glyph (cog / 2x2 grid / power) on top

When Kodi colordiffuses the texture, the disc appears as a darker shade
of the target colour while the glyph appears full-strength, giving
contrast on both focused (accent) and unfocused (bg_panel) buttons.
The icon is then a single texture on a normal <button> — keeping it
focus-navigable inside its grouplist parent.
"""
from PIL import Image, ImageDraw
from math import cos, sin, radians
from pathlib import Path

OUT = Path(__file__).parent / "skin.functional" / "media" / "icons"
OUT.mkdir(parents=True, exist_ok=True)

SIZE = 128
TRANS = (0, 0, 0, 0)
DISC_ALPHA = 90               # semi-transparent disc
DISC_COLOUR = (255, 255, 255, DISC_ALPHA)
GLYPH_COLOUR = (255, 255, 255, 255)


def base_disc():
    img = Image.new("RGBA", (SIZE, SIZE), TRANS)
    d = ImageDraw.Draw(img)
    d.ellipse([4, 4, SIZE - 4, SIZE - 4], fill=DISC_COLOUR)
    return img, d


def cog(path: Path):
    img, d = base_disc()
    cx, cy = SIZE / 2, SIZE / 2
    teeth = 8
    inner_r = 14
    outer_r = 36
    base_r = 27
    half = 11

    pts = []
    step = 360 / teeth
    for i in range(teeth):
        a = i * step - 90
        for ang, r in (
            (a - half, base_r),
            (a - half * 0.55, outer_r),
            (a + half * 0.55, outer_r),
            (a + half, base_r),
        ):
            pts.append((cx + r * cos(radians(ang)), cy + r * sin(radians(ang))))
        nxt = (i + 1) * step - 90 - half
        for k in (1, 2):
            ang = a + half + (nxt - a - half) * k / 3
            pts.append((cx + base_r * cos(radians(ang)), cy + base_r * sin(radians(ang))))
    d.polygon(pts, fill=GLYPH_COLOUR)
    # Punch centre hole back to transparent.
    d.ellipse([cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r], fill=TRANS)
    # Restore the disc inside the hole so we don't punch through the background.
    d.ellipse([cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r], fill=DISC_COLOUR)
    img.save(path)


def puzzle(path: Path):
    img, d = base_disc()
    pad = 36
    gap = 6
    side = (SIZE - 2 * pad - gap) // 2
    for row in range(2):
        for col in range(2):
            x = pad + col * (side + gap)
            y = pad + row * (side + gap)
            d.rounded_rectangle([x, y, x + side, y + side], radius=4, fill=GLYPH_COLOUR)
    img.save(path)


def power(path: Path):
    img, d = base_disc()
    cx, cy = SIZE / 2, SIZE / 2
    ring_outer = 32
    ring_inner = 24
    d.pieslice(
        [cx - ring_outer, cy - ring_outer, cx + ring_outer, cy + ring_outer],
        start=-65,
        end=245,
        fill=GLYPH_COLOUR,
    )
    # Clear interior of the ring.
    d.ellipse([cx - ring_inner, cy - ring_inner, cx + ring_inner, cy + ring_inner], fill=TRANS)
    d.ellipse([cx - ring_inner, cy - ring_inner, cx + ring_inner, cy + ring_inner], fill=DISC_COLOUR)
    # Widen the gap at the top so the vertical bar sits cleanly.
    bar_w = 10
    d.rectangle([cx - bar_w / 2 - 2, 4, cx + bar_w / 2 + 2, cy - 4], fill=TRANS)
    d.rectangle([cx - bar_w / 2 - 2, 4, cx + bar_w / 2 + 2, cy - 4], fill=DISC_COLOUR)
    # Vertical bar.
    d.rounded_rectangle([cx - bar_w / 2, cy - 38, cx + bar_w / 2, cy - 8], radius=3, fill=GLYPH_COLOUR)
    img.save(path)


def star(path: Path):
    img, d = base_disc()
    cx, cy = SIZE / 2, SIZE / 2
    outer_r = 38
    inner_r = 15
    pts = []
    # 5-point star: alternate outer/inner vertices, first point straight up.
    for i in range(10):
        ang = radians(-90 + i * 36)
        r = outer_r if i % 2 == 0 else inner_r
        pts.append((cx + r * cos(ang), cy + r * sin(ang)))
    d.polygon(pts, fill=GLYPH_COLOUR)
    img.save(path)


cog(OUT / "home_settings.png")
puzzle(OUT / "home_addons.png")
power(OUT / "home_power.png")
star(OUT / "home_favourites.png")
print("Wrote:", *(p.name for p in (OUT / n for n in (
    "home_settings.png", "home_addons.png", "home_power.png", "home_favourites.png"))))
