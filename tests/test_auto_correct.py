"""auto_correct.py のテスト（TC-33〜TC-36）。docs/04-implementation/impl-notes.md 参照。"""
import numpy as np
from PIL import Image

from wallpaper_editor.auto_correct import (
    adaptive_tone,
    auto_contrast,
    auto_white_balance,
    vivid_preset,
)


# --- TC-33: オートコントラストは、明暗レンジが狭い（眠い）画像のコントラストを引き上げる ---
def test_auto_contrast_boosts_flat_image():
    arr = np.full((40, 40, 3), 128, dtype=np.uint8)
    arr[:, :20] = 110  # 明暗差がわずかしかない「眠い」画像
    arr[:, 20:] = 146
    img = Image.fromarray(arr, mode="RGB")

    result = auto_contrast(img)

    assert result.contrast > 100


# --- TC-34: オートホワイトバランスは、赤かぶりした画像を寒色側に補正する ---
def test_auto_white_balance_corrects_warm_cast():
    arr = np.zeros((30, 30, 3), dtype=np.uint8)
    arr[..., 0] = 200  # R強め（赤かぶり）
    arr[..., 1] = 120
    arr[..., 2] = 80   # B弱め
    img = Image.fromarray(arr, mode="RGB")

    result = auto_white_balance(img)

    assert result.warmth < 0  # 寒色側（Bを持ち上げる方向）に補正される


# --- TC-35: オートホワイトバランスは、無彩色の画像には補正をほぼかけない ---
def test_auto_white_balance_neutral_image_stays_near_zero():
    img = Image.new("RGB", (20, 20), (128, 128, 128))
    result = auto_white_balance(img)
    assert abs(result.warmth) <= 2


# --- TC-36: 適応的トーン補正は、明暗レンジが狭い画像ほど明瞭度を強くかける ---
def test_adaptive_tone_boosts_clarity_more_for_flatter_image():
    flat = Image.new("RGB", (30, 30), (130, 130, 130))
    arr = np.zeros((30, 30, 3), dtype=np.uint8)
    for x in range(30):
        arr[:, x] = int(255 * x / 29)
    contrasty = Image.fromarray(arr, mode="RGB")

    flat_result = adaptive_tone(flat)
    contrasty_result = adaptive_tone(contrasty)

    assert flat_result.clarity > contrasty_result.clarity


# --- TC-37: おまかせ強調（Vivid）は画像に関わらず常に同じ固定値を返す ---
def test_vivid_preset_returns_fixed_values():
    result1 = vivid_preset()
    result2 = vivid_preset()
    assert result1 == result2
    assert result1.saturate > 100
    assert result1.vibrance > 0
