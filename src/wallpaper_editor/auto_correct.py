"""F-18: 自動補正（4パターン）。docs/03-design/api-spec.md 参照。

各関数は「加工済み画像」ではなく AdjustmentSettings（の一部）を返す。
GUI側でこれを現在の設定にマージしてからスライダーに反映し、
apply_adjustments() で実際に適用する（自動補正後もスライダーで微調整できるようにするため）。
"""
import numpy as np
from PIL import Image

from wallpaper_editor.image_ops import AdjustmentSettings


def auto_contrast(img: Image.Image, cutoff: float = 1.0) -> AdjustmentSettings:
    """① オートコントラスト。上下cutoff%の外れ値を無視して明暗レンジを0-255に
    引き伸ばす係数から brightness / contrast を算出する。"""
    gray = np.array(img.convert("L"), dtype=np.float64)
    lo, hi = np.percentile(gray, [cutoff, 100 - cutoff])
    rng = max(1.0, hi - lo)
    contrast = int(round(min(200, max(60, (255 / rng) * 100))))
    median = np.percentile(gray, 50)
    brightness = int(round(min(130, max(80, 100 + (128 - median) * 0.15))))
    return AdjustmentSettings(brightness=brightness, contrast=contrast)


def auto_white_balance(img: Image.Image) -> AdjustmentSettings:
    """② オートホワイトバランス（グレーワールド法）。R/Bチャンネルの平均の偏りから
    既存の色温度（warmth）調整で補正できる量を算出する。"""
    arr = np.array(img.convert("RGB"), dtype=np.float64)
    r_avg = arr[..., 0].mean()
    b_avg = arr[..., 2].mean()
    warmth = int(round(max(-100, min(100, -(r_avg - b_avg)))))
    return AdjustmentSettings(warmth=warmth)


def adaptive_tone(img: Image.Image) -> AdjustmentSettings:
    """③ 適応的トーン補正。明暗レンジが狭い（眠い写り）画像ほど明瞭度(clarity)を
    強めに算出する。本格的なCLAHEはOpenCVという新規依存が必要になるため、
    既存のclarity処理の自動版として実装する（api-spec.md参照）。"""
    gray = np.array(img.convert("L"), dtype=np.float64)
    p1, p99 = np.percentile(gray, [1, 99])
    rng = max(1.0, p99 - p1)
    clarity = int(round(min(100, max(0, (255 - rng) / 255 * 100))))
    return AdjustmentSettings(clarity=clarity)


def vivid_preset() -> AdjustmentSettings:
    """④ おまかせ強調（Vivid）。画像解析を行わず、鮮やかさ重視の固定値を返す。"""
    return AdjustmentSettings(brightness=104, contrast=108, saturate=112, vibrance=40)
