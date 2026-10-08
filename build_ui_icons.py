"""
<summary>
Generate the Lists quick button glyphs and the volume ring frames.
</summary>
<remarks>
Everything is drawn in white on a transparent canvas so the skin tints it
with colordiffuse, the same idea as build_home_icons.py.

  * media/icons/list_up.png, list_down.png, list_remove.png: the up arrow,
    down arrow and cross on a focused row of the Lists screen (LISTS-QUICK
    in Custom_1151_Lists.xml).
  * media/volume/disc.png: the filled circle the ring sits on.
  * media/volume/track.png: the full ring behind the fill.
  * media/volume/ring_000.png to ring_100.png: the fill, one frame per
    volume percent, starting at twelve o'clock and running clockwise.
    DialogVolumeBar.xml picks the frame through the VolumePercent variable.

The ring is drawn at four times its size and scaled down, which is how it
gets smooth edges without an anti aliasing pass. PIL writes no text chunks
by default, so the PNGs carry no metadata.
</remarks>
"""
from pathlib import Path

from PIL import Image, ImageDraw

MEDIA = Path(__file__).parent / "skin.functional" / "media"
WHITE = (255, 255, 255, 255)
TRANS = (0, 0, 0, 0)

ICON = 64           # quick button glyph size
RING = 360          # ring frame size on screen
RING_WIDTH = 22     # stroke on screen
SCALE = 4           # supersampling factor


def _save(img, path):
    """
    <summary>Write a PNG, creating its folder first.</summary>
    <param name="img">The image to write.</param>
    <param name="path">Destination path.</param>
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)


def _arrow(path, up):
    """
    <summary>A solid triangle pointing up or down, centred in the glyph.</summary>
    <param name="path">Destination path.</param>
    <param name="up">True for the up arrow, False for down.</param>
    """
    big = ICON * SCALE
    img = Image.new("RGBA", (big, big), TRANS)
    d = ImageDraw.Draw(img)
    m = big * 0.22
    if up:
        pts = [(big / 2, m), (big - m, big - m * 1.3), (m, big - m * 1.3)]
    else:
        pts = [(big / 2, big - m), (big - m, m * 1.3), (m, m * 1.3)]
    d.polygon(pts, fill=WHITE)
    _save(img.resize((ICON, ICON), Image.LANCZOS), path)


def _cross(path):
    """
    <summary>Two thick strokes crossing at the centre of the glyph.</summary>
    <param name="path">Destination path.</param>
    """
    big = ICON * SCALE
    img = Image.new("RGBA", (big, big), TRANS)
    d = ImageDraw.Draw(img)
    m = big * 0.26
    w = int(big * 0.12)
    d.line([(m, m), (big - m, big - m)], fill=WHITE, width=w)
    d.line([(big - m, m), (m, big - m)], fill=WHITE, width=w)
    _save(img.resize((ICON, ICON), Image.LANCZOS), path)


def _ring(path, percent):
    """
    <summary>One ring frame: an arc from twelve o'clock, clockwise, covering percent of the circle.</summary>
    <param name="path">Destination path.</param>
    <param name="percent">0 to 100; 0 writes an empty frame, 100 the whole ring.</param>
    """
    big = RING * SCALE
    img = Image.new("RGBA", (big, big), TRANS)
    if percent > 0:
        d = ImageDraw.Draw(img)
        inset = RING_WIDTH * SCALE / 2 + SCALE
        box = [inset, inset, big - inset, big - inset]
        w = RING_WIDTH * SCALE
        if percent >= 100:
            d.ellipse(box, outline=WHITE, width=w)
        else:
            # PIL measures angles clockwise from three o'clock.
            d.arc(box, -90, -90 + 360 * percent / 100, fill=WHITE, width=w)
    _save(img.resize((RING, RING), Image.LANCZOS), path)


def _disc(path):
    """
    <summary>A filled circle the size of a ring frame, the pop-up's backing.</summary>
    <param name="path">Destination path.</param>
    """
    big = RING * SCALE
    img = Image.new("RGBA", (big, big), TRANS)
    ImageDraw.Draw(img).ellipse([SCALE, SCALE, big - SCALE, big - SCALE], fill=WHITE)
    _save(img.resize((RING, RING), Image.LANCZOS), path)


def main():
    """<summary>Write every glyph and frame.</summary>"""
    icons = MEDIA / "icons"
    _arrow(icons / "list_up.png", True)
    _arrow(icons / "list_down.png", False)
    _cross(icons / "list_remove.png")
    vol = MEDIA / "volume"
    _disc(vol / "disc.png")
    _ring(vol / "track.png", 100)
    for p in range(101):
        _ring(vol / "ring_{0:03d}.png".format(p), p)


if __name__ == "__main__":
    main()
