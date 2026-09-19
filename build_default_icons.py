"""
<summary>
Generate the stock Default*.png fallback icons the XML references.
</summary>
<remarks>
Kodi looks these up in the skin's own media/ folder (core ships none), so a
skin that references them via fallback= must bundle them; Estuary packs its
own set into Textures.xbt. Without them, any list item lacking real art
renders a blank hole.

Style matches the skin: an opaque near-bg rounded panel with a muted
blue-grey glyph, so placeholders read as intentional, not as missing art.
None of the referencing controls colordiffuse their fallback, so the
colours here are final.
</remarks>
"""
from PIL import Image, ImageDraw
from pathlib import Path

OUT = Path(__file__).parent / "skin.functional" / "media"
OUT.mkdir(parents=True, exist_ok=True)

SIZE = 256
TRANS = (0, 0, 0, 0)
PANEL = (26, 30, 36, 255)     # a step above colors/defaults.xml "bg"
GLYPH = (110, 122, 133, 255)  # muted blue-grey, quieter than "grey"


def base_panel():
    """
    <summary>
    Start a new icon: a transparent canvas with the rounded panel drawn on it.
    </summary>
    <returns>The image and its ImageDraw handle, ready for a glyph.</returns>
    """
    img = Image.new("RGBA", (SIZE, SIZE), TRANS)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=20, fill=PANEL)
    return img, d


def video(path: Path):
    """
    <summary>
    Play triangle.
    </summary>
    <param name="path">Where the PNG is written.</param>
    """
    img, d = base_panel()
    d.polygon([(104, 78), (104, 178), (188, 128)], fill=GLYPH)
    img.save(path)


def video_cover(path: Path):
    """
    <summary>
    Film strip: frame with sprocket holes down both edges.
    </summary>
    <param name="path">Where the PNG is written.</param>
    """
    img, d = base_panel()
    left, right, top, bottom = 84, 172, 56, 200
    d.rounded_rectangle([left, top, right, bottom], radius=8, fill=GLYPH)
    # Frame windows.
    d.rectangle([left + 24, top + 12, right - 24, 126], fill=PANEL)
    d.rectangle([left + 24, 130, right - 24, bottom - 12], fill=PANEL)
    # Sprocket holes.
    for y in range(top + 12, bottom - 12, 26):
        d.rectangle([left + 8, y, left + 16, y + 12], fill=PANEL)
        d.rectangle([right - 16, y, right - 8, y + 12], fill=PANEL)
    img.save(path)


def folder(path: Path):
    """
    <summary>
    Folder: a tab above a body.
    </summary>
    <param name="path">Where the PNG is written.</param>
    """
    img, d = base_panel()
    d.rounded_rectangle([60, 80, 132, 108], radius=8, fill=GLYPH)   # tab
    d.rounded_rectangle([60, 94, 196, 180], radius=8, fill=GLYPH)   # body
    img.save(path)


def actor(path: Path):
    """
    <summary>
    Head-and-shoulders silhouette.
    </summary>
    <param name="path">Where the PNG is written.</param>
    """
    img, d = base_panel()
    d.ellipse([100, 66, 156, 122], fill=GLYPH)                       # head
    d.rounded_rectangle([76, 134, 180, 198], radius=26, fill=GLYPH)  # torso
    # Square the torso's bottom off against the panel edge padding.
    d.rectangle([76, 172, 180, 198], fill=GLYPH)
    img.save(path)


def addon(path: Path):
    """
    <summary>
    2x2 grid, echoing the home_addons icon.
    </summary>
    <param name="path">Where the PNG is written.</param>
    """
    img, d = base_panel()
    pad, gap = 76, 12
    side = (SIZE - 2 * pad - gap) // 2
    for row in range(2):
        for col in range(2):
            x = pad + col * (side + gap)
            y = pad + row * (side + gap)
            d.rounded_rectangle([x, y, x + side, y + side], radius=8, fill=GLYPH)
    img.save(path)


def album_cover(path: Path):
    """
    <summary>
    Beamed pair of eighth notes.
    </summary>
    <param name="path">Where the PNG is written.</param>
    """
    img, d = base_panel()
    stem_w = 10
    for hx, hy, sx in ((94, 168, 118), (150, 158, 174)):
        d.ellipse([hx - 16, hy - 12, hx + 16, hy + 12], fill=GLYPH)  # head
        d.rectangle([sx - stem_w, 86 + (hy - 168), sx, hy], fill=GLYPH)  # stem
    d.polygon([(108, 86), (174, 76), (174, 96), (108, 106)], fill=GLYPH)  # beam
    img.save(path)


ICONS = {
    "DefaultVideo.png": video,
    "DefaultVideoCover.png": video_cover,
    "DefaultFolder.png": folder,
    "DefaultActor.png": actor,
    "DefaultAddon.png": addon,
    "DefaultAlbumCover.png": album_cover,
}

for name, fn in ICONS.items():
    fn(OUT / name)
print("Wrote:", *ICONS)
