from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


@dataclass
class HslBand:
    """F-23: 色相帯ごとの彩度・明度補正。"""
    hue_deg: int           # 帯の中心角度（固定）
    saturation: int = 0    # -100-100
    lightness: int = 0     # -100-100


def default_hsl_bands() -> list["HslBand"]:
    return [HslBand(hue_deg=d) for d in range(0, 360, 45)]  # 8帯（45度刻み）


@dataclass
class ToneCurve:
    """F-21: 各チャンネルのカーブ制御点。空リスト=無調整（恒等）。(x, y) は0-255。"""
    rgb: list[tuple[int, int]] = field(default_factory=list)
    r: list[tuple[int, int]] = field(default_factory=list)
    g: list[tuple[int, int]] = field(default_factory=list)
    b: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class AdjustmentSettings:
    saturate: int = 100      # 0-200（%）
    brightness: int = 100    # 0-200（%）
    contrast: int = 100      # 0-200（%）
    hue: int = 0              # -180-180（度）
    sharpen: int = 0          # 0-100
    warmth: int = 0           # -100-100（負=寒色 / 正=暖色）
    highlights: int = 0       # -50-50
    shadows: int = 0          # -50-50
    vignette: int = 0         # 0-100（%）
    vibrance: int = 0         # 0-100（自然な彩度。くすんだ色ほど強くブースト）
    clarity: int = 0          # 0-100（明瞭度・ローカルコントラスト）
    blur: int = 0              # 0-20（F-09 全体ぼかし。ガウスぼかし半径に相当）
    denoise: int = 0           # 0-100（F-26 ノイズ除去）
    filter_preset: str = "none"   # F-07: "none" | "mono" | "sepia" | "vintage"
    flip_h: bool = False       # F-13
    flip_v: bool = False       # F-13
    rotate: int = 0             # F-14。0/90/180/270のみ
    crop_rect: tuple[float, float, float, float] | None = None  # F-15（相対座標 x0,y0,x1,y1）
    frame_width: int = 0        # F-16
    frame_color: str = "#e0913a"  # F-16
    hsl_bands: list[HslBand] = field(default_factory=default_hsl_bands)  # F-23
    tone_curve: ToneCurve = field(default_factory=ToneCurve)              # F-21
    super_res_enabled: bool = False  # F-28（アップスケール時のみ効果あり）
    resize_w: int | None = None
    resize_h: int | None = None


def apply_adjustments(img: Image.Image, settings: AdjustmentSettings) -> Image.Image:
    """docs/03-design/api-spec.md の順序で加工する:
    反転・回転 → トリミング → プリセットフィルター → 色相 → 色温度 → 彩度 →
    自然な彩度(Vibrance) → HSL個別調整 → トーンカーブ → 明るさ → コントラスト → 明瞭度 →
    ハイライト/シャドウ → シャープネス → ノイズ除去 → 全体ぼかし → ビネット →
    フレーム → リサイズ（アップスケール時のみsuper_res_enabledが効く）
    元の img は変更せず、新しい Image を返す。
    """
    out = img.convert("RGB")

    if settings.flip_h or settings.flip_v:
        out = flip_image(out, settings.flip_h, settings.flip_v)
    if settings.rotate != 0:
        out = rotate_image(out, settings.rotate)
    if settings.crop_rect is not None:
        out = crop_image(out, settings.crop_rect)
    if settings.filter_preset != "none":
        out = apply_filter_preset(out, settings.filter_preset)
    if settings.hue != 0:
        out = _adjust_hue(out, settings.hue)
    if settings.warmth != 0:
        out = _adjust_warmth(out, settings.warmth)
    if settings.saturate != 100:
        out = ImageEnhance.Color(out).enhance(settings.saturate / 100)
    if settings.vibrance != 0:
        out = _adjust_vibrance(out, settings.vibrance)
    for band in settings.hsl_bands:
        out = adjust_hsl_band(out, band)
    out = apply_tone_curve(out, settings.tone_curve)
    if settings.brightness != 100:
        out = ImageEnhance.Brightness(out).enhance(settings.brightness / 100)
    if settings.contrast != 100:
        out = ImageEnhance.Contrast(out).enhance(settings.contrast / 100)
    if settings.clarity != 0:
        out = _adjust_clarity(out, settings.clarity)
    if settings.highlights != 0 or settings.shadows != 0:
        out = _adjust_highlights_shadows(out, settings.highlights, settings.shadows)
    if settings.sharpen != 0:
        out = out.filter(ImageFilter.UnsharpMask(radius=2, percent=int(settings.sharpen * 3), threshold=3))
    if settings.denoise != 0:
        out = apply_denoise(out, settings.denoise)
    if settings.blur != 0:
        out = apply_blur(out, settings.blur)
    if settings.vignette != 0:
        out = _apply_vignette(out, settings.vignette)
    if settings.frame_width > 0:
        out = add_frame(out, settings.frame_width, settings.frame_color)
    if settings.resize_w and settings.resize_h:
        out = resize_to_fill(out, settings.resize_w, settings.resize_h, enhance=settings.super_res_enabled)

    return out


def flip_image(img: Image.Image, flip_h: bool, flip_v: bool) -> Image.Image:
    """F-13: 左右・上下反転。"""
    out = img
    if flip_h:
        out = out.transpose(Image.FLIP_LEFT_RIGHT)
    if flip_v:
        out = out.transpose(Image.FLIP_TOP_BOTTOM)
    return out


_VALID_ROTATIONS = (0, 90, 180, 270)


def rotate_image(img: Image.Image, degrees: int) -> Image.Image:
    """F-14: 90度単位の回転。degreesは0/90/180/270のみ許可する。"""
    if degrees not in _VALID_ROTATIONS:
        raise ValueError(f"rotate は 0/90/180/270 のいずれかである必要があります: {degrees}")
    if degrees == 0:
        return img
    return img.rotate(-degrees, expand=True)


def crop_image(img: Image.Image, rect: tuple[float, float, float, float]) -> Image.Image:
    """F-15: rect は元画像に対する相対座標 (x0, y0, x1, y1)、いずれも0.0-1.0。"""
    w, h = img.size
    x0, y0, x1, y1 = rect
    box = (
        max(0, round(x0 * w)),
        max(0, round(y0 * h)),
        min(w, round(x1 * w)),
        min(h, round(y1 * h)),
    )
    return img.crop(box)


def apply_filter_preset(img: Image.Image, preset: str) -> Image.Image:
    """F-07: "none" | "mono" | "sepia" | "vintage"。未知の値は無加工として扱う。"""
    if preset == "mono":
        gray = img.convert("L")
        return Image.merge("RGB", (gray, gray, gray))
    if preset == "sepia":
        return _apply_sepia(img, strength=1.0)
    if preset == "vintage":
        toned = _apply_sepia(img, strength=0.3)
        toned = ImageEnhance.Contrast(toned).enhance(0.92)
        toned = ImageEnhance.Brightness(toned).enhance(1.05)
        return toned
    return img


def _apply_sepia(img: Image.Image, strength: float) -> Image.Image:
    gray = np.array(img.convert("L"), dtype=np.float64)
    sepia_color = np.array([112.0, 66.0, 20.0])  # 暖色（茶色）のトーン
    sepia = gray[..., None] / 255.0 * sepia_color[None, None, :] + gray[..., None] * (1 - sepia_color.max() / 255)
    sepia = np.clip(sepia, 0, 255)
    gray_rgb = np.repeat(gray[..., None], 3, axis=2)
    blended = gray_rgb * (1 - strength) + sepia * strength
    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8), mode="RGB")


def apply_blur(img: Image.Image, amount: int) -> Image.Image:
    """F-09: 全体ぼかし。amountは0-20（ガウスぼかし半径0-8px相当）。"""
    radius = amount * 0.4
    return img.filter(ImageFilter.GaussianBlur(radius=radius))


def apply_denoise(img: Image.Image, amount: int) -> Image.Image:
    """F-26: ノイズ除去。メディアンフィルタ結果を amount(0-100)の割合でブレンドする簡易実装。"""
    if amount <= 0:
        return img
    filtered = img.filter(ImageFilter.MedianFilter(size=3))
    alpha = min(1.0, amount / 100)
    arr = np.array(img).astype(np.float64)
    filtered_arr = np.array(filtered).astype(np.float64)
    blended = arr * (1 - alpha) + filtered_arr * alpha
    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8), mode="RGB")


def add_frame(img: Image.Image, width: int, color: str) -> Image.Image:
    """F-16: 縁取り。画像サイズは上下左右にそれぞれwidthずつ大きくなる。"""
    if width <= 0:
        return img
    return ImageOps.expand(img, border=width, fill=color)


def adjust_hsl_band(img: Image.Image, band: HslBand, band_width_deg: int = 30) -> Image.Image:
    """F-23: 指定した色相帯（band.hue_deg ± band_width_deg/2、境界はなめらかにフェード）
    の彩度・明度だけを補正する。対象外の画素は変更しない。"""
    if band.saturation == 0 and band.lightness == 0:
        return img

    hsv = np.array(img.convert("HSV"), dtype=np.float64)
    hue_deg = hsv[..., 0] / 255.0 * 360.0
    diff = np.abs(((hue_deg - band.hue_deg + 180) % 360) - 180)  # 円環距離
    half_width = band_width_deg / 2
    fade = 5.0
    mask = np.clip(1 - (diff - half_width) / fade, 0, 1)

    if band.saturation != 0:
        s = hsv[..., 1]
        sat_amt = band.saturation / 100
        delta = sat_amt * (255 - s) if sat_amt >= 0 else sat_amt * s
        hsv[..., 1] = np.clip(s + delta * mask, 0, 255)
    if band.lightness != 0:
        v = hsv[..., 2]
        hsv[..., 2] = np.clip(v + (band.lightness / 100) * 128 * mask, 0, 255)

    return Image.fromarray(hsv.astype(np.uint8), mode="HSV").convert("RGB")


def _catmull_rom(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    t2, t3 = t * t, t * t * t
    return 0.5 * (
        2 * p1
        + (-p0 + p2) * t
        + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
        + (-p0 + 3 * p1 - 3 * p2 + p3) * t3
    )


def build_lut(points: list[tuple[int, int]]) -> list[int]:
    """F-21: 制御点からCatmull-Romスプラインで256階調のLUTを作る（RV-06: 折れ線でなく
    なめらかな曲線）。points が空なら恒等LUTを返す。(0,0)と(255,255)は暗黙のアンカーとして
    補間するが、明示的に指定されていればそちらを優先する。"""
    if not points:
        return list(range(256))

    pts = sorted(set(points), key=lambda p: p[0])
    xs = {p[0] for p in pts}
    if 0 not in xs:
        pts = [(0, 0)] + pts
    if 255 not in xs:
        pts = pts + [(255, 255)]
    pts = sorted(pts, key=lambda p: p[0])

    ext = [pts[0]] + pts + [pts[-1]]
    lut = [0] * 256
    for i in range(len(pts) - 1):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        x0, x1 = p1[0], p2[0]
        if x1 <= x0:
            continue
        for x in range(x0, x1):
            t = (x - x0) / (x1 - x0)
            y = _catmull_rom(p0[1], p1[1], p2[1], p3[1], t)
            lut[x] = int(round(max(0, min(255, y))))
    lut[255] = int(round(max(0, min(255, pts[-1][1]))))
    return lut


def apply_tone_curve(img: Image.Image, curve: ToneCurve) -> Image.Image:
    """F-21: 全体(rgb)LUTを先に適用し、その上にR/G/B個別のLUTを重ねて適用する。"""
    if not (curve.rgb or curve.r or curve.g or curve.b):
        return img

    r, g, b = img.split()
    if curve.rgb:
        rgb_lut = build_lut(curve.rgb)
        r, g, b = r.point(rgb_lut), g.point(rgb_lut), b.point(rgb_lut)
    if curve.r:
        r = r.point(build_lut(curve.r))
    if curve.g:
        g = g.point(build_lut(curve.g))
    if curve.b:
        b = b.point(build_lut(curve.b))
    return Image.merge("RGB", (r, g, b))


def _adjust_hue(img: Image.Image, degrees: int) -> Image.Image:
    hsv = np.array(img.convert("HSV"), dtype=np.int16)
    shift = int(round(degrees / 360 * 255))
    hsv[..., 0] = (hsv[..., 0] + shift) % 256
    return Image.fromarray(hsv.astype(np.uint8), mode="HSV").convert("RGB")


def _adjust_warmth(img: Image.Image, warmth: int) -> Image.Image:
    arr = np.array(img).astype(np.int16)
    offset = warmth * 0.5  # -100..100 -> -50..50 のピクセルオフセット
    arr[..., 0] = np.clip(arr[..., 0] + offset, 0, 255)   # R: 暖色で増加
    arr[..., 2] = np.clip(arr[..., 2] - offset, 0, 255)   # B: 暖色で減少
    return Image.fromarray(arr.astype(np.uint8), mode="RGB")


def _adjust_vibrance(img: Image.Image, amount: int) -> Image.Image:
    """彩度の低いピクセルほど強く彩度を上げ、既に鮮やかなピクセルはほぼ変えない。"""
    hsv = np.array(img.convert("HSV"), dtype=np.float64)
    s = hsv[..., 1]
    boost = (amount / 100) * 0.8 * (255 - s)  # 低彩度ほどboostが大きい
    hsv[..., 1] = np.clip(s + boost, 0, 255)
    return Image.fromarray(hsv.astype(np.uint8), mode="HSV").convert("RGB")


def _adjust_clarity(img: Image.Image, amount: int) -> Image.Image:
    """半径の大きいアンシャープマスクで、輪郭・質感のローカルコントラストを強調する。"""
    return img.filter(ImageFilter.UnsharpMask(radius=8, percent=int(amount * 2.5), threshold=2))


def _adjust_highlights_shadows(img: Image.Image, highlights: int, shadows: int) -> Image.Image:
    arr = np.array(img).astype(np.float64)
    luminance = arr.mean(axis=2) / 255.0  # 0(暗)〜1(明) per pixel

    if highlights != 0:
        mask = luminance[..., None]  # 明るい部分ほど強く効く
        arr = arr + highlights * mask
    if shadows != 0:
        mask = (1 - luminance)[..., None]  # 暗い部分ほど強く効く
        arr = arr + shadows * mask

    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")


def _apply_vignette(img: Image.Image, strength: int) -> Image.Image:
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = (w - 1) / 2, (h - 1) / 2
    max_dist = np.sqrt(cx**2 + cy**2)
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / max_dist  # 0(中心)〜1(角)

    alpha = (strength / 100) * 0.9
    darken = 1 - dist * alpha  # 中心=1（そのまま）、角ほど暗くなる

    arr = np.array(img).astype(np.float64)
    arr = arr * darken[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")


def resize_to_fill(img: Image.Image, target_w: int, target_h: int, enhance: bool = False) -> Image.Image:
    """中央クロップしてから target_w x target_h にリサイズする（黒帯を作らない）。
    api-spec.md のとおり、壁紙用途では画面いっぱいに表示することを優先する設計判断。
    enhance=True（F-28、super_res_enabled）のときは、単純なLANCZOSではなく
    弱ノイズ低減→Lanczos拡大→アンシャープマスクの3段階（_enhanced_upscale）で処理する。
    """
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        # 元画像の方が横長 → 左右をクロップ
        new_w = int(round(src_h * target_ratio))
        left = (src_w - new_w) // 2
        box = (left, 0, left + new_w, src_h)
    else:
        # 元画像の方が縦長（またはアスペクト比一致） → 上下をクロップ
        new_h = int(round(src_w / target_ratio))
        top = (src_h - new_h) // 2
        box = (0, top, src_w, top + new_h)

    cropped = img.crop(box)
    if enhance:
        return _enhanced_upscale(cropped, target_w, target_h)
    return cropped.resize((target_w, target_h), Image.LANCZOS)


def _enhanced_upscale(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """F-28: AIモデルは使わず、Pillow単体で現実的に可能な最高品質でアップスケールする
    （questions.md Q-01「現実的な可能な範囲での高精度化」）。
    弱いノイズ低減（圧縮ノイズの増幅を抑える）→ Lanczos拡大 → アンシャープマスク（輪郭補正）。"""
    denoised = img.filter(ImageFilter.GaussianBlur(radius=0.4))
    resized = denoised.resize((target_w, target_h), Image.LANCZOS)
    return resized.filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=2))
