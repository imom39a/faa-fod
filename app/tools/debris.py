"""Debris cut-outs and compositing.

Cut-outs come from (a) the FOD-A example images (MIT licence, FOD-UNOmaha/FOD-data: the manyEx.png
grid and the Picture*.png single examples) and (b) openly licensed Wikimedia Commons photographs of
single objects on a plain background (see manifest/objects.json; attribution is written to
ATTRIBUTION.md). cut_foda()/paste() are copies of prototypes/spike/make_dataset.py, and
cut_picture() of prototypes/dashboard/tools/build_assets.py, with numpy in place of pixel loops.
"""
import cv2
import numpy as np
from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageStat

# FOD-A manyEx.png grid (column and row pixel ranges)
COLS = [(8, 115), (127, 234), (246, 354), (365, 472), (485, 593), (604, 711), (722, 830), (842, 949)]
ROWS = [(33, 140), (150, 257), (267, 375)]


def _key_mask(cell: Image.Image, thr, ring=6, drop_red=False, chroma=None):
    """Mask of pixels that differ from the median border colour by more than thr (sum of abs RGB
    differences). chroma: also require max-min channel spread above this (coloured object on a
    neutral grey floor, e.g. the brass bolt)."""
    a = np.asarray(cell.convert("RGB")).astype(np.int16)
    edge = np.concatenate([a[:ring].reshape(-1, 3), a[-ring:].reshape(-1, 3), a[:, :ring].reshape(-1, 3), a[:, -ring:].reshape(-1, 3)])
    bg = np.median(edge, axis=0)
    d = np.abs(a - bg).sum(axis=2)
    m = d > thr
    if chroma:
        m &= (a.max(axis=2) - a.min(axis=2)) > chroma
    if drop_red:
        m &= ~((a[..., 0] > 170) & (a[..., 1] < 90) & (a[..., 2] < 90))
    mask = Image.fromarray((m * 255).astype(np.uint8))
    return mask, tuple(int(v) for v in bg)


def _finish(cell, mask, bg, open_px=3):
    if open_px > 1:
        mask = mask.filter(ImageFilter.MinFilter(open_px)).filter(ImageFilter.MaxFilter(open_px + 2))
    # keep only the largest connected blob: drops patches of background texture that passed the key
    n, lab, stats, _ = cv2.connectedComponentsWithStats((np.asarray(mask) > 127).astype(np.uint8), connectivity=8)
    if n > 2:
        keep = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        mask = Image.fromarray(((lab == keep) * 255).astype(np.uint8))
    bb = mask.getbbox()
    return cell.crop(bb), mask.crop(bb).filter(ImageFilter.GaussianBlur(0.8)), bg


def cut_foda(sheet: Image.Image, row, col, thr=60, sub=None, chroma=None, open_px=3):
    """sub = optional [fx0, fy0, fx1, fy1] fraction of the cell that holds the object."""
    (x0, x1), (y0, y1) = COLS[col], ROWS[row]
    cell = sheet.crop((x0 + 3, y0 + 3, x1 - 2, y1 - 2)).convert("RGB")
    if sub:
        w, h = cell.size
        cell = cell.crop((round(sub[0] * w), round(sub[1] * h), round(sub[2] * w), round(sub[3] * h)))
    mask, bg = _key_mask(cell, thr, ring=3 if sub else 6, chroma=chroma)
    return _finish(cell, mask, bg, open_px)


def red_box(im: Image.Image, which=0):
    """Bounding box of FOD-A's drawn red annotation rectangle, inset to exclude the red line."""
    a = np.asarray(im.convert("RGB")).astype(np.int16)
    ys, xs = np.nonzero((a[..., 0] > 180) & (a[..., 1] < 80) & (a[..., 2] < 80))
    return (int(xs.min()) + 5, int(ys.min()) + 5, int(xs.max()) - 4, int(ys.max()) - 4)


def cut_picture(full: Image.Image, thr=70, box=None):
    full = full.convert("RGB")
    cell = full.crop(tuple(box) if box else red_box(full))
    mask, bg = _key_mask(cell, thr, ring=8, drop_red=True)
    return _finish(cell, mask, bg)


def cut_plain(photo: Image.Image, box=None, thr=45, max_side=400):
    """Cut a single object photographed on a plain (near-uniform) background."""
    im = photo.convert("RGB")
    if box:
        im = im.crop(tuple(box))
    if max(im.size) > max_side:
        s = max_side / max(im.size)
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    mask, bg = _key_mask(im, thr, ring=4)
    # keep the largest connected component region (fills holes are left as-is)
    return _finish(im, mask, bg)


def paste(frame: Image.Image, obj: Image.Image, mask: Image.Image, cx: int, cy: int,
          long_px: int, angle: float, src_bg=None, min_gain=0.35):
    """Paste obj centred at (cx,cy) with its long edge = long_px: brightness matched to the local
    pavement, feathered mask, soft contact shadow. Returns (box, contrast): the box of the pasted
    object and the mean grey-level change inside it (how visible the paste is)."""
    before = frame.copy()
    obj = obj.rotate(angle, expand=True, resample=Image.BICUBIC)
    mask = mask.rotate(angle, expand=True, resample=Image.BICUBIC)
    bb = mask.point(lambda v: 255 if v > 40 else 0).getbbox()
    obj, mask = obj.crop(bb), mask.crop(bb)
    sc = long_px / max(obj.size)
    nw, nh = max(2, round(obj.width * sc)), max(2, round(obj.height * sc))
    obj = obj.resize((nw, nh), Image.LANCZOS)
    mask = mask.resize((nw, nh), Image.LANCZOS).filter(ImageFilter.GaussianBlur(max(0.6, long_px / 120)))
    x0, y0 = cx - nw // 2, cy - nh // 2
    local = frame.crop((x0 - nw, y0 - nh, x0 + 2 * nw, y0 + 2 * nh))
    lum_local = ImageStat.Stat(local.convert("L")).median[0]
    if src_bg is not None:
        lum_src = 0.299 * src_bg[0] + 0.587 * src_bg[1] + 0.114 * src_bg[2]
        obj = ImageEnhance.Brightness(obj).enhance(max(min_gain, min(1.4, lum_local / max(lum_src, 1))))
    sh = Image.new("RGB", (nw, nh), (0, 0, 0))
    shm = mask.point(lambda v: int(v * 0.35)).filter(ImageFilter.GaussianBlur(max(1, long_px / 30)))
    frame.paste(sh, (x0 + max(1, nw // 25), y0 + max(1, nh // 12)), shm)
    frame.paste(obj, (x0, y0), mask)
    # ground-truth box = extent of the pasted object (mask above 30%), not of the faint shadow fringe
    mb = mask.point(lambda v: 255 if v > 76 else 0).getbbox() or (0, 0, nw, nh)
    W, H = frame.size
    box = [max(0, x0 + mb[0] - 1), max(0, y0 + mb[1] - 1), min(W, x0 + mb[2] + 1), min(H, y0 + mb[3] + 1)]
    # visibility: mean absolute change inside the object, in grey levels (0 = the paste changed nothing)
    diff = np.asarray(ImageChops.difference(before, frame).convert("L").crop((x0, y0, x0 + nw, y0 + nh)), dtype=np.float32)
    m = np.asarray(mask.crop((0, 0, diff.shape[1], diff.shape[0])), dtype=np.float32) / 255.0
    contrast = float((diff * m).sum() / max(1.0, m.sum()))
    return box, contrast
