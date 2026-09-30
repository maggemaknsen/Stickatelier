"""Deterministic raster preparation. Physical thresholds refer to the whole canvas."""
from io import BytesIO
import math
import re
import warnings
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

Image.MAX_IMAGE_PIXELS = 24_000_000
warnings.simplefilter('error', Image.DecompressionBombWarning)
DEFAULTS = dict(colors=6, width_mm=100, long_side_mm=None, smooth=0, contrast=100,
                detail_mm=0, darken_mm=0, remove_bg=False,
                background='#ffffff', tolerance=20, palette_edit=None)
LIMITS = dict(colors=(1, 24), width_mm=(10, 260), smooth=(0, 3),
              contrast=(50, 180), detail_mm=(0, 2), darken_mm=(0, 0.8), tolerance=(0, 120))

def settings(raw):
    if not isinstance(raw, dict):
        raise ValueError('Einstellungen müssen ein Objekt sein.')
    out = DEFAULTS.copy()
    if raw.get('long_side_mm') is not None:
        val = float(raw['long_side_mm'])
        if not math.isfinite(val) or not 10 <= val <= 260:
            raise ValueError('Ungültiger Wert für long_side_mm.')
        out['long_side_mm'] = val
    for key, (lo, hi) in LIMITS.items():
        val = float(raw.get(key, out[key]))
        # A narrow portrait can have an actual width below 10 mm. Legacy
        # width-only requests retain their original 10–260 mm validation.
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
    return out

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

def quantize(rgb, alpha, count):
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
            if np.max(np.abs(updated-centers)) < 0.3:
                break
            centers = updated
        chosen = np.unique(np.clip(np.rint(updated),0,255).astype(np.uint8),axis=0)
    return assign_palette(rgb, alpha, chosen)

def assign_palette(rgb, alpha, chosen):
    """Use the same base colors for preview and export during manual editing."""
    ids = np.zeros(alpha.shape, dtype=np.uint8)
    flat = rgb.reshape(-1, 3)
    target = ids.ravel()
    for start in range(0, len(flat), 30_000):
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
    """Resolve the requested long side into the actual width of this raster."""
    if s['long_side_mm'] is not None:
        return s['long_side_mm'] if image.width >= image.height else s['long_side_mm'] * image.width / image.height
    return s['width_mm']

def prepare(original, raw, max_edge=1200):
    s = settings(raw)
    image = original.copy()
    image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    s['width_mm'] = physical_width(image, s)
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
        rgb, ids, pal = assign_palette(rgb, alpha, pal)
    else:
        rgb, ids, pal = quantize(rgb, alpha, s['colors'])
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
    rgba = np.dstack((rgb, alpha))
    rgba[alpha == 0, :3] = 0
    result = Image.fromarray(rgba)
    colors, counts = np.unique(rgb[alpha > 0], axis=0, return_counts=True)
    order = np.argsort(-counts)
    height_mm = (s['long_side_mm'] if image.height >= image.width else s['long_side_mm'] * image.height/image.width) if s['long_side_mm'] is not None else s['width_mm'] * image.height/image.width
    if not ((s['width_mm'] <= 260 and height_mm <= 160) or (s['width_mm'] <= 160 and height_mm <= 260)):
        notices.append('Das Motiv überschreitet die maximale b70-deco-Fläche von 260 × 160 mm, auch gedreht.')
    notices.append('Grafikvorbereitung: Stichdichte, Unterlagen und Stichfolge anschließend in Creator 9 prüfen.')
    stats = dict(colors=len(colors), width_px=image.width, height_px=image.height,
                 width_mm=s['width_mm'], height_mm=round(height_mm,1),
                 long_side_mm=max(s['width_mm'], height_mm),
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
