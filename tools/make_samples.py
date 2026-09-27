"""デモ用のサンプル壁紙（1920x1080）を生成する。

著作権のある画像を同梱しないで済むように、グラデーションとノイズだけで風景風の画像を作る。
使い方: python tools/make_samples.py
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

W, H = 1920, 1080
ROOT = Path(__file__).resolve().parent.parent
OUT_DIRS = [ROOT / "samples", ROOT / "prototype" / "assets"]
rng = np.random.default_rng(42)


def vertical_gradient(stops):
    """stops: [(位置0..1, (r,g,b)), ...] から縦グラデーションを作る。"""
    ys = np.linspace(0, 1, H)
    pos = [s[0] for s in stops]
    img = np.zeros((H, W, 3), np.float32)
    for c in range(3):
        col = np.interp(ys, pos, [s[1][c] for s in stops])
        img[:, :, c] = col[:, None]
    return img


def ridge(base, amp, octaves, seed):
    """横方向に連なる山の稜線（高さ[px]の配列）。"""
    r = np.random.default_rng(seed)
    x = np.linspace(0, 1, W)
    y = np.full(W, float(base))
    for o in range(octaves):
        f = 2 ** o
        y += amp / f * np.sin(2 * np.pi * (x * f * 1.3 + r.random()))
    return y


def fill_below(img, heights, color, fade=0.0):
    rows = np.arange(H)[:, None]
    mask = rows >= heights[None, :]
    shade = np.clip((rows - heights[None, :]) / H * fade, 0, 1)[..., None]
    layer = np.array(color, np.float32) * (1 - shade)
    img[mask] = layer[mask]


def stars(img, n, brightness=255):
    ys = rng.integers(0, int(H * 0.6), n)
    xs = rng.integers(0, W, n)
    v = rng.uniform(0.3, 1.0, n)[:, None] * brightness
    img[ys, xs] = np.maximum(img[ys, xs], v)


def save(img, name, blur=0.0):
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    for d in OUT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        im.save(d / name, quality=90)


# 1. 夕焼けの山並み
img = vertical_gradient([(0, (40, 30, 90)), (0.45, (230, 110, 90)), (0.7, (255, 200, 120)), (1, (255, 220, 160))])
yy, xx = np.mgrid[0:H, 0:W]
sun = np.exp(-(((xx - 1300) ** 2 + (yy - 640) ** 2) / (2 * 90.0 ** 2)))[..., None]
img = img * (1 - sun) + np.array([255, 245, 210]) * sun
for i, (base, col) in enumerate([(620, (120, 70, 100)), (720, (80, 45, 80)), (840, (45, 25, 55))]):
    fill_below(img, ridge(base, 70 - i * 10, 5, i), col)
save(img, "sample-01.jpg", blur=0.8)

# 2. 星空と湖
img = vertical_gradient([(0, (5, 8, 30)), (0.55, (20, 40, 90)), (0.62, (40, 70, 120)), (1, (5, 10, 25))])
stars(img, 2500)
fill_below(img, ridge(600, 50, 5, 7), (10, 15, 35))
img[700:] = img[700:] * 0.6 + img[700 - (np.arange(H - 700) + 1)][:, :, :] * 0.25
save(img, "sample-02.jpg", blur=0.5)

# 3. 海と空
img = vertical_gradient([(0, (70, 140, 220)), (0.5, (170, 215, 245)), (0.52, (30, 110, 170)), (1, (10, 50, 100))])
waves = (np.sin(xx / 23.0 + yy / 5.0) * np.sin(xx / 71.0) * 12)[..., None] * (yy > 560)[..., None]
img = img + waves
def smooth_noise(gh, gw):
    small = Image.fromarray((rng.random((gh, gw)) * 255).astype(np.uint8))
    big = small.resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(W / gw / 2))
    return np.array(big, np.float32) / 255


clouds = 0.55 * smooth_noise(4, 7) + 0.3 * smooth_noise(8, 14) + 0.15 * smooth_noise(16, 28)
clouds = (clouds - clouds.min()) / (clouds.max() - clouds.min())
horizon_fade = np.clip((560 - yy) / 200, 0, 1)
cmask = (np.clip((clouds - 0.5) * 2.2, 0, 0.9) * horizon_fade)[..., None]
img = img * (1 - cmask) + 255 * cmask
save(img, "sample-03.jpg", blur=1.0)

# 4. 霧の森
img = vertical_gradient([(0, (190, 210, 200)), (0.5, (150, 180, 165)), (1, (60, 90, 70))])
for i in range(4):
    depth = i / 3
    col = np.array([150, 175, 160]) * (1 - depth) + np.array([25, 55, 40]) * depth
    base = 480 + i * 130
    for _ in range(40 + i * 10):
        cx = rng.integers(0, W)
        h = rng.integers(200, 380) * (0.6 + depth * 0.6)
        top = base - h
        rows = np.arange(max(int(top), 0), H)
        half = (rows - top) / h * (40 + depth * 40)
        for r, hw in zip(rows, half):
            img[r, max(int(cx - hw), 0):min(int(cx + hw), W)] = col
save(img, "sample-04.jpg", blur=1.5)

print("generated:", [str(d) for d in OUT_DIRS])
