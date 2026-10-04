"""Deterministic raster preparation. Physical thresholds refer to the whole canvas."""
from io import BytesIO
import math
import re
import warnings
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

Image.MAX_IMAGE_PIXELS = 24_000_000
warnings.simplefilter('error', Image.DecompressionBombWarning)
DEFAULTS = dict(colors=6, width_mm=100, long_side_mm=None, short_side_mm=None, smooth=0, contrast=100,
                detail_mm=0, darken_mm=0, remove_bg=False,
                background='#ffffff', tolerance=20, color_space='rgb', palette_edit=None, fill_edits=[])
LIMITS = dict(colors=(1, 24), width_mm=(10, 260), smooth=(0, 3),
              contrast=(50, 180), detail_mm=(0, 2), darken_mm=(0, 0.8), tolerance=(0, 120))

def settings(raw):
    if not isinstance(raw, dict):
        raise ValueError('Einstellungen müssen ein Objekt sein.')
    out = DEFAULTS.copy()
    color_space = raw.get('color_space', 'rgb')
    if color_space not in ('rgb', 'oklab'):
        raise ValueError('Ungültige Methode für die Farbreduktion.')
    out['color_space'] = color_space
    if raw.get('short_side_mm') is not None:
        val = float(raw['short_side_mm'])
        if not math.isfinite(val) or val < 10:
            raise ValueError('Die kurze Seite muss mindestens 10 mm betragen.')
        out['short_side_mm'] = val
    elif raw.get('long_side_mm') is not None:
        val = float(raw['long_side_mm'])
        if not math.isfinite(val) or not 10 <= val <= 260:
            raise ValueError('Ungültiger Wert für long_side_mm.')
        out['long_side_mm'] = val
    for key, (lo, hi) in LIMITS.items():
        val = float(raw.get(key, out[key]))
        # A narrow portrait can have an actual width below 10 mm. Legacy
        # width-only requests retain their original 10–260 mm validation.
        if key == 'width_mm' and out['short_side_mm'] is not None:
            valid = val > 0
        else:
            valid = 0 < val <= hi if key == 'width_mm' and out['long_side_mm'] is not None else lo <= val <= hi
        if not math.isfinite(val) or not valid:
            raise ValueError(f'Ungültiger Wert für {key}.')
        out[key] = int(val) if key in ('colors', 'smooth', 'contrast', 'tolerance') else val
    if not isinstance(raw.get('remove_bg', False), bool):
        raise ValueError('Ungültige Hintergrundoption.')
    out['remove_bg'] = raw.get('remove_bg', False)
    color = raw.get('background', '#ffffff')
    if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        raise ValueError('Ungültige Hintergrundfarbe.')
    out['background'] = color.lower()
    edit = raw.get('palette_edit')
    if edit is not None:
        if not isinstance(edit, dict) or set(edit) != {'base', 'map'}:
            raise ValueError('Ungültige Palettenänderung.')
        base, mapping = edit['base'], edit['map']
        def valid_hex(value):
            return isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value)
        if not isinstance(base, list) or not 1 <= len(base) <= out['colors'] or not all(valid_hex(c) for c in base):
            raise ValueError('Ungültige Basispalette oder Farbgrenze.')
        base = [c.lower() for c in base]
        if len(set(base)) != len(base) or not isinstance(mapping, dict) or len(mapping) > len(base):
            raise ValueError('Ungültige Farbzuordnung.')
        if not all(valid_hex(k) and k.lower() in base and valid_hex(v) for k, v in mapping.items()):
            raise ValueError('Ungültige Farbzuordnung.')
        normalized = {k.lower(): v.lower() for k, v in mapping.items()}
        if len(normalized) != len(mapping):
            raise ValueError('Doppelte Farbzuordnung.')
        out['palette_edit'] = dict(base=base, map=normalized)
    fills = raw.get('fill_edits', [])
    if not isinstance(fills, list) or len(fills) > 100:
        raise ValueError('Höchstens 100 Füllungen und Pinselstriche pro Motiv verwenden.')
    out['fill_edits'] = []
    brush_points = 0
    for fill in fills:
        if isinstance(fill, dict) and fill.get('type') == 'brush':
            if set(fill) != {'type', 'points', 'size', 'color'}:
                raise ValueError('Ungültiger Pinselstrich.')
            points, size, color = fill['points'], fill['size'], fill['color']
            if not isinstance(points, list) or not 1 <= len(points) <= 2000:
                raise ValueError('Ein Pinselstrich darf höchstens 2000 Punkte enthalten.')
            brush_points += len(points)
            if brush_points > 20_000:
                raise ValueError('Zu viele Pinselpunkte. Bitte einige Striche zurücknehmen.')
            for point in points:
                if not isinstance(point, list) or len(point) != 2 or not all(
                        isinstance(v, (int, float)) and not isinstance(v, bool)
                        and math.isfinite(v) and 0 <= v < 1 for v in point):
                    raise ValueError('Ungültige Pinselposition.')
            if not isinstance(size, (int, float)) or isinstance(size, bool) or not math.isfinite(size) or not 0.001 <= size <= 0.5:
                raise ValueError('Ungültige Pinselgröße.')
            if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
                raise ValueError('Ungültige Pinselfarbe.')
            out['fill_edits'].append(dict(type='brush', points=[list(p) for p in points], size=size, color=color.lower()))
            continue
        if not isinstance(fill, dict) or set(fill) != {'x', 'y', 'color'}:
            raise ValueError('Ungültige Füllung.')
        if not all(isinstance(fill[k], (int, float)) and not isinstance(fill[k], bool)
                   and math.isfinite(fill[k]) and 0 <= fill[k] < 1 for k in ('x', 'y')):
            raise ValueError('Ungültige Füllposition.')
        if not isinstance(fill['color'], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', fill['color']):
            raise ValueError('Ungültige Füllfarbe.')
        out['fill_edits'].append(dict(x=fill['x'], y=fill['y'], color=fill['color'].lower()))
    return out

def fill_region(rgb, alpha, fill):
    """Fill one four-connected exact-color region, including transparent holes."""
    h, w = alpha.shape
    x, y = min(w-1, int(fill['x']*w)), min(h-1, int(fill['y']*h))
    color = np.array([int(fill['color'][i:i+2], 16) for i in (1,3,5)], dtype=np.uint8)
    if alpha[y,x] > 0 and np.array_equal(rgb[y,x], color):
        return
    candidate = (alpha == 0) if alpha[y,x] == 0 else ((alpha > 0) & np.all(rgb == rgb[y,x].copy(), axis=2))
    # Scanline flood fill avoids a Python object per pixel and recursion limits.
    pending = [(x,y)]
    while pending:
        x, y = pending.pop()
        if not candidate[y,x]:
            continue
        left, right = x, x
        while left > 0 and candidate[y,left-1]:
            left -= 1
        while right+1 < w and candidate[y,right+1]:
            right += 1
        candidate[y,left:right+1] = False
        rgb[y,left:right+1] = color
        alpha[y,left:right+1] = 255
        for row in (y-1,y+1):
            if 0 <= row < h:
                line = candidate[row,left:right+1]
                starts = np.flatnonzero(line & ~np.r_[False,line[:-1]])
                pending.extend((left+int(start),row) for start in starts)


def paint_stroke(rgb, alpha, stroke):
    """Draw a hard-edged round brush over visible pixels, preserving transparency."""
    h, w = alpha.shape
    diameter = max(1, round(stroke['size'] * min(w, h)))
    points = [(min(w-1, int(x*w)), min(h-1, int(y*h))) for x, y in stroke['points']]
    mask = Image.new('L', (w, h))
    draw = ImageDraw.Draw(mask)
    if len(points) > 1:
        draw.line(points, fill=255, width=diameter, joint='curve')
    radius = (diameter-1) / 2
    for x, y in points:
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=255)
    selected = (np.asarray(mask) > 0) & (alpha > 0)
    rgb[selected] = [int(stroke['color'][i:i+2], 16) for i in (1,3,5)]

def decode(data):
    try:
        with Image.open(BytesIO(data), formats=['PNG', 'JPEG', 'WEBP', 'BMP']) as im:
            im.load()
            if min(im.size) < 2:
                raise ValueError('Das Bild ist zu klein.')
            # Strip metadata and EXIF after applying orientation.
            clean = ImageOps.exif_transpose(im).convert('RGBA')
            clean.info.clear()
            return clean
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('Das Bild darf höchstens 24 Millionen Pixel enthalten.')
    except (OSError, SyntaxError):
        raise ValueError('Bitte eine gültige PNG-, JPG-, WEBP- oder BMP-Datei verwenden.')

def components(mask):
    """4-connected run-length union-find, without a native CV dependency."""
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    parent = [0]
    def root(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n
    prev = []
    for y in range(h):
        edges = np.flatnonzero(np.diff(np.pad(mask[y].astype(np.int8), (1, 1))))
        current, j = [], 0
        for a, b in zip(edges[::2], edges[1::2]):
            n = len(parent)
            parent.append(n)
            while j < len(prev) and prev[j][1] <= a:
                j += 1
            k = j
            while k < len(prev) and prev[k][0] < b:
                rn, rp = root(n), root(prev[k][2])
                if rn != rp:
                    parent[rn] = rp
                k += 1
            labels[y, a:b] = n
            current.append((a, b, n))
        prev = current
    lookup = np.array([root(i) for i in range(len(parent))], dtype=np.int32)
    return lookup[labels]

def rgb_to_oklab(rgb):
    """sRGB bytes to perceptual coordinates, using Björn Ottosson's matrices.

    Source: https://bottosson.github.io/posts/oklab/ (public domain / MIT).
    """
    srgb = np.asarray(rgb, dtype=np.float64) / 255
    linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    lms = linear @ np.array([[0.4122214708, 0.2119034982, 0.0883024619],
                             [0.5363325363, 0.6806995451, 0.2817188376],
                             [0.0514459929, 0.1073969566, 0.6299787005]])
    return np.cbrt(lms) @ np.array([[0.2104542553, 1.9779984951, 0.0259040371],
                                   [0.7936177850, -2.4285922050, 0.7827717662],
                                   [-0.0040720468, 0.4505937099, -0.8086757660]])


def oklab_to_rgb(lab):
    """Convert palette centers back to displayable sRGB bytes."""
    lms = (np.asarray(lab) @ np.array([[1, 1, 1],
                                     [0.3963377774, -0.1055613458, -0.0894841775],
                                     [0.2158037573, -0.0638541728, -1.2914855480]])) ** 3
    linear = np.clip(lms @ np.array([[4.0767416621, -1.2684380046, -0.0041960863],
                                    [-3.3077115913, 2.6097574011, -0.7034186147],
                                    [0.2309699292, -0.3413193965, 1.7076147010]]), 0, 1)
    srgb = np.where(linear <= 0.0031308, 12.92 * linear, 1.055 * linear ** (1 / 2.4) - 0.055)
    return np.clip(np.rint(srgb * 255), 0, 255).astype(np.uint8)


def quantize(rgb, alpha, count, color_space='rgb'):
    visible = rgb[alpha > 0]
    if not len(visible):
        raise ValueError('Keine sichtbaren Flächen übrig. Hintergrundtoleranz oder Detailfilter reduzieren.')
    # Learn the palette from visible pixels only; hidden backgrounds use no color slot.
    # A logo that already fits the color cap must keep even a one-pixel color.
    # Scan packed colors in bounded chunks. Photos exit as soon as cap+1 colors
    # are seen; simple logos are scanned completely before using a sample.
    exact_colors = set()
    for start in range(0, len(visible), 32_768):
        chunk = visible[start:start+32_768].astype(np.uint32)
        packed = (chunk[:,0] << 16) | (chunk[:,1] << 8) | chunk[:,2]
        exact_colors.update(np.unique(packed).tolist())
        if len(exact_colors) > count:
            break
    samples = visible[::max(1, len(visible) // 80_000)]
    unique = np.unique(samples, axis=0)
    if len(exact_colors) <= count:
        chosen = np.array([[(color >> 16) & 255, (color >> 8) & 255, color & 255]
                           for color in sorted(exact_colors)], dtype=np.uint8)
    elif len(unique) <= count:
        chosen = unique
    else:
        # Weighted 5-bit histogram avoids spending multiple slots on tiny JPEG
        # variations of one dominant color. Initialization is deterministic.
        bins, inverse, weights = np.unique(samples >> 3, axis=0, return_inverse=True, return_counts=True)
        points = np.column_stack([np.bincount(inverse, weights=samples[:,i])/weights for i in range(3)])
        if color_space == 'oklab':
            points = rgb_to_oklab(points)
        centers = [points[weights.argmax()]]
        distance = np.full(len(points), np.inf)
        for _ in range(1,min(count,len(points))):
            distance = np.minimum(distance, ((points-centers[-1])**2).sum(axis=1))
            centers.append(points[(distance*np.sqrt(weights)).argmax()])
        centers = np.array(centers)
        for _ in range(12):
            assigned = ((points[:,None,:]-centers[None,:,:])**2).sum(axis=2).argmin(axis=1)
            updated = centers.copy()
            for i in range(len(centers)):
                sel = assigned == i
                if sel.any():
                    updated[i] = np.average(points[sel],axis=0,weights=weights[sel])
            if np.max(np.abs(updated-centers)) < (0.001 if color_space == 'oklab' else 0.3):
                break
            centers = updated
        chosen = np.unique(oklab_to_rgb(updated) if color_space == 'oklab'
                           else np.clip(np.rint(updated),0,255).astype(np.uint8),axis=0)
    return assign_palette(rgb, alpha, chosen, color_space)

def assign_palette(rgb, alpha, chosen, color_space='rgb'):
    """Use the same base colors for preview and export during manual editing."""
    ids = np.zeros(alpha.shape, dtype=np.uint8)
    flat = rgb.reshape(-1, 3)
    target = ids.ravel()
    palette_points = rgb_to_oklab(chosen) if color_space == 'oklab' else chosen
    for start in range(0, len(flat), 30_000):
        if color_space == 'oklab':
            diff = rgb_to_oklab(flat[start:start+30_000])[:,None,:] - palette_points[None,:,:]
        else:
            diff = flat[start:start+30_000, None, :].astype(np.int32) - chosen[None, :, :].astype(np.int32)
        target[start:start+30_000] = (diff * diff).sum(axis=2).argmin(axis=1)
    return chosen[ids], ids, chosen

def clean_islands(ids, alpha, palette, threshold):
    """Merge tiny color islands into their most common immediate neighbor."""
    codes = ids.astype(np.int16)
    codes[alpha == 0] = -1
    source = codes.copy()
    count = 0
    for c in range(len(palette)):
        lab = components(source == c)
        sizes = np.bincount(lab.ravel())
        small = np.flatnonzero((sizes > 0) & (sizes < threshold))
        small = small[small != 0]
        if len(small) > 5000:
            raise ValueError('Zu viele Kleinstflächen. Zuerst die Glättung erhöhen oder weniger Farben wählen.')
        # Collect all component boundary pairs once per color.
        pairs = []
        for a, b, ca, cb in ((lab[:, :-1], lab[:, 1:], source[:, :-1], source[:, 1:]),
                               (lab[:-1], lab[1:], source[:-1], source[1:])):
            for la, lb, sa, sb in ((a,b,ca,cb),(b,a,cb,ca)):
                edge = (la > 0) & (lb == 0)
                if edge.any():
                    pairs.append(la[edge].astype(np.int64) * (len(palette)+1) + sb[edge] + 1)
        if not pairs:
            continue
        keys, freq = np.unique(np.concatenate(pairs), return_counts=True)
        mapping = np.full(len(sizes), c, dtype=np.int16)
        for n in small:
            lo, hi = np.searchsorted(keys, [n * (len(palette)+1), (n+1) * (len(palette)+1)])
            if hi > lo:
                neighbor = keys[lo:hi][freq[lo:hi].argmax()] % (len(palette)+1) - 1
                mapping[n] = neighbor
                count += 1
        selected = np.isin(lab, small)
        codes[selected] = mapping[lab[selected]]
    result_alpha = np.where(codes < 0, 0, 255).astype(np.uint8)
    result = palette[np.maximum(codes, 0)]
    return result, result_alpha, count

def physical_width(image, s):
    """Resolve the selected side, retaining support for older sizing requests."""
    if s['short_side_mm'] is not None:
        return s['short_side_mm'] if image.width <= image.height else s['short_side_mm'] * image.width / image.height
    if s['long_side_mm'] is not None:
        return s['long_side_mm'] if image.width >= image.height else s['long_side_mm'] * image.width / image.height
    return s['width_mm']

def prepare(original, raw, max_edge=1200):
    s = settings(raw)
    image = original.copy()
    image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    s['width_mm'] = physical_width(image, s)
    if not math.isfinite(s['width_mm']):
        raise ValueError('Die Zielgröße ist zu groß.')
    arr = np.array(image)
    # Hard alpha is intentional: no semitransparent fringe colors for auto-digitizing.
    alpha = np.where(arr[:,:,3] >= 128, 255, 0).astype(np.uint8)
    rgb = arr[:,:,:3].copy()
    px_mm = image.width / s['width_mm']
    notices = []
    if s['remove_bg']:
        bg = np.array([int(s['background'][i:i+2], 16) for i in (1,3,5)])
        candidate = (np.max(np.abs(rgb.astype(np.int16) - bg), axis=2) <= s['tolerance']) & (alpha > 0)
        lab = components(candidate)
        border = np.unique(np.concatenate((lab[0], lab[-1], lab[:,0], lab[:,-1])))
        border = border[border != 0]
        alpha[np.isin(lab, border)] = 0
        notices.append('Hintergrund: Nur farblich passende, mit dem Bildrand verbundene Flächen entfernt. Innenräume bleiben erhalten.')
    # Prevent hidden RGB values from bleeding into neighboring visible pixels.
    rgb[alpha == 0] = 255
    im = Image.fromarray(rgb)
    if s['smooth']:
        radius = min(7,max(1,round(s['smooth'] * px_mm / 12)))
        im = im.filter(ImageFilter.MedianFilter(2*radius+1))
    if s['contrast'] != 100:
        im = ImageEnhance.Contrast(im).enhance(s['contrast']/100)
    rgb = np.array(im)
    if s['darken_mm']:
        radius = max(1, round(s['darken_mm'] * px_mm / 2))
        dark = (rgb.mean(axis=2) < 85) & (alpha > 0)
        if dark.any():
            expanded = np.array(Image.fromarray(dark.astype(np.uint8)*255).filter(ImageFilter.MaxFilter(2*radius+1))) > 0
            # Expand existing dark details only; don't invent outlines.
            darkest = rgb[dark][rgb[dark].mean(axis=1).argmin()]
            rgb[expanded] = darkest
            alpha[expanded] = 255
        notices.append('Dunkle Details wurden verbreitert. Schrift und Zwischenräume im Vergleich prüfen.')
    edit = s['palette_edit']
    if edit:
        pal = np.array([[int(c[i:i+2], 16) for i in (1,3,5)] for c in edit['base']], dtype=np.uint8)
        rgb, ids, pal = assign_palette(rgb, alpha, pal, s['color_space'])
    else:
        rgb, ids, pal = quantize(rgb, alpha, s['colors'], s['color_space'])
    if s['color_space'] == 'oklab':
        notices.append('OKLab-Farbreduktion aktiv. Farbunterschiede werden nach menschlicher Wahrnehmung angenähert; einzelne Motivbereiche werden nicht erkannt.')
    removed = 0
    if s['detail_mm']:
        area = max(1, (s['detail_mm'] * px_mm)**2)
        rgb, alpha, removed = clean_islands(ids, alpha, pal, area)
        notices.append(f'{removed} kleine Farbflächen bearbeitet. Der Regler betrifft Flächen, nicht Strichbreiten.')
    if not (alpha > 0).any():
        raise ValueError('Keine sichtbaren Flächen übrig. Detailfilter reduzieren.')
    if edit:
        # Compare with the unmodified base colors: A -> B and B -> C must
        # happen simultaneously, never accidentally cascade A all the way to C.
        source = rgb.astype(np.uint32)
        codes = (source[:,:,0] << 16) | (source[:,:,1] << 8) | source[:,:,2]
        rgb = rgb.copy()
        for origin, target in edit['map'].items():
            rgb[(codes == int(origin[1:], 16)) & (alpha > 0)] = [int(target[i:i+2], 16) for i in (1,3,5)]
        notices.append('Manuelle Farbzuordnung aktiv. Die Basispalette bleibt für Vorschau und Export fixiert.')
    for fill in s['fill_edits']:
        if fill.get('type') == 'brush':
            paint_stroke(rgb, alpha, fill)
        else:
            fill_region(rgb, alpha, fill)
    if s['fill_edits']:
        notices.append(f"{len(s['fill_edits'])} Füllungen und Pinselstriche angewendet. Grenzen und kleine Details prüfen.")
    rgba = np.dstack((rgb, alpha))
    rgba[alpha == 0, :3] = 0
    result = Image.fromarray(rgba)
    colors, counts = np.unique(rgb[alpha > 0], axis=0, return_counts=True)
    if s['fill_edits'] and len(colors) > s['colors']:
        notices.append(f"Zusätzliche Korrekturfarben: Das Motiv enthält jetzt {len(colors)} Farben. Die Farbreduktion bleibt bei {s['colors']} Basisfarben.")
    order = np.argsort(-counts)
    height_mm = (s['long_side_mm'] if image.height >= image.width else s['long_side_mm'] * image.height/image.width) if s['long_side_mm'] is not None else s['width_mm'] * image.height/image.width
    if not math.isfinite(height_mm):
        raise ValueError('Die Zielgröße ist zu groß.')
    frame_exceeded = min(s['width_mm'], height_mm) > 160+1e-9 or max(s['width_mm'], height_mm) > 260+1e-9
    if frame_exceeded:
        notices.append('Zu groß für den Stickrahmen (260 × 160 mm), auch gedreht. Vorschau und Export sind weiterhin möglich.')
    notices.append('Grafikvorbereitung: Stichdichte, Unterlagen und Stichfolge anschließend in Creator 9 prüfen.')
    stats = dict(colors=len(colors), width_px=image.width, height_px=image.height,
                 width_mm=s['width_mm'], height_mm=round(height_mm,1),
                 long_side_mm=max(s['width_mm'], height_mm),
                 short_side_mm=min(s['width_mm'], height_mm), frame_exceeded=frame_exceeded,
                 base_palette=['#'+''.join(f'{v:02x}' for v in color) for color in pal],
                 palette=[dict(hex='#'+''.join(f'{v:02x}' for v in colors[i]),
                               share=round(100*int(counts[i])/int(counts.sum()),1)) for i in order],
                 notices=notices, settings=s)
    return result, stats

def png(image, width_mm=None):
    b = BytesIO()
    kwargs = {}
    if width_mm:
        dpi = image.width / width_mm * 25.4
        kwargs['dpi'] = (dpi, dpi)
    image.save(b, format='PNG', **kwargs)
    return b.getvalue()

def demo():
    # Technical calibration sample, deliberately includes a gradient and tiny islands.
    im = Image.new('RGB', (900,650), 'white')
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((200,100,700,550), radius=70, fill='#173758')
    for x in range(270,630):
        t=(x-270)/360
        draw.line((x,190,x,405), fill=(int(10+50*t),int(140+50*t),int(185+40*t)))
    draw.ellipse((360,220,540,400), fill='#f6c644')
    draw.line((300,470,600,470), fill='white', width=9)
    for x,y in ((160,180),(750,300),(155,410),(760,500)):
        draw.ellipse((x,y,x+5,y+5),fill='#e87436')
    return im.convert('RGBA')
