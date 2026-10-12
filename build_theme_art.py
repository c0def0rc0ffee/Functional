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
  * spider_PATH/NN.png     a spider's gait, turned for each crawl path.
  * witch_rtl/, witch_ltr/ a witch on a broomstick, both ways.
  * ghost/NN.png           a sheet ghost with a waving hem.
  * christmas_scene.jpg    the snowy village for Christmas, tree, church
    and the long roof the sleigh lands on (XMAS_RIDGE).
  * sleigh_rtl/, sleigh_ltr/, sleigh_parked.png  Santa and four reindeer.
  * robin/NN.png, snow_far.png, snow_near.png, frost.png, light_glow.png
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
import sys
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


# Spider paths in screen pixels, start and end of the sprite's top left
# corner. ThemeSpider in Includes.xml slides the 96 by 96 sprite along the
# same lines; each path gets its own frames turned to face its heading.
SPIDER_PATHS = {
    "a": ((-120, 860), (2040, 860)),     # along the foot, left to right
    "b": ((2040, 250), (-120, 250)),     # across the top, right to left
    "c": ((1560, -120), (360, 1200)),    # top right, down to the bottom left
    "d": ((240, 1200), (1500, -120)),    # bottom left, up to the top right
    "drop": ((1300, -120), (1300, 560)), # down a thread and back up
}


def spider_frame(phase):
    """
    <summary>One spider facing up the canvas, legs at a point in the gait, 96 square RGBA.</summary>
    <param name="phase">Gait position in radians; four frames step it by a quarter turn.</param>
    <returns>The image.</returns>
    <remarks>Legs move in two alternating sets of four (left 1 and 3 with
    right 2 and 4), the way a spider walks, so the frames read as a
    scuttle rather than a wave.</remarks>
    """
    s = SS
    img = Image.new("RGBA", (96 * s, 96 * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    body = (10, 8, 10, 255)
    cx, cy = 48 * s, 40 * s
    bases = (-58, -22, 14, 48)  # degrees from straight out sideways, negative forward
    for side in (-1, 1):
        for i, base in enumerate(bases):
            set_a = (i % 2 == 0) == (side < 0)
            swing = 14 * math.sin(phase + (0 if set_a else math.pi))
            ang = math.radians(base + swing)
            hip = (cx + side * 6 * s, cy + (i - 1.5) * 4 * s)
            knee = (hip[0] + side * math.cos(ang) * 20 * s, hip[1] + math.sin(ang) * 20 * s - 10 * s)
            foot = (knee[0] + side * math.cos(ang) * 16 * s, knee[1] + math.sin(ang) * 18 * s + 14 * s)
            d.line([hip, knee], fill=body, width=3 * s)
            d.line([knee, foot], fill=body, width=2 * s)
    d.ellipse([cx - 15 * s, cy + 4 * s, cx + 15 * s, cy + 42 * s], fill=body)
    d.ellipse([cx - 10 * s, cy - 12 * s, cx + 10 * s, cy + 10 * s], fill=body)
    d.line([(cx - 3 * s, cy - 12 * s), (cx - 5 * s, cy - 17 * s)], fill=body, width=2 * s)
    d.line([(cx + 3 * s, cy - 12 * s), (cx + 5 * s, cy - 17 * s)], fill=body, width=2 * s)
    # an hourglass mark and two glints, so it is not just a blot
    d.polygon([(cx - 4 * s, cy + 16 * s), (cx + 4 * s, cy + 16 * s), (cx, cy + 23 * s)], fill=(150, 10, 16, 255))
    d.polygon([(cx - 4 * s, cy + 30 * s), (cx + 4 * s, cy + 30 * s), (cx, cy + 23 * s)], fill=(150, 10, 16, 255))
    for ex in (-4, 4):
        d.ellipse([cx + (ex - 1.5) * s, cy - 9 * s, cx + (ex + 1.5) * s, cy - 6 * s], fill=(120, 110, 120, 255))
    return img.resize((96, 96), Image.LANCZOS)


def spiders():
    """
    <summary>Four gait frames per spider path, turned to face the way that path runs.</summary>
    <remarks>Written to spider_PATH/NN.png. The drop path faces down.</remarks>
    """
    frames = [spider_frame(i * math.pi / 2) for i in range(4)]
    for name, ((x0, y0), (x1, y1)) in SPIDER_PATHS.items():
        heading = math.degrees(math.atan2(x1 - x0, -(y1 - y0)))  # clockwise from straight up
        for i, frame in enumerate(frames):
            turned = frame.rotate(-heading, resample=Image.BICUBIC)
            save_png(turned, OUT / "spider_{0}".format(name) / "{0:02d}.png".format(i))


def witch_frame(flutter):
    """
    <summary>A witch on a broomstick flying left, 240 by 150 RGBA silhouette.</summary>
    <param name="flutter">0 to 1, how far the cape, hair and bristles stream back.</param>
    <returns>The image.</returns>
    <remarks>Hunched forward over the stick, head clear of the hat brim
    and the cape thin and ragged, so the outline still says witch at the
    size and speed she crosses the screen.</remarks>
    """
    s = SS
    img = Image.new("RGBA", (240 * s, 150 * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ink = (10, 6, 10, 255)

    def P(x, y):
        return (x * s, y * s)

    # broomstick and bristles
    d.line([P(16, 106), P(192, 94)], fill=ink, width=4 * s)
    spread = 9 + 7 * flutter
    d.polygon([P(186, 90), P(232, 86 - spread), P(228, 98), P(234, 110 + spread * 0.6), P(186, 101)], fill=ink)
    d.line([P(184, 88), P(184, 104)], fill=ink, width=3 * s)
    # cape: thin, ragged, streaming back from the shoulders
    t = 30 * flutter
    d.polygon([P(118, 52), P(146, 54), P(174 + t, 52 - 8 * flutter), P(160 + t * 0.6, 62),
               P(184 + t, 68 - 4 * flutter), P(158 + t * 0.4, 74), P(170 + t * 0.7, 84), P(136, 88)], fill=ink)
    # hunched body on the stick
    d.polygon([P(100, 60), P(116, 50), P(132, 58), P(138, 92), P(118, 98), P(80, 96), P(80, 90),
               P(104, 86)], fill=ink)
    # arm reaching forward to the stick, hand on it
    d.line([P(108, 62), P(86, 80), P(70, 100)], fill=ink, width=5 * s)
    # shin forward and a pointed boot
    d.polygon([P(82, 92), P(64, 108), P(70, 112), P(90, 98)], fill=ink)
    d.polygon([P(66, 106), P(50, 110), P(68, 114)], fill=ink)
    # head below the brim, hooked nose, pointed chin
    d.ellipse([P(97, 33)[0], P(97, 33)[1], P(115, 51)[0], P(115, 51)[1]], fill=ink)
    d.polygon([P(99, 40), P(86, 48), P(99, 46)], fill=ink)
    d.polygon([P(101, 48), P(94, 56), P(106, 50)], fill=ink)
    # hair streaming back from under the hat
    d.polygon([P(112, 36), P(132 + 10 * flutter, 42), P(126 + 8 * flutter, 46), P(134 + 10 * flutter, 50),
               P(114, 48)], fill=ink)
    # hat: a wide brim, then a tall cone bending back at the tip
    d.polygon([P(86, 35), P(130, 28), P(132, 32), P(88, 39)], fill=ink)
    d.polygon([P(98, 34), P(120, 30), P(118, 14), P(126, 2), P(136 + 4 * flutter, 4 + 2 * flutter),
               P(124, 8), P(112, 16)], fill=ink)
    return img.resize((240, 150), Image.LANCZOS)


def witches():
    """
    <summary>Three cape frames of the witch, flying left (rtl) and mirrored flying right (ltr).</summary>
    """
    for i, flutter in enumerate((0.0, 0.55, 1.0)):
        frame = witch_frame(flutter)
        save_png(frame, OUT / "witch_rtl" / "{0:02d}.png".format(i))
        save_png(frame.transpose(Image.FLIP_LEFT_RIGHT), OUT / "witch_ltr" / "{0:02d}.png".format(i))


def ghost_frame(wave):
    """
    <summary>A sheet ghost with a waving hem and a soft glow, 140 by 170 RGBA.</summary>
    <param name="wave">Hem phase in radians.</param>
    <returns>The image.</returns>
    <remarks>Drawn translucent so the background shows through it; Kodi
    fades it further in and out as it drifts.</remarks>
    """
    s = SS
    w, h = 140 * s, 170 * s
    sheet = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(sheet)
    d.ellipse([28 * s, 14 * s, 112 * s, 98 * s], fill=255)
    hem = [(28 * s, 56 * s)]
    for k in range(9):
        x = 28 + k * 84 / 8
        y = 140 + 10 * math.sin(wave + k * 1.3) + (8 if k % 2 else -4)
        hem.append((x * s, y * s))
    hem.append((112 * s, 56 * s))
    d.polygon(hem, fill=255)
    # arms raised a little, sleeves hanging
    d.polygon([(30 * s, 70 * s), (8 * s, 84 * s + 6 * math.sin(wave) * s), (30 * s, 96 * s)], fill=255)
    d.polygon([(110 * s, 70 * s), (132 * s, 80 * s - 6 * math.sin(wave) * s), (110 * s, 94 * s)], fill=255)
    sheet = sheet.resize((140, 170), Image.LANCZOS)
    glow = sheet.filter(ImageFilter.GaussianBlur(9))
    alpha = np.maximum(np.asarray(sheet, np.float32) * 0.78, np.asarray(glow, np.float32) * 0.5)
    shade = 0.82 + 0.18 * np.linspace(1, 0, 170)[:, None]
    rgb = np.stack([235 * shade, 238 * shade, 248 * shade], -1) * np.ones((170, 140, 1))
    img = Image.fromarray(np.dstack([rgb, alpha]).astype(np.uint8), "RGBA")
    d = ImageDraw.Draw(img)
    for ex in (54, 82):
        d.ellipse([ex - 7, 46, ex + 7, 64], fill=(20, 16, 24, 230))
    d.ellipse([60, 72, 76, 92], fill=(20, 16, 24, 210))
    return img


def ghosts():
    """
    <summary>Three hem frames of the ghost, played in a loop as it drifts.</summary>
    """
    for i in range(3):
        save_png(ghost_frame(i * 2 * math.pi / 3), OUT / "ghost" / "{0:02d}.png".format(i))


# ===== Christmas =====
# Positions the skin repeats: ChristmasLayers in Includes.xml puts the
# tree lights, the robin and the parked sleigh on these points.
XMAS_MOON = (1230, 190)
XMAS_RIDGE = (1140, 652)          # centre of the long roof's ridge, where the sleigh parks
XMAS_TREE = (330, 960, 340)       # trunk foot x, y and height
XMAS_ROBIN = (1480, 902)          # top of the fence post the robin sits on


def xmas_tree_lights():
    """
    <summary>Where the lights hang on the tree, with each one's colour name.</summary>
    <returns>List of (x, y, colour) in screen pixels, top to bottom; the first is the star.</returns>
    <remarks>Fixed by a seed so the art and the XML agree; print them with
    --lights and copy them into ChristmasLayers when the tree moves.</remarks>
    """
    rng = random.Random(1225)
    x0, base, height = XMAS_TREE
    top = base - height
    lights = [(x0, top - 6, "gold")]
    colours = ("red", "gold", "green", "blue")
    for tier in range(5):
        y = top + 50 + tier * 54
        half = 22 + tier * 24
        for k in range(3 + tier // 2):
            frac = (k + 0.5) / (3 + tier // 2)
            x = x0 - half + frac * 2 * half + rng.uniform(-8, 8)
            lights.append((int(x), int(y + rng.uniform(-6, 10)), colours[(tier + k) % 4]))
    return lights


def snowy_roof_house(draw, x, base, w, wall_h, roof_h, colour, snow, window, rng, chimney=False, ridge=0):
    """
    <summary>A village house with a snow capped roof and lit windows.</summary>
    <param name="draw">ImageDraw on a supersampled canvas.</param>
    <param name="x">Left wall, supersampled pixels.</param>
    <param name="base">Ground line, supersampled pixels.</param>
    <param name="w">Width.</param>
    <param name="wall_h">Wall height.</param>
    <param name="roof_h">Roof height.</param>
    <param name="colour">Wall and roof colour.</param>
    <param name="snow">Snow colour.</param>
    <param name="window">Lit window colour.</param>
    <param name="rng">Random source for the windows.</param>
    <param name="chimney">Add a chimney at the right end of the roof.</param>
    <param name="ridge">Length of a flat ridge; 0 gives a plain gable.</param>
    """
    top = base - wall_h
    draw.rectangle([x, top, x + w, base], fill=colour)
    cx = x + w / 2
    over = w * 0.08
    draw.polygon([(x - over, top), (cx - ridge / 2, top - roof_h), (cx + ridge / 2, top - roof_h), (x + w + over, top)], fill=colour)
    # snow lying along the roof, thicker on the ridge
    t = max(6, int(w * 0.05))
    draw.polygon([(x - over, top), (cx - ridge / 2, top - roof_h), (cx + ridge / 2, top - roof_h), (x + w + over, top),
                  (x + w + over - t, top + t * 0.6), (cx + ridge / 2, top - roof_h + t * 1.4),
                  (cx - ridge / 2, top - roof_h + t * 1.4), (x - over + t, top + t * 0.6)], fill=snow)
    if chimney:
        chx = cx + ridge / 2 + w * 0.12
        draw.rectangle([chx, top - roof_h - w * 0.06, chx + w * 0.09, top - roof_h * 0.45], fill=colour)
        draw.rectangle([chx - w * 0.01, top - roof_h - w * 0.075, chx + w * 0.1, top - roof_h - w * 0.05], fill=snow)
    cols = max(2, int(w / (55 * SS)))
    for c in range(cols):
        wx = x + (c + 0.5) * w / cols - 9 * SS
        for r in range(max(1, int(wall_h / (60 * SS)))):
            wy = top + 18 * SS + r * 52 * SS
            lit = rng.random() < 0.75
            draw.rectangle([wx, wy, wx + 18 * SS, wy + 24 * SS], fill=window if lit else (30, 34, 52, 255))
            draw.line([(wx + 9 * SS, wy), (wx + 9 * SS, wy + 24 * SS)], fill=colour, width=SS)
            draw.line([(wx, wy + 12 * SS), (wx + 18 * SS, wy + 12 * SS)], fill=colour, width=SS)
    draw.rectangle([cx - 10 * SS, base - 36 * SS, cx + 10 * SS, base], fill=(60, 30, 20, 255))


def christmas_tree(draw, x0, base, height, rng):
    """
    <summary>A snowy fir in tiers with a star on top; the lights are separate glows.</summary>
    <param name="draw">ImageDraw on a supersampled canvas.</param>
    <param name="x0">Trunk centre, supersampled pixels.</param>
    <param name="base">Foot of the trunk.</param>
    <param name="height">Height to the top.</param>
    <param name="rng">Random source for the snow lumps.</param>
    """
    green = (16, 62, 34, 255)
    dark = (10, 42, 24, 255)
    snow = (226, 234, 246, 255)
    draw.rectangle([x0 - 14 * SS, base - 30 * SS, x0 + 14 * SS, base], fill=(58, 34, 20, 255))
    top = base - height
    tiers = 5
    for t in range(tiers):
        ty = top + t * height * 0.16
        half = (40 + t * 30) * SS
        by = ty + height * 0.30
        draw.polygon([(x0, ty), (x0 + half, by), (x0 - half, by)], fill=dark if t % 2 else green)
        for k in range(5):
            sx = x0 - half * 0.8 + k * half * 0.4 + rng.uniform(-4, 4) * SS
            sy = by - (abs(sx - x0) / half) * 6 * SS - 4 * SS
            draw.ellipse([sx - 10 * SS, sy - 4 * SS, sx + 10 * SS, sy + 4 * SS], fill=snow)
    star = []
    for i in range(10):
        r = (18 if i % 2 == 0 else 8) * SS
        a = math.radians(-90 + i * 36)
        star.append((x0 + r * math.cos(a), top - 6 * SS + r * math.sin(a)))
    draw.polygon(star, fill=(255, 214, 90, 255))


def office_tower(draw, x, base, w, h, rng):
    """
    <summary>A lone glass office tower far off on the horizon, a quiet nod to Die Hard.</summary>
    <param name="draw">ImageDraw on the full size scene.</param>
    <param name="x">Left edge.</param>
    <param name="base">Where it meets the far hills.</param>
    <param name="w">Width.</param>
    <param name="h">Height.</param>
    <param name="rng">Random source for the lit windows.</param>
    <remarks>Asked for on 12/10/2026 as a subtle reference. Ordinary office
    lights on most floors, one floor near the top having its Christmas
    party in coloured lights, and two windows on it glowing orange as if
    something has just gone off. No name, no lettering.</remarks>
    """
    top = base - h
    draw.rectangle([x, top, x + w, base], fill=(22, 26, 44))
    draw.rectangle([x + w * 0.3, top - 16, x + w * 0.7, top], fill=(22, 26, 44))
    draw.line([(x + w / 2, top - 16), (x + w / 2, top - 40)], fill=(22, 26, 44), width=2)
    draw.ellipse([x + w / 2 - 2, top - 43, x + w / 2 + 2, top - 39], fill=(220, 40, 40))
    floors = int(h / 9)
    party = 4
    for f in range(floors):
        fy = top + 6 + f * 9
        for c in range(int(w / 7)):
            wx = x + 3 + c * 7
            if f == party:
                colour = ((230, 60, 60), (60, 200, 90), (250, 210, 80), (90, 140, 255))[c % 4]
                if c in (2, 3):
                    colour = (255, 140, 30)
                draw.rectangle([wx, fy, wx + 3, fy + 4], fill=colour)
            elif rng.random() < 0.28:
                draw.rectangle([wx, fy, wx + 3, fy + 4], fill=(150, 160, 120))
    return (x + 3 + 2.5 * 7, top + 6 + party * 9 + 2)


def window_boy(draw, x, y, w, h):
    """
    <summary>A lit window with a small boy inside, hands pressed to his cheeks, a quiet nod to Home Alone.</summary>
    <param name="draw">ImageDraw on a supersampled canvas.</param>
    <param name="x">Left of the window.</param>
    <param name="y">Top of the window.</param>
    <param name="w">Width.</param>
    <param name="h">Height.</param>
    <remarks>Asked for on 12/10/2026 as a subtle reference: just the pose,
    in silhouette against the light, nothing written.</remarks>
    """
    draw.rectangle([x, y, x + w, y + h], fill=(255, 200, 100, 255))
    ink = (40, 26, 22, 255)
    cx = x + w / 2
    hr = w * 0.17
    hy = y + h * 0.36
    draw.ellipse([cx - hr, hy - hr, cx + hr, hy + hr], fill=ink)                       # head
    draw.rectangle([cx - w * 0.2, hy + hr * 0.8, cx + w * 0.2, y + h], fill=ink)        # shoulders down
    for side in (-1, 1):
        ex = cx + side * w * 0.34
        draw.line([(cx + side * w * 0.2, hy + hr * 1.6), (ex, hy + hr * 1.2), (cx + side * hr * 0.95, hy + hr * 0.1)],
                  fill=ink, width=max(2, int(w * 0.09)))
        draw.ellipse([cx + side * hr * 0.95 - w * 0.07, hy - w * 0.04, cx + side * hr * 0.95 + w * 0.07, hy + w * 0.12],
                     fill=ink)                                                           # hands on the cheeks
    draw.line([(cx, y), (cx, y + h)], fill=(40, 30, 34, 255), width=max(1, int(w * 0.04)))
    draw.line([(x, y + h * 0.5), (x + w, y + h * 0.5)], fill=(40, 30, 34, 120), width=max(1, int(w * 0.03)))


def christmas_scene():
    """
    <summary>The Christmas village at night: stars, a moon, snowy hills, houses, a church, the tree and a fence.</summary>
    <remarks>Kept in the open band below the menu row, like the
    cemetery. The long house at XMAS_RIDGE is where the sleigh lands on
    Christmas Eve, the tree at XMAS_TREE carries the twinkling lights and
    the robin sits on the fence post at XMAS_ROBIN.</remarks>
    """
    rng = random.Random(2512)
    img = vertical_gradient((6, 10, 30), (36, 52, 92))
    sky = ImageDraw.Draw(img)
    for _ in range(260):
        x, y = rng.uniform(0, W), rng.uniform(0, 640)
        b = rng.randint(120, 255)
        r = rng.choice((0.6, 0.8, 1.2))
        sky.ellipse([x - r, y - r, x + r, y + r], fill=(b, b, min(255, b + 20)))
    clouds(img, (70, 84, 120), 0.35, 81, 0, 600, 160)
    moon(img, XMAS_MOON, 62, (238, 236, 224), 82)
    # far on the left horizon, behind the hills
    party = office_tower(ImageDraw.Draw(img), 96, 820, 62, 330, rng)
    paste_glow(img, 40, (int(party[0]), int(party[1])), (255, 140, 30), 0.5, 2.0)

    hills = Image.new("L", (W * SS, H * SS), 0)
    hd = ImageDraw.Draw(hills)
    far = [(x, (800 - 40 * math.sin(x / SS / 300 + 1.2) - 30 * math.sin(x / SS / 130)) * SS) for x in range(0, W * SS + 1, 8)]
    hd.polygon(far + [(W * SS, H * SS), (0, H * SS)], fill=255)
    img.paste(Image.new("RGB", (W, H), (120, 136, 176)), (0, 0), hills.resize((W, H), Image.LANCZOS))

    art = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    ad = ImageDraw.Draw(art)
    wall = (40, 30, 34, 255)
    snow = (232, 238, 248, 255)
    window = (255, 196, 92, 255)
    # church with a spire, behind
    cx, cb = 880 * SS, 870 * SS
    ad.rectangle([cx - 60 * SS, cb - 150 * SS, cx + 60 * SS, cb], fill=(34, 28, 36, 255))
    ad.polygon([(cx - 70 * SS, cb - 150 * SS), (cx, cb - 210 * SS), (cx + 70 * SS, cb - 150 * SS)], fill=(34, 28, 36, 255))
    ad.rectangle([cx - 22 * SS, cb - 290 * SS, cx + 22 * SS, cb - 150 * SS], fill=(34, 28, 36, 255))
    ad.polygon([(cx - 26 * SS, cb - 290 * SS), (cx, cb - 360 * SS), (cx + 26 * SS, cb - 290 * SS)], fill=(34, 28, 36, 255))
    ad.ellipse([cx - 12 * SS, cb - 260 * SS, cx + 12 * SS, cb - 236 * SS], fill=window)
    for wx in (-36, 24):
        ad.rounded_rectangle([cx + wx * SS, cb - 120 * SS, cx + (wx + 14) * SS, cb - 76 * SS], 6 * SS, fill=window)
    # houses, the long one in the middle with the flat ridge and chimney
    snowy_roof_house(ad, 600 * SS, 890 * SS, 150 * SS, 110 * SS, 70 * SS, wall, snow, window, rng)
    window_boy(ad, 704 * SS, 796 * SS, 34 * SS, 42 * SS)
    ridge_w = 130
    rx, ry = XMAS_RIDGE
    snowy_roof_house(ad, (rx - 115) * SS, 900 * SS, 230 * SS, 150 * SS, (ry and (900 - 150 - ry)) * SS, wall, snow, window, rng,
                     chimney=True, ridge=ridge_w * SS)
    snowy_roof_house(ad, 1300 * SS, 905 * SS, 130 * SS, 100 * SS, 60 * SS, wall, snow, window, rng)
    snowy_roof_house(ad, 1660 * SS, 895 * SS, 170 * SS, 120 * SS, 70 * SS, wall, snow, window, rng, chimney=True)
    x0, base, height = XMAS_TREE
    christmas_tree(ad, x0 * SS, base * SS, height * SS, rng)
    # a wooden fence along the front with snow on the rails
    fx0, fx1, fy = 1360, 1560, XMAS_ROBIN[1]
    for x in range(fx0, fx1 + 1, 40):
        ad.rectangle([x * SS, fy * SS, (x + 10) * SS, (fy + 70) * SS], fill=(70, 46, 30, 255))
        ad.ellipse([(x - 2) * SS, (fy - 5) * SS, (x + 12) * SS, (fy + 4) * SS], fill=snow)
    for ry_ in (fy + 18, fy + 46):
        ad.rectangle([fx0 * SS, ry_ * SS, (fx1 + 10) * SS, (ry_ + 7) * SS], fill=(70, 46, 30, 255))
        ad.rectangle([fx0 * SS, (ry_ - 3) * SS, (fx1 + 10) * SS, ry_ * SS], fill=snow)
    art = art.resize((W, H), Image.LANCZOS)
    img.paste(art, (0, 0), art)
    # window glow
    for x, y in ((675, 840), (1140, 820), (1365, 860), (1745, 840)):
        paste_glow(img, 160, (x, y), (255, 170, 70), 0.25, 2.0)

    # deep snow in front, gently rolling, with a blue shadow along its top
    front = Image.new("L", (W * SS, H * SS), 0)
    fd = ImageDraw.Draw(front)
    pts = [(x, (930 + 14 * math.sin(x / SS / 210 + 0.4) + 8 * math.sin(x / SS / 70)) * SS) for x in range(0, W * SS + 1, 8)]
    fd.polygon(pts + [(W * SS, H * SS), (0, H * SS)], fill=255)
    front = front.resize((W, H), Image.LANCZOS)
    # moonlit, not daylight white: Home's version line and corner bar
    # sit on this snow in light grey and must still read
    shade = vertical_gradient((104, 118, 156), (70, 80, 112))
    img.paste(shade, (0, 0), front)
    arr = np.asarray(img, np.float32) * vignette_array(0.55)[..., None]
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    img.save(OUT / "christmas_scene.jpg", "JPEG", quality=88, optimize=True, progressive=True)


def reindeer(draw, x, y, s, phase, colour, nose=None):
    """
    <summary>One reindeer facing left, galloping or standing.</summary>
    <param name="draw">ImageDraw on a supersampled canvas.</param>
    <param name="x">Body centre x.</param>
    <param name="y">Body centre y.</param>
    <param name="s">Pixels per unit; the body is about 40 units long.</param>
    <param name="phase">Gallop phase in radians, or None to stand.</param>
    <param name="colour">Silhouette colour.</param>
    <param name="nose">RGB for a glowing nose, or None.</param>
    """
    def P(u, v):
        return (x + u * s, y + v * s)

    d = draw
    d.ellipse([P(-20, -8), P(20, 8)], fill=colour)
    d.polygon([P(-16, -4), P(-26, -20), P(-20, -22), P(-10, -6)], fill=colour)        # neck
    d.ellipse([P(-34, -26), P(-20, -16)], fill=colour)                                 # head
    d.polygon([P(-32, -22), P(-40, -19), P(-32, -17)], fill=colour)                    # muzzle
    for ax, lean in ((-26, -1), (-22, 1)):                                             # antlers
        tip = P(ax + lean * 6, -38)
        d.line([P(ax, -25), tip], fill=colour, width=max(1, int(1.6 * s)))
        d.line([P(ax + lean * 2, -31), P(ax + lean * 2 - 5, -34)], fill=colour, width=max(1, int(1.2 * s)))
        d.line([P(ax + lean * 4, -35), P(ax + lean * 4 + 4, -39)], fill=colour, width=max(1, int(1.2 * s)))
    d.polygon([P(18, -5), P(25, -9), P(22, -2)], fill=colour)                          # tail
    for i, hx in enumerate((-14, -9, 11, 16)):
        if phase is None:
            dx = 0
        else:
            front = i < 2
            dx = 9 * math.sin(phase + (0 if front else math.pi) + i * 0.4)
        d.line([P(hx, 5), P(hx + dx, 22)], fill=colour, width=max(1, int(2.2 * s)))
    if nose:
        d.ellipse([P(-43, -21), P(-38, -16)], fill=nose)


def sleigh_frame(phase, parked=False):
    """
    <summary>Santa's sleigh and four reindeer facing left, as a silhouette.</summary>
    <param name="phase">Gallop phase in radians.</param>
    <param name="parked">Standing reindeer and an empty sleigh with a sack,
    for the rooftop; Santa is down the chimney.</param>
    <returns>RGBA, 520 by 150 flying, 240 by 80 parked.</returns>
    """
    w, h = 520, 150
    img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ink = (12, 14, 30, 255)
    s = 1.6 * SS
    base_y = 80 * SS
    for k in range(4):
        rx = (70 + k * 78) * SS
        bob = 0 if parked else 4 * SS * math.sin(phase + k * 0.9)
        reindeer(d, rx, base_y + bob, s, None if parked else phase + k * 0.9, ink,
                 nose=(235, 30, 30, 255) if k == 0 else None)
    # reins from the team to the sleigh
    d.line([(70 * SS, base_y - 4 * SS), (395 * SS, base_y + 6 * SS)], fill=ink, width=SS)
    # the sleigh: a curled front, a box and a runner
    sx = 380 * SS
    d.polygon([(sx, 70 * SS), (sx + 20 * SS, 52 * SS), (sx + 26 * SS, 60 * SS), (sx + 16 * SS, 74 * SS),
               (sx + 110 * SS, 74 * SS), (sx + 118 * SS, 40 * SS), (sx + 130 * SS, 40 * SS), (sx + 124 * SS, 104 * SS),
               (sx + 14 * SS, 104 * SS)], fill=ink)
    d.line([(sx - 4 * SS, 118 * SS), (sx + 132 * SS, 118 * SS)], fill=ink, width=3 * SS)
    d.arc([(sx - 22 * SS, 100 * SS), (sx + 6 * SS, 128 * SS)], 90, 270, fill=ink, width=3 * SS)
    for px in (sx + 20 * SS, sx + 104 * SS):
        d.line([(px, 104 * SS), (px, 118 * SS)], fill=ink, width=2 * SS)
    # the sack
    d.ellipse([sx + 66 * SS, 34 * SS, sx + 118 * SS, 78 * SS], fill=ink)
    d.polygon([(sx + 86 * SS, 38 * SS), (sx + 92 * SS, 24 * SS), (sx + 100 * SS, 38 * SS)], fill=ink)
    if not parked:
        # Santa: body, arm out with the reins, bobble hat
        d.ellipse([sx + 30 * SS, 34 * SS, sx + 74 * SS, 82 * SS], fill=ink)
        d.ellipse([sx + 34 * SS, 14 * SS, sx + 56 * SS, 38 * SS], fill=ink)
        d.polygon([(sx + 34 * SS, 22 * SS), (sx + 50 * SS, 4 * SS), (sx + 66 * SS, 12 * SS), (sx + 56 * SS, 22 * SS)], fill=ink)
        d.ellipse([sx + 62 * SS, 6 * SS, sx + 72 * SS, 16 * SS], fill=ink)
        d.line([(sx + 36 * SS, 50 * SS), (sx + 10 * SS, 64 * SS)], fill=ink, width=4 * SS)
    out = img.resize((w, h), Image.LANCZOS)
    if not parked:
        # A faint moonlit halo, so the dark team still shows against the
        # dark sky away from the moon.
        halo_a = out.getchannel("A").filter(ImageFilter.GaussianBlur(5)).point(lambda v: int(v * 0.45))
        halo = Image.new("RGBA", (w, h), (200, 214, 245, 0))
        halo.putalpha(halo_a)
        halo.alpha_composite(out)
        out = halo
    if parked:
        out = out.resize((240, 70), Image.LANCZOS)
        canvas = Image.new("RGBA", (240, 80), (0, 0, 0, 0))
        canvas.paste(out, (0, 10), out)
        return canvas
    return out


def sleighs():
    """
    <summary>Four gallop frames of the sleigh both ways, and the parked sleigh.</summary>
    <remarks>sleigh_rtl/ flies right to left, sleigh_ltr/ is the same
    frames mirrored. sleigh_parked.png is 240 by 80 with the runners on
    its bottom edge, set on XMAS_RIDGE by ChristmasLayers.</remarks>
    """
    for i in range(4):
        f = sleigh_frame(i * math.pi / 2)
        save_png(f, OUT / "sleigh_rtl" / "{0:02d}.png".format(i))
        save_png(f.transpose(Image.FLIP_LEFT_RIGHT), OUT / "sleigh_ltr" / "{0:02d}.png".format(i))
    save_png(sleigh_frame(0, parked=True), OUT / "sleigh_parked.png")


def robin_frame(tilt):
    """
    <summary>A robin perched facing left, 64 square, feet at the bottom centre.</summary>
    <param name="tilt">Head tilt and tail flick, 0 or 1.</param>
    <returns>The image.</returns>
    """
    s = SS
    img = Image.new("RGBA", (64 * s, 64 * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    brown = (110, 78, 50, 255)
    breast = (222, 92, 40, 255)

    def P(x, y):
        return (x * s, y * s)

    d.polygon([P(40, 40), P(60, 30 - 6 * tilt), P(62, 36 - 6 * tilt), P(44, 46)], fill=brown)       # tail
    d.ellipse([P(14, 24), P(48, 56)], fill=brown)                                                   # body
    d.ellipse([P(16, 32), P(36, 56)], fill=(236, 228, 214, 255))                                    # belly
    d.ellipse([P(13, 26), P(33, 48)], fill=breast)                                                  # breast
    hy = 18 - 2 * tilt
    d.ellipse([P(12, hy), P(32, hy + 18)], fill=brown)                                              # head
    d.ellipse([P(13, hy + 7), P(25, hy + 18)], fill=breast)                                         # face
    d.polygon([P(13, hy + 8 + tilt), P(4, hy + 10 + 2 * tilt), P(13, hy + 11 + tilt)], fill=(40, 30, 24, 255))
    d.ellipse([P(18, hy + 5), P(22, hy + 9)], fill=(10, 8, 8, 255))
    for lx in (28, 34):
        d.line([P(lx, 54), P(lx, 63)], fill=(60, 40, 30, 255), width=s)
    return img.resize((64, 64), Image.LANCZOS)


def robins():
    """
    <summary>Two frames of the robin, still and with its head cocked, played slowly by Kodi.</summary>
    """
    save_png(robin_frame(0), OUT / "robin" / "00.png")
    save_png(robin_frame(1), OUT / "robin" / "01.png")


def snow(name, count, rmin, rmax, alpha, seed):
    """
    <summary>A 960 by 540 snowfall tile that wraps top to bottom, scaled up 2x by Kodi.</summary>
    <param name="name">Output file name.</param>
    <param name="count">Number of flakes.</param>
    <param name="rmin">Smallest flake radius in tile pixels.</param>
    <param name="rmax">Largest flake radius.</param>
    <param name="alpha">Peak flake opacity.</param>
    <param name="seed">Seed.</param>
    """
    tw, th = 960, 540
    rng = random.Random(seed)
    img = Image.new("RGBA", (tw * SS, th * SS), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    for _ in range(count):
        x, y = rng.uniform(0, tw) * SS, rng.uniform(0, th) * SS
        r = rng.uniform(rmin, rmax) * SS
        a = rng.randint(alpha // 2, alpha)
        for oy in (0, -th * SS, th * SS):
            d.ellipse([x - r, y + oy - r, x + r, y + oy + r], fill=(255, 255, 255, a))
    img = img.resize((tw, th), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.6))
    save_png(img, OUT / name)


def frost():
    """
    <summary>Frost creeping in from the corners, 960 by 540, stretched to the screen by Kodi.</summary>
    <remarks>Branching ice needles grown out of each corner over a soft
    white haze, transparent in the middle.</remarks>
    """
    tw, th = 960, 540
    rng = random.Random(1201)
    img = Image.new("RGBA", (tw * SS, th * SS), (230, 240, 255, 0))
    d = ImageDraw.Draw(img)

    def needle(x, y, ang, length, depth):
        if depth == 0 or length < 3 * SS:
            return
        x2 = x + math.cos(ang) * length
        y2 = y + math.sin(ang) * length
        d.line([(x, y), (x2, y2)], fill=(235, 244, 255, 90 + 15 * depth), width=max(1, depth * SS // 2))
        for side in (-1, 1):
            if rng.random() < 0.8:
                t = rng.uniform(0.3, 0.8)
                needle(x + (x2 - x) * t, y + (y2 - y) * t, ang + side * math.radians(rng.uniform(45, 65)),
                       length * rng.uniform(0.35, 0.55), depth - 1)
        needle(x2, y2, ang + math.radians(rng.uniform(-15, 15)), length * 0.7, depth - 1)

    corners = ((0, 0, 0.25 * math.pi), (tw, 0, 0.75 * math.pi), (0, th, -0.25 * math.pi), (tw, th, -0.75 * math.pi))
    for cx, cy, ang in corners:
        for _ in range(9):
            needle(cx * SS, cy * SS, ang + math.radians(rng.uniform(-40, 40)), rng.uniform(22, 48) * SS, 4)
    img = img.resize((tw, th), Image.LANCZOS)
    y, x = np.mgrid[0:th, 0:tw]
    r = np.hypot((x - tw / 2) / (tw / 2), (y - th / 2) / (th / 2)) / math.sqrt(2)
    haze = np.clip((r - 0.55) / 0.45, 0, 1) ** 2 * 120
    a = np.maximum(np.asarray(img.getchannel("A"), np.float32), haze)
    img.putalpha(Image.fromarray(a.astype(np.uint8)))
    save_png(img, OUT / "frost.png")


def light_glow():
    """
    <summary>A white point of light with a soft halo, coloured by Kodi for each tree light.</summary>
    """
    g = radial_glow(48, (255, 255, 255), 2.6)
    save_png(g, OUT / "light_glow.png")


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
    # Drawn last so the seeded pictures above come out exactly as before.
    spiders()
    witches()
    ghosts()
    christmas_scene()
    sleighs()
    robins()
    snow("snow_far.png", 700, 0.8, 1.6, 170, 91)
    snow("snow_near.png", 160, 1.8, 3.4, 230, 92)
    frost()
    light_glow()
    if "--lights" in sys.argv:
        for light in xmas_tree_lights():
            print(light)
    for path in sorted(OUT.rglob("*")):
        if path.is_file():
            print("{0:>9,}  {1}".format(path.stat().st_size, path.relative_to(OUT.parent.parent)))


if __name__ == "__main__":
    main()
