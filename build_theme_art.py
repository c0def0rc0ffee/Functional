"""
<summary>
Draw the seasonal theme artwork into skin.functional/media/themes/.
</summary>
<remarks>
Everything is drawn from code here, nothing is traced from a film still,
poster or logo: the skin is published, so the art has to be our own.
Run it by hand after changing a drawing; the outputs are committed and the
skin build does not call this.

Two scenes and the sprites that move over them:
  * devilsnight_scene.jpg  the cemetery for 30 October: two headstones,
    Eric Draven and Shelly Webster, under a moon, a city skyline behind.
    The crow lands on the left (Eric's) stone; CROW_PERCH below is that
    point and Includes.xml (ThemeCrow) has the same numbers.
  * halloween_scene.jpg    the haunted hill for the rest of the season.
  * crow_fly/NN.png, crow_perch.png, crow_caw.png  the crow, facing left.
  * bat/NN.png             wing frames for the bats that cross the screen.
  * fog.png                horizontally tileable band, slid in a loop.
  * rain_near.png, rain_far.png  vertically tileable rain, slid in a loop.
  * vignette.png           dark edges, scaled up by Kodi.
  * pumpkin_glow.png       the lantern glow that flickers over the hill.

Photographic artwork is JPEG under the house rules, so the two scenes are
JPEG; anything with transparency is PNG, written with no metadata chunks.
The headstone lettering uses Noto Serif from the system fonts at build
time only; the text is baked into the JPEG and no font ships for it.
A random seed is fixed so a rerun gives the same pictures.
</remarks>
"""
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).parent / "skin.functional" / "media" / "themes"
SERIF = "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf"
SERIF_BOLD = "/usr/share/fonts/truetype/noto/NotoSerif-Bold.ttf"
W, H = 1920, 1080
SS = 2  # supersampling factor for the line art

# Where the crow's feet go on Eric's stone, in screen pixels. ThemeCrow in
# Includes.xml positions the perched sprite from the same numbers.
ERIC_X, SHELLY_X = 840, 1090      # stone centre lines
STONE_TOP = 690                   # top of the rounded head
STONE_W, STONE_H = 200, 270
CROW_PERCH = (ERIC_X, STONE_TOP + 4)

RNG = random.Random(1994)
NP_RNG = np.random.default_rng(1994)


def save_png(img, path):
    """
    <summary>Write a PNG with no ancillary chunks at all.</summary>
    <param name="img">RGBA image.</param>
    <param name="path">Destination.</param>
    <remarks>PIL adds nothing unless asked, but img.info can carry a gamma
    or dpi over from an operation, so it is cleared first.</remarks>
    """
    img.info = {}
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)


def periodic_noise(width, height, scale, seed):
    """
    <summary>Smooth noise that wraps at both edges, values 0 to 1.</summary>
    <param name="width">Width in pixels.</param>
    <param name="height">Height in pixels.</param>
    <param name="scale">Feature size in pixels; bigger is softer.</param>
    <param name="seed">Random seed.</param>
    <returns>A float array, height by width.</returns>
    <remarks>White noise low passed in the frequency domain is periodic by
    construction, which is what lets fog and cloud bands tile in a loop
    with no seam.</remarks>
    """
    rng = np.random.default_rng(seed)
    field = rng.standard_normal((height, width))
    fy = np.fft.fftfreq(height)[:, None]
    fx = np.fft.fftfreq(width)[None, :]
    gauss = np.exp(-((fx ** 2 + fy ** 2) * (scale ** 2) * 6.0))
    out = np.real(np.fft.ifft2(np.fft.fft2(field) * gauss))
    out -= out.min()
    return out / max(out.max(), 1e-9)


def vertical_gradient(top, bottom, height=H, width=W):
    """
    <summary>An RGB image fading from one colour at the top to another at the bottom.</summary>
    <param name="top">RGB tuple at y 0.</param>
    <param name="bottom">RGB tuple at the last row.</param>
    <returns>The image.</returns>
    """
    t = np.linspace(0, 1, height)[:, None, None]
    arr = np.array(top)[None, None, :] * (1 - t) + np.array(bottom)[None, None, :] * t
    arr = np.repeat(arr, width, axis=1)
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def radial_glow(size, colour, power=2.0):
    """
    <summary>A soft round glow, opaque colour at the centre fading to clear.</summary>
    <param name="size">Diameter in pixels.</param>
    <param name="colour">RGB tuple.</param>
    <param name="power">Falloff exponent; higher is a tighter core.</param>
    <returns>An RGBA image.</returns>
    """
    y, x = np.mgrid[0:size, 0:size]
    r = np.hypot(x - size / 2, y - size / 2) / (size / 2)
    alpha = np.clip(1 - r, 0, 1) ** power
    arr = np.zeros((size, size, 4), np.uint8)
    arr[..., :3] = colour
    arr[..., 3] = (alpha * 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def paste_glow(base, size, centre, colour, strength=1.0, power=2.0):
    """
    <summary>Add a radial glow onto an RGB image, screen style.</summary>
    <param name="base">RGB image changed in place.</param>
    <param name="size">Glow diameter.</param>
    <param name="centre">(x, y) of the glow.</param>
    <param name="colour">RGB tuple.</param>
    <param name="strength">0 to 1 multiplier on the glow.</param>
    <param name="power">Falloff exponent.</param>
    """
    glow = radial_glow(size, colour, power)
    a = glow.getchannel("A").point(lambda v: int(v * strength))
    glow.putalpha(a)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(glow, (int(centre[0] - size / 2), int(centre[1] - size / 2)), glow)
    base_arr = np.asarray(base, np.float32)
    lay = np.asarray(layer, np.float32)
    al = lay[..., 3:4] / 255.0
    out = 255 - (255 - base_arr) * (1 - lay[..., :3] / 255.0 * al)
    base.paste(Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB"))


def clouds(base, colour, density, seed, y0=0, y1=H, scale=90):
    """
    <summary>Lay a band of soft periodic cloud over an RGB image.</summary>
    <param name="base">RGB image changed in place.</param>
    <param name="colour">Cloud RGB.</param>
    <param name="density">Peak opacity 0 to 1.</param>
    <param name="seed">Noise seed.</param>
    <param name="y0">Top of the band.</param>
    <param name="y1">Bottom of the band.</param>
    <param name="scale">Feature size.</param>
    """
    n = periodic_noise(W // 4, H // 4, scale / 4, seed)
    n = np.clip((n - 0.45) * 2.2, 0, 1)
    mask = Image.fromarray((n * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
    m = np.asarray(mask, np.float32) / 255.0 * density
    rows = np.arange(H)[:, None]
    band = np.clip(np.minimum((rows - y0) / 120.0, (y1 - rows) / 120.0), 0, 1)
    m *= band
    arr = np.asarray(base, np.float32)
    arr = arr * (1 - m[..., None]) + np.array(colour)[None, None, :] * m[..., None]
    base.paste(Image.fromarray(arr.astype(np.uint8), "RGB"))


def moon(base, centre, radius, tone, seed):
    """
    <summary>A full moon with a halo and faint maria.</summary>
    <param name="base">RGB image changed in place.</param>
    <param name="centre">(x, y).</param>
    <param name="radius">Disc radius in pixels.</param>
    <param name="tone">RGB of the lit surface.</param>
    <param name="seed">Seed for the surface markings.</param>
    """
    paste_glow(base, radius * 7, centre, tone, 0.35, 2.4)
    paste_glow(base, radius * 3, centre, tone, 0.45, 1.6)
    size = radius * 2
    disc = Image.new("L", (size * SS, size * SS), 0)
    ImageDraw.Draw(disc).ellipse([0, 0, size * SS - 1, size * SS - 1], fill=255)
    disc = disc.resize((size, size), Image.LANCZOS)
    surf = np.ones((size, size, 3), np.float32) * np.array(tone)[None, None, :]
    n = periodic_noise(size, size, size / 6, seed)
    maria = np.clip((n - 0.55) * 3, 0, 1)
    surf *= (1 - 0.22 * maria)[..., None]
    y, x = np.mgrid[0:size, 0:size]
    limb = np.clip(np.hypot(x - radius, y - radius) / radius, 0, 1)
    surf *= (1 - 0.18 * limb ** 3)[..., None]
    tile = Image.fromarray(np.clip(surf, 0, 255).astype(np.uint8), "RGB")
    base.paste(tile, (centre[0] - radius, centre[1] - radius), disc)


def bare_tree(draw, x, y, length, angle, width, depth, colour):
    """
    <summary>A leafless tree drawn by recursive branching.</summary>
    <param name="draw">ImageDraw on a supersampled canvas.</param>
    <param name="x">Base x.</param>
    <param name="y">Base y.</param>
    <param name="length">Trunk length.</param>
    <param name="angle">Direction in degrees, 90 is straight up.</param>
    <param name="width">Trunk width.</param>
    <param name="depth">Branching levels left.</param>
    <param name="colour">Fill colour.</param>
    """
    if depth == 0 or length < 4:
        return
    bend = RNG.uniform(-9, 9)
    x2 = x + math.cos(math.radians(angle + bend)) * length
    y2 = y - math.sin(math.radians(angle + bend)) * length
    draw.line([(x, y), (x2, y2)], fill=colour, width=max(1, int(width)))
    draw.ellipse([x2 - width / 2, y2 - width / 2, x2 + width / 2, y2 + width / 2], fill=colour)
    branches = 2 if depth > 2 else RNG.choice((2, 3))
    for i in range(branches):
        spread = RNG.uniform(18, 42) * (1 if i % 2 else -1)
        bare_tree(draw, x2, y2, length * RNG.uniform(0.62, 0.8), angle + spread,
                  width * 0.68, depth - 1, colour)


def headstone(name_lines, light_from_right=True):
    """
    <summary>One rounded headstone with engraved lettering, as RGBA.</summary>
    <param name="name_lines">Lines of the inscription, top to bottom.</param>
    <param name="light_from_right">Moonlight falls on the right edge.</param>
    <returns>RGBA image STONE_W wide, STONE_H plus a plinth tall.</returns>
    <remarks>The stone is a granite noise texture under a side light, the
    lettering cut in with a dark stroke and a pale lower lip so it reads
    as incised. Only the names are carved: the inscriptions on the film's
    stones are not something this was checked against, so nothing else
    is claimed.</remarks>
    """
    sw, sh = STONE_W, STONE_H
    plinth = 26
    img = Image.new("RGBA", (sw + 40, sh + plinth), (0, 0, 0, 0))
    shape = Image.new("L", (sw * SS, sh * SS), 0)
    d = ImageDraw.Draw(shape)
    r = sw * SS // 2
    d.ellipse([0, 0, sw * SS - 1, 2 * r], fill=255)
    d.rectangle([0, r, sw * SS - 1, sh * SS - 1], fill=255)
    shape = shape.resize((sw, sh), Image.LANCZOS)

    n = periodic_noise(sw, sh, 3, RNG.randint(0, 9999))
    n2 = periodic_noise(sw, sh, 18, RNG.randint(0, 9999))
    base = 74 + 22 * (n - 0.5) + 26 * (n2 - 0.5)
    x = np.linspace(0, 1, sw)[None, :]
    side = x if light_from_right else 1 - x
    light = 0.55 + 0.6 * side ** 1.6
    y = np.linspace(0, 1, sh)[:, None]
    light = light * (1.05 - 0.35 * y)
    grey = base * light
    arr = np.stack([grey * 0.95, grey * 0.97, grey * 1.04], -1)
    # moss and weathering near the foot
    moss = np.clip((periodic_noise(sw, sh, 10, RNG.randint(0, 9999)) - 0.5) * 3, 0, 1) * np.clip((y - 0.6) * 3, 0, 1)
    arr = arr * (1 - 0.5 * moss[..., None]) + np.array([30, 42, 28])[None, None, :] * 0.5 * moss[..., None]
    stone = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    stone.putalpha(shape)

    # incised lettering
    draw = ImageDraw.Draw(stone)
    cross_y = 46
    draw.line([(sw / 2, cross_y - 18), (sw / 2, cross_y + 22)], fill=(40, 40, 46, 255), width=5)
    draw.line([(sw / 2 - 14, cross_y - 6), (sw / 2 + 14, cross_y - 6)], fill=(40, 40, 46, 255), width=5)
    draw.line([(sw / 2 + 2, cross_y - 16), (sw / 2 + 2, cross_y + 24)], fill=(150, 150, 158, 160), width=1)
    font = ImageFont.truetype(SERIF_BOLD, 22)
    ty = 92
    for line in name_lines:
        box = draw.textbbox((0, 0), line, font=font)
        tw = box[2] - box[0]
        tx = (sw - tw) / 2 - box[0]
        draw.text((tx + 1, ty + 1), line, font=font, fill=(170, 170, 178, 190))
        draw.text((tx, ty), line, font=font, fill=(18, 18, 22, 255))
        ty += 38
    small = ImageFont.truetype(SERIF, 17)
    rip = "REST IN PEACE"
    box = draw.textbbox((0, 0), rip, font=small)
    draw.text(((sw - (box[2] - box[0])) / 2 + 1, ty + 21), rip, font=small, fill=(150, 150, 158, 120))
    draw.text(((sw - (box[2] - box[0])) / 2, ty + 20), rip, font=small, fill=(40, 40, 46, 230))
    stone.putalpha(Image.fromarray(np.minimum(np.asarray(stone.getchannel("A")),
                                              np.asarray(shape)).astype(np.uint8)))

    img.paste(stone, (20, 0), stone)
    pd = ImageDraw.Draw(img)
    pd.rectangle([6, sh - 2, sw + 33, sh + plinth - 1], fill=(42, 42, 48, 255))
    pd.rectangle([6, sh - 2, sw + 33, sh + 3], fill=(70, 70, 78, 255))
    return img


def city_skyline(draw, y_base, x0, x1, colour, window_colour, seed):
    """
    <summary>A dark city skyline with a few lit windows, Detroit's round towers in it.</summary>
    <param name="draw">ImageDraw on the full size scene.</param>
    <param name="y_base">Ground line the buildings stand on.</param>
    <param name="x0">Left edge of the run.</param>
    <param name="x1">Right edge of the run.</param>
    <param name="colour">Silhouette colour.</param>
    <param name="window_colour">Lit window colour.</param>
    <param name="seed">Seed for heights and windows.</param>
    """
    rng = random.Random(seed)
    x = x0
    while x < x1:
        w = rng.randint(34, 90)
        h = rng.randint(50, 190)
        draw.rectangle([x, y_base - h, x + w, y_base], fill=colour)
        if rng.random() < 0.25:
            draw.rectangle([x + w // 2 - 2, y_base - h - 26, x + w // 2 + 2, y_base - h], fill=colour)
        for wy in range(y_base - h + 10, y_base - 6, 14):
            for wx in range(x + 6, x + w - 6, 11):
                if rng.random() < 0.06:
                    draw.rectangle([wx, wy, wx + 3, wy + 5], fill=window_colour)
        x += w + rng.randint(-6, 8)


def round_towers(draw, cx, y_base, colour, window_colour):
    """
    <summary>A cluster of tall round towers, a nod to the Detroit waterfront.</summary>
    <param name="draw">ImageDraw on the full size scene.</param>
    <param name="cx">Centre x of the cluster.</param>
    <param name="y_base">Ground line.</param>
    <param name="colour">Silhouette colour.</param>
    <param name="window_colour">Lit window colour.</param>
    """
    towers = [(-70, 190, 36), (70, 190, 36), (-38, 230, 40), (38, 230, 40), (0, 330, 54)]
    for dx, h, w in towers:
        x = cx + dx
        draw.rectangle([x - w / 2, y_base - h, x + w / 2, y_base], fill=colour)
        draw.ellipse([x - w / 2, y_base - h - 8, x + w / 2, y_base - h + 8], fill=colour)
        for wy in range(int(y_base - h + 12), y_base - 8, 16):
            if RNG.random() < 0.3:
                draw.rectangle([x - 3, wy, x + 2, wy + 5], fill=window_colour)


def iron_fence(draw, y_top, y_bottom, x0, x1, colour):
    """
    <summary>A cemetery railing of spear topped bars between two rails.</summary>
    <param name="draw">ImageDraw on a supersampled canvas.</param>
    <param name="y_top">Spear tips.</param>
    <param name="y_bottom">Foot of the bars.</param>
    <param name="x0">Left end.</param>
    <param name="x1">Right end.</param>
    <param name="colour">Fill colour.</param>
    """
    step = 22 * SS
    for x in range(int(x0), int(x1), step):
        lean = RNG.uniform(-3, 3) * SS
        draw.line([(x, y_bottom), (x + lean, y_top + 10 * SS)], fill=colour, width=3 * SS)
        draw.polygon([(x + lean - 5 * SS, y_top + 12 * SS), (x + lean, y_top),
                      (x + lean + 5 * SS, y_top + 12 * SS)], fill=colour)
    for ry in (y_top + 22 * SS, y_bottom - 16 * SS):
        draw.line([(x0, ry), (x1, ry)], fill=colour, width=4 * SS)


def ground(base, y_line, colour, seed, amplitude=18):
    """
    <summary>A rolling ground line with grass tufts, filled to the bottom.</summary>
    <param name="base">RGB image changed in place.</param>
    <param name="y_line">Average height of the ground's top edge.</param>
    <param name="colour">Fill colour.</param>
    <param name="seed">Seed for the roll and the tufts.</param>
    <param name="amplitude">How far the line rolls up and down.</param>
    """
    rng = random.Random(seed)
    canvas = Image.new("L", (W * SS, H * SS), 0)
    d = ImageDraw.Draw(canvas)
    pts = []
    phase = rng.uniform(0, 6)
    for x in range(0, W * SS + 1, 8):
        xs = x / SS
        y = y_line + amplitude * math.sin(xs / 260 + phase) + amplitude * 0.5 * math.sin(xs / 90 + phase * 2)
        pts.append((x, y * SS))
    d.polygon(pts + [(W * SS, H * SS), (0, H * SS)], fill=255)
    for x, y in pts[::2]:
        for _ in range(3):
            h = rng.uniform(4, 14) * SS
            lean = rng.uniform(-5, 5) * SS
            d.line([(x + rng.uniform(-4, 4) * SS, y + 2 * SS), (x + lean, y - h)], fill=255, width=SS)
    mask = canvas.resize((W, H), Image.LANCZOS)
    base.paste(Image.new("RGB", (W, H), colour), (0, 0), mask)


def vignette_array(strength=0.75):
    """
    <summary>Darkening factor per pixel, 1 at the centre falling towards the corners.</summary>
    <param name="strength">How dark the corners go, 0 to 1.</param>
    <returns>Float array H by W.</returns>
    """
    y, x = np.mgrid[0:H, 0:W]
    r = np.hypot((x - W / 2) / (W / 2), (y - H / 2) / (H / 2)) / math.sqrt(2)
    return 1 - strength * np.clip((r - 0.35) / 0.65, 0, 1) ** 1.7


def devilsnight_scene():
    """
    <summary>The 30 October cemetery: moon, skyline, railings, a dead tree and the two stones.</summary>
    <remarks>The menu row on Home sits roughly between y 480 and 600 and
    the stats column on the right, so the stones stand in the open band
    below the row, the moon in the sky left of the stats. Kept dark so
    the white menu text still reads over it.</remarks>
    """
    img = vertical_gradient((4, 5, 12), (30, 26, 44))
    clouds(img, (40, 42, 58), 0.55, 11, 0, 700, 140)
    moon(img, (1220, 250), 78, (226, 224, 212), 30)
    clouds(img, (22, 22, 32), 0.6, 12, 150, 420, 70)

    d = ImageDraw.Draw(img)
    horizon = 830
    city = (14, 13, 22)
    lit = (120, 100, 60)
    city_skyline(d, horizon, -20, 560, city, lit, 5)
    round_towers(d, 330, horizon, (12, 11, 19), lit)
    city_skyline(d, horizon, 1380, 1960, city, lit, 6)

    ground(img, 860, (12, 11, 16), 7, 12)

    art = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    ad = ImageDraw.Draw(art)
    iron_fence(ad, 790 * SS, 880 * SS, 420 * SS, 1520 * SS, (8, 8, 12, 255))
    bare_tree(ad, 250 * SS, 930 * SS, 210 * SS, 88, 26 * SS, 9, (6, 6, 9, 255))
    bare_tree(ad, 1640 * SS, 950 * SS, 150 * SS, 95, 18 * SS, 8, (7, 7, 10, 255))
    art = art.resize((W, H), Image.LANCZOS)
    img.paste(art, (0, 0), art)

    ground(img, 930, (8, 8, 11), 8, 8)

    stones = ((ERIC_X, ("ERIC", "DRAVEN")), (SHELLY_X, ("SHELLY", "WEBSTER")))
    # Ground shadows first, both of them, so neither falls across the
    # other stone's plinth.
    for cx, _lines in stones:
        sh = Image.new("RGBA", (STONE_W + 120, 60), (0, 0, 0, 0))
        ImageDraw.Draw(sh).ellipse([0, 0, STONE_W + 119, 59], fill=(0, 0, 0, 170))
        sh = sh.filter(ImageFilter.GaussianBlur(10))
        img.paste(sh, (cx - STONE_W // 2 - 80, STONE_TOP + STONE_H - 10), sh)
    for cx, lines in stones:
        stone = headstone(lines)
        img.paste(stone, (cx - STONE_W // 2 - 20, STONE_TOP), stone)

    # a single red rose laid at the foot of Shelly's stone
    rose = Image.new("RGBA", (90 * SS, 40 * SS), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rose)
    rd.line([(8 * SS, 30 * SS), (70 * SS, 22 * SS)], fill=(20, 50, 22, 255), width=3 * SS)
    rd.polygon([(30 * SS, 27 * SS), (40 * SS, 18 * SS), (44 * SS, 26 * SS)], fill=(24, 60, 26, 255))
    rd.ellipse([66 * SS, 10 * SS, 86 * SS, 30 * SS], fill=(120, 8, 16, 255))
    rd.arc([70 * SS, 14 * SS, 82 * SS, 26 * SS], 30, 300, fill=(70, 0, 8, 255), width=2 * SS)
    rose = rose.resize((90, 40), Image.LANCZOS)
    img.paste(rose, (SHELLY_X - 30, STONE_TOP + STONE_H + 2), rose)

    # ground mist and a vignette baked in; the animated fog sits on top
    mist = periodic_noise(W // 4, 80, 10, 21)
    mist = Image.fromarray((mist * 255).astype(np.uint8)).resize((W, 320), Image.BICUBIC)
    m = np.asarray(mist, np.float32) / 255.0
    rows = np.linspace(0, 1, 320)[:, None]
    m = m * np.clip(rows * 1.4, 0, 1) * 0.35
    arr = np.asarray(img, np.float32)
    arr[H - 320:] = arr[H - 320:] * (1 - m[..., None]) + np.array([70, 72, 88])[None, None, :] * m[..., None]
    arr *= vignette_array(0.7)[..., None]
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    img.save(OUT / "devilsnight_scene.jpg", "JPEG", quality=88, optimize=True, progressive=True)


def pumpkin(size, seed):
    """
    <summary>A carved jack o'lantern, lit from inside, as RGBA.</summary>
    <param name="size">Width in pixels; height is about 0.8 of it.</param>
    <param name="seed">Varies the carved face.</param>
    <returns>The image.</returns>
    """
    rng = random.Random(seed)
    w, h = size * SS, int(size * 0.85) * SS
    img = Image.new("RGBA", (w, h + 30 * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    top = 30 * SS
    for i, frac in enumerate((0.0, 0.18, 0.34, 0.5, 0.66, 0.82)):
        lobe_w = w * 0.42
        cx = w * 0.29 + frac * w * 0.5
        shade = 150 + int(40 * math.sin(math.pi * (frac + 0.1)))
        d.ellipse([cx - lobe_w / 2, top, cx + lobe_w / 2, top + h - 1],
                  fill=(shade, int(shade * 0.42), 10, 255))
    d.polygon([(w * 0.47, top + 6 * SS), (w * 0.5, 4 * SS), (w * 0.57, 0), (w * 0.55, top + 8 * SS)],
              fill=(50, 60, 20, 255))
    glow = (255, 200, 60, 255)
    ey = top + h * 0.32
    for ex in (0.32, 0.68):
        x = w * ex
        d.polygon([(x - 18 * SS, ey + 22 * SS), (x, ey - 6 * SS), (x + 18 * SS, ey + 22 * SS)], fill=glow)
    d.polygon([(w * 0.5 - 8 * SS, ey + 40 * SS), (w * 0.5, ey + 28 * SS), (w * 0.5 + 8 * SS, ey + 40 * SS)], fill=glow)
    my = top + h * 0.68
    mouth = []
    teeth = rng.choice((3, 4))
    for i in range(teeth * 2 + 1):
        x = w * 0.22 + i * (w * 0.56) / (teeth * 2)
        mouth.append((x, my + (0 if i % 2 else -12 * SS)))
    for i in range(teeth * 2, -1, -1):
        x = w * 0.22 + i * (w * 0.56) / (teeth * 2)
        mouth.append((x, my + 30 * SS - (10 * SS if i % 2 else 0) - abs(i - teeth) * 2 * SS))
    d.polygon(mouth, fill=glow)
    return img.resize((size, int((h + 30 * SS) / SS)), Image.LANCZOS)


PUMPKINS = ((430, 905, 150, 3), (1330, 925, 120, 8), (560, 960, 90, 5))


def haunted_house(draw, x, y, s, colour, window):
    """
    <summary>A crooked gothic house silhouette with towers and lit windows.</summary>
    <param name="draw">ImageDraw on a supersampled canvas.</param>
    <param name="x">Left of the main block, supersampled pixels.</param>
    <param name="y">Ground line, supersampled pixels.</param>
    <param name="s">Scale, supersampled pixels per unit.</param>
    <param name="colour">Silhouette colour.</param>
    <param name="window">Lit window colour.</param>
    """
    def r(a, b, c, e, fill=colour):
        draw.rectangle([x + a * s, y - e * s, x + c * s, y - b * s], fill=fill)

    def roof(a, c, base, peak, lean=0):
        draw.polygon([(x + a * s, y - base * s), (x + (a + c) / 2 * s + lean * s, y - peak * s),
                      (x + c * s, y - base * s)], fill=colour)

    r(0, 0, 60, 34)
    roof(-4, 64, 34, 62, 2)
    r(-22, 0, 4, 58)
    roof(-26, 8, 58, 92, -1)
    r(54, 0, 76, 46)
    roof(50, 80, 46, 70, 1)
    r(24, 50, 28, 68)
    for wx, wy in ((8, 12), (22, 12), (38, 12), (8, 24), (40, 24), (-14, 30), (-14, 44), (62, 22)):
        lit = RNG.random() < 0.6
        draw.rectangle([x + wx * s, y - (wy + 7) * s, x + (wx + 5) * s, y - wy * s],
                       fill=window if lit else (20, 12, 10, 255))
    draw.ellipse([x + 24 * s, y - 50 * s, x + 32 * s, y - 42 * s], fill=window)


def halloween_scene():
    """
    <summary>The 29 and 31 October backdrop: blood moon, haunted house on a hill, lanterns.</summary>
    <remarks>The lanterns sit at PUMPKINS; ThemeLanterns in Includes.xml
    puts the flickering glow over the same points.</remarks>
    """
    img = vertical_gradient((6, 2, 6), (58, 14, 10))
    clouds(img, (60, 16, 18), 0.45, 41, 0, 760, 150)
    moon(img, (960, 300), 150, (186, 44, 28), 44)
    clouds(img, (18, 6, 8), 0.7, 42, 220, 470, 60)

    hill = Image.new("L", (W * SS, H * SS), 0)
    hd = ImageDraw.Draw(hill)
    pts = [(x, (820 - 120 * math.exp(-((x / SS - 1000) / 380) ** 2)) * SS) for x in range(0, W * SS + 1, 8)]
    hd.polygon(pts + [(W * SS, H * SS), (0, H * SS)], fill=255)
    img.paste(Image.new("RGB", (W, H), (14, 6, 8)), (0, 0), hill.resize((W, H), Image.LANCZOS))

    art = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    ad = ImageDraw.Draw(art)
    haunted_house(ad, 930 * SS, 712 * SS, 3.1 * SS, (8, 3, 5, 255), (255, 170, 60, 255))
    bare_tree(ad, 230 * SS, 960 * SS, 230 * SS, 84, 28 * SS, 9, (5, 2, 4, 255))
    bare_tree(ad, 1700 * SS, 960 * SS, 200 * SS, 97, 24 * SS, 9, (5, 2, 4, 255))
    bare_tree(ad, 760 * SS, 740 * SS, 70 * SS, 92, 8 * SS, 6, (8, 3, 5, 255))
    # leaning crosses on the hillside
    for cx, cy, lean in ((640, 830, -8), (720, 805, 5), (1300, 800, 10), (1420, 835, -4)):
        a = math.radians(lean)
        def p(dx, dy):
            return ((cx + dx * math.cos(a) - dy * math.sin(a)) * SS, (cy + dx * math.sin(a) + dy * math.cos(a)) * SS)
        ad.line([p(0, 0), p(0, -46)], fill=(8, 3, 5, 255), width=6 * SS)
        ad.line([p(-14, -32), p(14, -32)], fill=(8, 3, 5, 255), width=6 * SS)
    # still bats against the moon
    for bx, by, bs in ((900, 250, 0.5), (1010, 330, 0.4), (1080, 230, 0.32)):
        ad.polygon(bat_points(bx * SS, by * SS, bs * SS * 60, 0.3), fill=(10, 3, 5, 255))
    art = art.resize((W, H), Image.LANCZOS)
    img.paste(art, (0, 0), art)

    ground(img, 950, (6, 3, 4), 47, 10)
    for x, y, size, seed in PUMPKINS:
        pk = pumpkin(size, seed)
        img.paste(pk, (x - size // 2, y - pk.height // 2), pk)
    for x, y, size, _seed in PUMPKINS:
        paste_glow(img, size * 3, (x, y), (255, 120, 20), 0.35, 2.2)

    arr = np.asarray(img, np.float32) * vignette_array(0.75)[..., None]
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    img.save(OUT / "halloween_scene.jpg", "JPEG", quality=88, optimize=True, progressive=True)


def pumpkin_glow():
    """
    <summary>The warm glow laid over each lantern, faded in and out by Kodi to flicker.</summary>
    """
    g = radial_glow(256, (255, 150, 40), 1.8)
    save_png(g, OUT / "pumpkin_glow.png")


def crow_body(draw, cx, cy, s, colour, head_up=False, beak_open=False):
    """
    <summary>A perched crow facing left: body, head, beak, tail and feet.</summary>
    <param name="draw">ImageDraw on a supersampled canvas.</param>
    <param name="cx">Where the feet grip, x.</param>
    <param name="cy">Where the feet grip, y.</param>
    <param name="s">Pixels per unit; the bird is about 100 units tall.</param>
    <param name="colour">Silhouette colour.</param>
    <param name="head_up">Raise the head for a caw.</param>
    <param name="beak_open">Open the beak.</param>
    """
    def P(x, y):
        return (cx + x * s, cy - y * s)

    # tail, angled down behind the bird
    draw.polygon([P(18, 34), P(62, 4), P(70, 10), P(30, 46)], fill=colour)
    # body
    draw.polygon([P(-20, 52), P(-10, 70), P(16, 66), P(34, 46), P(26, 22), P(4, 14), P(-14, 22), P(-22, 38)],
                 fill=colour)
    hx, hy = (-20, 84) if head_up else (-18, 74)
    # neck and head
    draw.polygon([P(-24, 56), P(hx - 4, hy + 4), P(hx + 14, hy + 8), P(-2, 64)], fill=colour)
    draw.ellipse([P(hx - 12, hy + 12)[0], P(hx - 12, hy + 12)[1], P(hx + 12, hy - 12)[0], P(hx + 12, hy - 12)[1]],
                 fill=colour)
    # beak
    if beak_open:
        draw.polygon([P(hx - 8, hy + 6), P(hx - 34, hy + 10), P(hx - 10, hy + 1)], fill=colour)
        draw.polygon([P(hx - 9, hy - 2), P(hx - 30, hy - 10), P(hx - 7, hy - 6)], fill=colour)
    else:
        draw.polygon([P(hx - 8, hy + 6), P(hx - 32, hy + 1), P(hx - 7, hy - 5)], fill=colour)
    # legs and toes gripping the stone
    for lx in (-4, 8):
        draw.line([P(lx, 16), P(lx - 2, 0)], fill=colour, width=int(3 * s))
        draw.line([P(lx - 2, 0), P(lx - 10, -2)], fill=colour, width=int(2.4 * s))
        draw.line([P(lx - 2, 0), P(lx + 6, -2)], fill=colour, width=int(2.4 * s))
    # folded wing edge, a faint blue sheen
    draw.line([P(-10, 58), P(18, 50), P(46, 26)], fill=(52, 58, 82, 255), width=int(2 * s))
    draw.ellipse([P(hx - 6, hy + 4)[0], P(hx - 6, hy + 4)[1], P(hx - 2, hy)[0], P(hx - 2, hy)[1]],
                 fill=(80, 90, 110, 255))


def perched_crows():
    """
    <summary>The perched crow, beak shut and mid caw; feet at the bottom centre of a 160 square.</summary>
    <remarks>ThemeCrow places the 160 by 160 sprite with its bottom centre
    on CROW_PERCH, so the feet must stay at (80, 156).</remarks>
    """
    for name, up, open_ in (("crow_perch.png", False, False), ("crow_caw.png", True, True)):
        img = Image.new("RGBA", (160 * SS, 160 * SS), (0, 0, 0, 0))
        crow_body(ImageDraw.Draw(img), 80 * SS, 156 * SS, 1.25 * SS, (6, 6, 10, 255), up, open_)
        save_png(img.resize((160, 160), Image.LANCZOS), OUT / name)


def wing_points(sx, sy, s, angle, span=1.0):
    """
    <summary>A crow's wing seen side on, as a polygon with fingered primaries.</summary>
    <param name="sx">Shoulder x.</param>
    <param name="sy">Shoulder y.</param>
    <param name="s">Pixels per unit.</param>
    <param name="angle">Wing angle in degrees: 90 straight up, -90 straight down.</param>
    <param name="span">Visible length 0 to 1; a wing level with the body points
    at the viewer, so it is drawn short there and full length at the top and
    bottom of the stroke.</param>
    <returns>Polygon points.</returns>
    <remarks>The bird flies left, so the chord, from the leading edge to
    the trailing feathers, always points right, towards the tail.</remarks>
    """
    a = math.radians(angle)
    length = 78 * span
    ux, uy = math.cos(a), -math.sin(a)
    cx_, cy_ = math.sin(a), math.cos(a)
    if cx_ < 0 or (abs(cx_) < 1e-6 and cy_ < 0):
        cx_, cy_ = -cx_, -cy_

    def at(u, v):
        v *= 1.7
        return (sx + (ux * u * length + cx_ * v) * s, sy + (uy * u * length + cy_ * v) * s)

    pts = [at(0, -4), at(0.55, -3), at(0.9, -1), at(1.0, 2)]
    fingers = ((0.97, 8), (0.92, 13), (0.85, 18), (0.77, 22))
    for u, v in fingers:
        pts.append(at(u - 0.06, v - 3))
        pts.append(at(u, v + 2))
    pts += [at(0.6, 30), at(0.3, 32), at(0.0, 26)]
    return pts


def flying_crows():
    """
    <summary>Six wing beat frames of the crow flying left, 240 by 160, body centred.</summary>
    <remarks>One full beat: up, coming down past level, down, and back up.
    The far wing is drawn first and lighter, offset back along the body,
    so the beat reads in silhouette. Frames are numbered 00 to 05 because
    Kodi's multiimage plays a folder in name order.</remarks>
    """
    beat = ((80, 1.0), (35, 0.55), (-10, 0.3), (-60, 0.85), (-80, 1.0), (10, 0.35))
    for i, (ang, span) in enumerate(beat):
        img = Image.new("RGBA", (240 * SS, 160 * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        s = 1.0 * SS
        cx, cy = 120 * SS, 80 * SS
        body = (6, 6, 10, 255)
        d.polygon(wing_points(cx + 2 * s, cy - 6 * s, s, ang * 0.85, span * 0.85), fill=(28, 28, 38, 255))
        # body pointing left: head and beak at the left, tail fan at the right
        d.polygon([(cx - 56 * s, cy - 6 * s), (cx - 30 * s, cy - 13 * s), (cx + 20 * s, cy - 10 * s),
                   (cx + 44 * s, cy - 4 * s), (cx + 44 * s, cy + 6 * s), (cx + 10 * s, cy + 12 * s),
                   (cx - 40 * s, cy + 8 * s)], fill=body)
        d.ellipse([cx - 74 * s, cy - 15 * s, cx - 48 * s, cy + 7 * s], fill=body)
        d.polygon([(cx - 70 * s, cy - 8 * s), (cx - 98 * s, cy - 2 * s), (cx - 70 * s, cy + 3 * s)], fill=body)
        d.polygon([(cx + 40 * s, cy - 5 * s), (cx + 80 * s, cy - 13 * s), (cx + 86 * s, cy + 0 * s),
                   (cx + 80 * s, cy + 12 * s), (cx + 40 * s, cy + 7 * s)], fill=body)
        d.ellipse([cx - 66 * s, cy - 8 * s, cx - 62 * s, cy - 4 * s], fill=(80, 90, 110, 255))
        d.polygon(wing_points(cx - 8 * s, cy - 4 * s, s, ang, span), fill=body)
        save_png(img.resize((240, 160), Image.LANCZOS), OUT / "crow_fly" / "{0:02d}.png".format(i))


def bat_points(cx, cy, s, flap):
    """
    <summary>A bat silhouette as one polygon, wings scalloped.</summary>
    <param name="cx">Centre x.</param>
    <param name="cy">Centre y.</param>
    <param name="s">Half span in pixels.</param>
    <param name="flap">-1 wings down to 1 wings up.</param>
    <returns>Polygon points.</returns>
    """
    lift = flap * 0.55
    pts = [(cx, cy - 0.18 * s), (cx + 0.06 * s, cy - 0.3 * s), (cx + 0.1 * s, cy - 0.16 * s)]
    right = [(0.25, -0.12), (0.6, -0.25), (1.0, -0.35), (0.85, -0.05), (0.7, 0.05),
             (0.55, -0.02), (0.42, 0.1), (0.28, 0.02), (0.12, 0.16)]
    for x, y in right:
        pts.append((cx + x * s, cy + (y - lift * x) * s))
    pts.append((cx, cy + 0.26 * s))
    for x, y in reversed(right):
        pts.append((cx - x * s, cy + (y - lift * x) * s))
    pts += [(cx - 0.1 * s, cy - 0.16 * s), (cx - 0.06 * s, cy - 0.3 * s)]
    return pts


def bats():
    """
    <summary>Four wing frames of a bat, 120 by 80, played in a loop as it crosses the screen.</summary>
    """
    for i, flap in enumerate((1.0, 0.2, -0.8, 0.0)):
        img = Image.new("RGBA", (120 * SS, 80 * SS), (0, 0, 0, 0))
        ImageDraw.Draw(img).polygon(bat_points(60 * SS, 40 * SS, 56 * SS, flap), fill=(8, 4, 8, 255))
        save_png(img.resize((120, 80), Image.LANCZOS), OUT / "bat" / "{0:02d}.png".format(i))


def fog():
    """
    <summary>A soft fog band 1920 by 360 that tiles left to right, densest at the foot.</summary>
    """
    n = periodic_noise(W // 4, 90, 14, 61)
    n2 = periodic_noise(W // 4, 90, 5, 62)
    v = np.clip(0.7 * n + 0.3 * n2, 0, 1)
    v = np.clip((v - 0.3) * 1.8, 0, 1)
    rows = np.linspace(0, 1, 90)[:, None]
    v *= np.clip(rows * 1.6, 0, 1) ** 1.2
    alpha = Image.fromarray((v * 200).astype(np.uint8)).resize((W, 360), Image.BICUBIC)
    img = Image.new("RGBA", (W, 360), (176, 172, 190, 0))
    img.putalpha(alpha)
    save_png(img, OUT / "fog.png")


def rain(name, count, length, alpha, width, seed):
    """
    <summary>A 960 by 540 rain tile that wraps top to bottom, scaled up 2x by Kodi.</summary>
    <param name="name">Output file name.</param>
    <param name="count">Number of streaks.</param>
    <param name="length">Typical streak length in tile pixels.</param>
    <param name="alpha">Peak streak opacity.</param>
    <param name="width">Stroke width.</param>
    <param name="seed">Seed.</param>
    <remarks>A streak that runs off the bottom is drawn again from the top
    so the slide loop has no seam.</remarks>
    """
    tw, th = 960, 540
    rng = random.Random(seed)
    img = Image.new("RGBA", (tw * SS, th * SS), (200, 210, 230, 0))
    d = ImageDraw.Draw(img)
    for _ in range(count):
        x = rng.uniform(0, tw) * SS
        y = rng.uniform(0, th) * SS
        L = rng.uniform(0.6, 1.3) * length * SS
        a = rng.randint(alpha // 2, alpha)
        for oy in (0, -th * SS, th * SS):
            d.line([(x, y + oy), (x - L * 0.06, y + L + oy)], fill=(200, 210, 230, a), width=width * SS)
    save_png(img.resize((tw, th), Image.LANCZOS), OUT / name)


def vignette():
    """
    <summary>Dark corners at 480 by 270, stretched to the screen by Kodi.</summary>
    """
    y, x = np.mgrid[0:270, 0:480]
    r = np.hypot((x - 240) / 240, (y - 135) / 135) / math.sqrt(2)
    a = np.clip((r - 0.3) / 0.7, 0, 1) ** 1.6 * 235
    img = Image.new("RGBA", (480, 270), (0, 0, 0, 0))
    img.putalpha(Image.fromarray(a.astype(np.uint8)))
    save_png(img, OUT / "vignette.png")


def main():
    """
    <summary>Draw every theme image.</summary>
    """
    OUT.mkdir(parents=True, exist_ok=True)
    devilsnight_scene()
    halloween_scene()
    pumpkin_glow()
    perched_crows()
    flying_crows()
    bats()
    fog()
    rain("rain_far.png", 520, 26, 70, 1, 71)
    rain("rain_near.png", 180, 44, 110, 1, 72)
    vignette()
    for path in sorted(OUT.rglob("*")):
        if path.is_file():
            print("{0:>9,}  {1}".format(path.stat().st_size, path.relative_to(OUT.parent.parent)))


if __name__ == "__main__":
    main()
