"""
<summary>
Generate the artwork for the hidden Colophon screen (custom window 1154),
and the dedication photo embedded in the skin's code.
</summary>
<remarks>
Drawn in white on a transparent canvas so the skin tints it with the accent
colour through colordiffuse, the same idea as build_ui_icons.py.

  * media/colophon/cup.png: a coffee cup on its saucer, in outline, with the
    coffee's surface as a filled ellipse. 480 by 400.
  * media/colophon/cup_fill.png: the same cup's body and saucer filled solid,
    drawn in the background colour between the steam and the outline, so
    steam rising from behind the cup never shows through its open body.
  * media/colophon/glow.png: a soft round glow, opaque at the centre and
    fading to nothing at the edge, for the light behind the cup. 512 square.
  * media/colophon/steam.png: one soft wisp of steam, a swaying ribbon that
    fades in at its foot and out towards its top. 120 by 300. Custom_1154_Credits.xml draws
    three of them, each rising and fading on its own loop, so the steam
    never moves in step.

  * skin.functional/colophon_art.py: the dedication photo as base64 text in
    a Python module, so it ships inside the skin's code rather than as an
    image file. service.py writes it out to the skin's own data folder at
    start up, which is where the Colophon screen shows it from. Made from
    the local source photo (resources/, excluded through .git/info/exclude
    and never published): cropped to the portrait the screen wants, clear
    of the bench's plaque and the camera's date stamp, shrunk to 360 by 512
    and saved fresh, so no EXIF, GPS or camera data survives. Skipped, with
    a note, when the source photo is not on this machine.

Everything is drawn at four times its size and scaled down, which is how it
gets smooth edges without an anti aliasing pass. PIL writes no text chunks
by default, so the PNGs carry no metadata.

Usage:
    python3 build_colophon_art.py
</remarks>
"""
import base64
import hashlib
import io
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

OUT = Path(__file__).parent / "skin.functional" / "media" / "colophon"
PHOTO_SOURCE = Path(__file__).parent / "resources" / "DSCN2079.jpg"
PHOTO_MODULE = Path(__file__).parent / "skin.functional" / "colophon_art.py"
# The crop as fractions of the photo's width and height: her, without the
# bench's memorial plaque (right) or the date stamp (bottom right).
PHOTO_CROP = (0.3167, 0.0593, 0.6444, 0.6815)
PHOTO_SIZE = (360, 512)
SCALE = 4
WHITE = (255, 255, 255, 255)


def _save(img, name, size):
    """
    <summary>Scale a supersampled canvas down and write it as a PNG.</summary>
    <param name="img">The canvas, SCALE times the final size.</param>
    <param name="name">File name inside media/colophon.</param>
    <param name="size">The final (width, height).</param>
    """
    OUT.mkdir(parents=True, exist_ok=True)
    img.resize(size, Image.LANCZOS).save(OUT / name, optimize=True)
    print("wrote", OUT / name)


def cup():
    """
    <summary>Draw the cup and saucer.</summary>
    <remarks>
    The body is a rounded rectangle with square top corners: straight sides
    and a round bottom, the shape of a coffee cup rather than a glass. It is
    drawn filled and then hollowed with a copy inset by the stroke, so the
    outline keeps one even width all the way round. The handle ring is drawn
    before the hollowing, so the part of it inside the body disappears.
    </remarks>
    """
    w, h = 480 * SCALE, 400 * SCALE
    stroke = 14 * SCALE
    clear = (0, 0, 0, 0)
    img = Image.new("RGBA", (w, h), clear)
    d = ImageDraw.Draw(img)

    fill_img = Image.new("RGBA", (w, h), clear)
    fd = ImageDraw.Draw(fill_img)

    def body(inset, fill, draw=None):
        """<summary>The cup body, shrunk by inset on every side, in one colour.</summary>"""
        draw = draw or d
        box = (70 * SCALE + inset, 70 * SCALE + inset, 350 * SCALE - inset, 300 * SCALE - inset)
        draw.rounded_rectangle(box, radius=120 * SCALE - inset, fill=fill)
        # Square off the top corners: only the bottom is rounded.
        draw.rectangle((box[0], box[1], box[2], box[1] + 130 * SCALE), fill=fill)

    d.ellipse((290 * SCALE, 110 * SCALE, 420 * SCALE, 240 * SCALE), outline=WHITE, width=stroke)
    body(0, WHITE)
    body(stroke, clear)
    # The coffee, a filled ellipse just under the rim, and the rim itself.
    d.ellipse((70 * SCALE + stroke, 52 * SCALE, 350 * SCALE - stroke, 88 * SCALE), fill=WHITE)
    d.ellipse((70 * SCALE, 40 * SCALE, 350 * SCALE, 100 * SCALE), outline=WHITE, width=stroke)
    # Saucer: a wide flat ellipse the base sits in.
    d.ellipse((10 * SCALE, 290 * SCALE, 410 * SCALE, 350 * SCALE), outline=WHITE, width=stroke)
    # The solid silhouette: body, rim and saucer filled.
    body(0, WHITE, fd)
    fd.ellipse((70 * SCALE, 40 * SCALE, 350 * SCALE, 100 * SCALE), fill=WHITE)
    fd.ellipse((10 * SCALE, 290 * SCALE, 410 * SCALE, 350 * SCALE), fill=WHITE)
    _save(fill_img, "cup_fill.png", (480, 400))
    _save(img, "cup.png", (480, 400))


def steam():
    """
    <summary>Draw one wisp: a swaying ribbon that thins and fades as it rises.</summary>
    """
    w, h = 120 * SCALE, 300 * SCALE
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    steps = 140
    for i in range(steps):
        t = i / steps
        y = h - t * h * 0.95
        x = w / 2 + math.sin(t * math.pi * 2.2) * 26 * SCALE
        radius = (13 - 9 * t) * SCALE
        alpha = int(235 * (1 - t) ** 1.4)
        d.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 255, 255, alpha))
    img = img.filter(ImageFilter.GaussianBlur(5 * SCALE))
    # Fade the foot in over its lowest fifth, so the wisp has no hard base.
    alpha = img.split()[3]
    ramp = Image.new("L", (w, h), 255)
    rd = ImageDraw.Draw(ramp)
    foot = int(h * 0.2)
    for y in range(foot):
        rd.line((0, h - 1 - y, w, h - 1 - y), fill=int(255 * y / foot))
    img.putalpha(Image.composite(alpha, Image.new("L", (w, h), 0), ramp))
    _save(img, "steam.png", (120, 300))


def glow():
    """
    <summary>Draw the soft round glow: white, its alpha falling off smoothly
    from the centre to nothing at the edge.</summary>
    """
    size = 512
    img = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(img)
    for r in range(size // 2, 0, -1):
        t = r / (size / 2)
        d.ellipse((size / 2 - r, size / 2 - r, size / 2 + r, size / 2 + r),
                  fill=int(255 * (1 - t) ** 1.8))
    out = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    out.putalpha(img.filter(ImageFilter.GaussianBlur(4)))
    OUT.mkdir(parents=True, exist_ok=True)
    out.save(OUT / "glow.png", optimize=True)
    print("wrote", OUT / "glow.png")


def dedication():
    """
    <summary>Embed the dedication photo in skin.functional/colophon_art.py.</summary>
    <remarks>
    The photo is opened, turned the way its camera said, cropped, shrunk and
    encoded again as a plain JPEG. PIL writes no EXIF, GPS or comment block
    unless asked to, so none reaches the skin. A SHA-256 of the bytes goes in
    the module too, which is what service.py compares against the copy it
    wrote last time.
    </remarks>
    """
    if not PHOTO_SOURCE.exists():
        print("skipped the dedication photo: no %s here" % PHOTO_SOURCE.name)
        return
    im = ImageOps.exif_transpose(Image.open(PHOTO_SOURCE)).convert("RGB")
    w, h = im.size
    box = tuple(int(round(f * (w if i % 2 == 0 else h))) for i, f in enumerate(PHOTO_CROP))
    im = im.crop(box).resize(PHOTO_SIZE, Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80, optimize=True, progressive=True)
    data = buf.getvalue()
    text = base64.b64encode(data).decode("ascii")
    lines = [text[i:i + 76] for i in range(0, len(text), 76)]
    body = "\n".join('    "%s"' % line for line in lines)
    PHOTO_MODULE.write_text('''# -*- coding: utf-8 -*-
"""
<summary>
The Colophon screen's dedication photo, embedded as base64 text.
</summary>
<remarks>
Generated by build_colophon_art.py; do not edit by hand. A small cropped
JPEG with no EXIF, GPS or camera data. service.py writes it out to the
skin's data folder at start up (FunctionalHelper.write_dedication).
</remarks>
"""

# SHA-256 of the decoded bytes, so the service rewrites the file only when
# the photo itself has changed.
DEDICATION_SHA256 = "%s"

DEDICATION_JPEG = (
%s
)
''' % (hashlib.sha256(data).hexdigest(), body), encoding="utf-8")
    print("wrote", PHOTO_MODULE, "(%d bytes of JPEG)" % len(data))


if __name__ == "__main__":
    cup()
    steam()
    glow()
    dedication()
