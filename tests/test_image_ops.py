"""image_ops.py のテスト（TC-01〜TC-09, TC-20〜TC-21, TC-22〜TC-31）。docs/04-implementation/impl-notes.md 参照。"""
import numpy as np
import pytest
from PIL import Image

from wallpaper_editor.image_ops import AdjustmentSettings, apply_adjustments, resize_to_fill


def colorful_image(size=(60, 40)) -> Image.Image:
    """彩度・明暗にムラのあるテスト用画像（左右で色相・明るさが変わるグラデーション）。"""
    w, h = size
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for x in range(w):
        arr[:, x, 0] = int(255 * x / (w - 1))          # 赤: 左→右で増加
        arr[:, x, 2] = int(255 * (1 - x / (w - 1)))     # 青: 左→右で減少
    for y in range(h):
        arr[y, :, 1] = int(255 * y / (h - 1))           # 緑: 上→下で増加
    return Image.fromarray(arr, mode="RGB")


def mean_rgb(img: Image.Image):
    return np.array(img).astype(float).reshape(-1, 3).mean(axis=0)


def channel_spread(img: Image.Image):
    """各ピクセルのR/G/Bのばらつき（彩度の目安）。0に近いほどグレースケールに近い。"""
    arr = np.array(img).astype(float)
    return (arr.max(axis=2) - arr.min(axis=2)).mean()


# --- TC-01: 彩度を0にするとグレースケールに近づく ---
def test_saturate_zero_removes_color_spread():
    img = colorful_image()
    settings = AdjustmentSettings(saturate=0)
    out = apply_adjustments(img, settings)
    assert channel_spread(out) < channel_spread(img) * 0.05


# --- TC-02: 明るさを上げると平均輝度が上がる ---
def test_brightness_increases_mean():
    img = colorful_image()
    out = apply_adjustments(img, AdjustmentSettings(brightness=160))
    assert mean_rgb(out).mean() > mean_rgb(img).mean()


# --- TC-03: コントラストを上げるとピクセル値のばらつき（標準偏差）が大きくなる ---
def test_contrast_increases_std():
    img = colorful_image()
    out = apply_adjustments(img, AdjustmentSettings(contrast=170))
    std_before = np.array(img).astype(float).std()
    std_after = np.array(out).astype(float).std()
    assert std_after > std_before


# --- TC-04: 色相を180度回転すると色味が反転する（赤が強い場所が変化する） ---
def test_hue_rotation_changes_dominant_channel():
    img = colorful_image()
    out = apply_adjustments(img, AdjustmentSettings(hue=180))
    # 色相を180度回すと、右端（元は赤が強い）の支配色が変わるはず
    orig_px = np.array(img)[20, -1]
    out_px = np.array(out)[20, -1]
    assert int(np.argmax(orig_px)) != int(np.argmax(out_px))


# --- TC-05: ビネットをかけると四隅が中心より暗くなる ---
def test_vignette_darkens_corners_more_than_center():
    img = Image.new("RGB", (100, 100), (200, 200, 200))
    out = apply_adjustments(img, AdjustmentSettings(vignette=80))
    arr = np.array(out).astype(float)
    center = arr[45:55, 45:55].mean()
    corner = arr[0:10, 0:10].mean()
    assert corner < center


# --- TC-06: リサイズは指定サイズちょうどになる（元画像とアスペクト比が異なっても） ---
@pytest.mark.parametrize("target", [(200, 100), (50, 200), (16, 16)])
def test_resize_to_fill_exact_size(target):
    img = colorful_image(size=(300, 150))
    out = resize_to_fill(img, *target)
    assert out.size == target


# --- TC-07: 極端なアスペクト比でもクラッシュせずサイズ通りになる（境界値） ---
def test_resize_to_fill_extreme_aspect_ratio():
    img = colorful_image(size=(300, 150))
    out = resize_to_fill(img, 10, 500)
    assert out.size == (10, 500)


# --- TC-08: すべて初期値なら加工結果は元画像と一致する（no-op） ---
def test_default_settings_are_noop():
    img = colorful_image()
    out = apply_adjustments(img, AdjustmentSettings())
    assert np.array_equal(np.array(img), np.array(out))


# --- TC-09: apply_adjustments は元画像オブジェクトを変更しない ---
def test_apply_adjustments_does_not_mutate_input():
    img = colorful_image()
    before = np.array(img).copy()
    apply_adjustments(img, AdjustmentSettings(brightness=150, vignette=50))
    after = np.array(img)
    assert np.array_equal(before, after)


def _channel_spread(img: Image.Image, x0: int, x1: int) -> float:
    arr = np.array(img)[:, x0:x1].astype(float)
    return (arr.max(axis=2) - arr.min(axis=2)).mean()


# --- TC-20: Vibrance はくすんだ色を、既に鮮やかな色より強くブーストする ---
def test_vibrance_boosts_muted_colors_more_than_saturated():
    w, h = 40, 20
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, : w // 2] = [150, 140, 130]  # くすんだ色（低彩度）
    arr[:, w // 2 :] = [255, 0, 0]      # 既に鮮やかな色（高彩度）
    img = Image.fromarray(arr, mode="RGB")

    out = apply_adjustments(img, AdjustmentSettings(vibrance=100))

    muted_delta = _channel_spread(out, 0, w // 2) - _channel_spread(img, 0, w // 2)
    vivid_delta = _channel_spread(out, w // 2, w) - _channel_spread(img, w // 2, w)
    assert muted_delta > vivid_delta


# --- TC-21: 明瞭度（ローカルコントラスト）を上げると画像全体のばらつきが増える ---
def test_clarity_increases_contrast():
    img = colorful_image()
    out_plain = apply_adjustments(img, AdjustmentSettings())
    out_clarity = apply_adjustments(img, AdjustmentSettings(clarity=80))

    std_plain = np.array(out_plain).astype(float).std()
    std_clarity = np.array(out_clarity).astype(float).std()
    assert std_clarity > std_plain


# --- TC-22: 左右反転（flip_h）で左右のピクセルが入れ替わる ---
def test_flip_h_mirrors_horizontally():
    img = colorful_image()
    out = apply_adjustments(img, AdjustmentSettings(flip_h=True))
    orig = np.array(img)
    flipped = np.array(out)
    assert np.array_equal(flipped[:, 0], orig[:, -1])
    assert not np.array_equal(flipped, orig)


# --- TC-23: 上下反転（flip_v）で上下のピクセルが入れ替わる ---
def test_flip_v_mirrors_vertically():
    img = colorful_image()
    out = apply_adjustments(img, AdjustmentSettings(flip_v=True))
    orig = np.array(img)
    flipped = np.array(out)
    assert np.array_equal(flipped[0, :], orig[-1, :])
    assert not np.array_equal(flipped, orig)


# --- TC-24: 90度回転で幅と高さが入れ替わる ---
def test_rotate_90_swaps_dimensions():
    img = colorful_image(size=(60, 40))
    out = apply_adjustments(img, AdjustmentSettings(rotate=90))
    assert out.size == (40, 60)


# --- TC-25: 90度単位以外の回転角は不正値としてエラーになる（境界値） ---
def test_rotate_invalid_degrees_raises():
    img = colorful_image()
    with pytest.raises(ValueError):
        apply_adjustments(img, AdjustmentSettings(rotate=45))


# --- TC-26: トリミングは相対座標どおりのサイズにクロップされる ---
def test_crop_rect_produces_expected_relative_size():
    img = colorful_image(size=(200, 100))
    out = apply_adjustments(img, AdjustmentSettings(crop_rect=(0.25, 0.25, 0.75, 0.75)))
    assert out.size == (100, 50)


# --- TC-27: crop_rect が None なら何もクロップされない（no-op） ---
def test_crop_rect_none_is_noop():
    img = colorful_image(size=(200, 100))
    out = apply_adjustments(img, AdjustmentSettings(crop_rect=None))
    assert out.size == img.size


# --- TC-28: プリセットフィルター「モノクロ」はR=G=Bになる ---
def test_filter_preset_mono_removes_color():
    img = colorful_image()
    out = apply_adjustments(img, AdjustmentSettings(filter_preset="mono"))
    arr = np.array(out).astype(int)
    assert np.allclose(arr[..., 0], arr[..., 1], atol=1)
    assert np.allclose(arr[..., 1], arr[..., 2], atol=1)


# --- TC-29: プリセットフィルター「セピア」はグレー画像を暖色（R>G>B）に寄せる ---
def test_filter_preset_sepia_warms_gray_image():
    img = Image.new("RGB", (40, 40), (128, 128, 128))
    out = apply_adjustments(img, AdjustmentSettings(filter_preset="sepia"))
    r, g, b = mean_rgb(out)
    assert r > g > b


# --- TC-30: プリセットフィルター「なし」は無加工（no-op） ---
def test_filter_preset_none_is_noop():
    img = colorful_image()
    out = apply_adjustments(img, AdjustmentSettings(filter_preset="none"))
    assert np.array_equal(np.array(img), np.array(out))


# --- TC-31: 全体ぼかしをかけると隣接ピクセル間の差（高周波成分）が小さくなる ---
def test_blur_reduces_local_variance():
    w, h = 40, 40
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, ::2] = [255, 255, 255]  # 縦縞の高周波パターン
    img = Image.fromarray(arr, mode="RGB")

    out = apply_adjustments(img, AdjustmentSettings(blur=15))
    out_arr = np.array(out).astype(float)
    diffs = np.abs(np.diff(out_arr[..., 0], axis=1))
    orig_diffs = np.abs(np.diff(arr[..., 0].astype(float), axis=1))
    assert diffs.mean() < orig_diffs.mean()


# --- TC-32: 反転・回転・トリミングは、リサイズより先に適用される（組み合わせても指定サイズちょうどになる） ---
def test_transform_then_resize_combo_hits_exact_target_size():
    img = colorful_image(size=(60, 40))
    out = apply_adjustments(
        img,
        AdjustmentSettings(rotate=90, crop_rect=(0.1, 0.1, 0.9, 0.9), resize_w=300, resize_h=200),
    )
    assert out.size == (300, 200)


# --- TC-42: フレーム幅0なら画像サイズは変わらない（no-op） ---
def test_frame_width_zero_is_noop():
    img = colorful_image(size=(50, 30))
    out = apply_adjustments(img, AdjustmentSettings(frame_width=0))
    assert out.size == img.size


# --- TC-43: フレームを付けると、縁取り幅の分だけ画像サイズが大きくなる ---
def test_frame_width_increases_size():
    img = colorful_image(size=(50, 30))
    out = apply_adjustments(img, AdjustmentSettings(frame_width=10, frame_color="#ff0000"))
    assert out.size == (70, 50)  # 上下左右+10pxずつ


# --- TC-44: フレームの縁の色は指定した色になる ---
def test_frame_color_matches_border_pixels():
    img = Image.new("RGB", (40, 40), (0, 0, 0))
    out = apply_adjustments(img, AdjustmentSettings(frame_width=5, frame_color="#00ff00"))
    arr = np.array(out)
    assert tuple(arr[0, 0]) == (0, 255, 0)


# --- TC-45: トーンカーブの制御点が空なら無加工（恒等LUT） ---
def test_tone_curve_empty_points_is_noop():
    from wallpaper_editor.image_ops import ToneCurve

    img = colorful_image()
    out = apply_adjustments(img, AdjustmentSettings(tone_curve=ToneCurve()))
    assert np.array_equal(np.array(img), np.array(out))


# --- TC-46: 明部側を持ち上げるカーブ点を追加すると、明るいピクセルの値が上がる ---
def test_tone_curve_highlight_point_brightens_bright_pixels():
    from wallpaper_editor.image_ops import ToneCurve

    img = Image.new("RGB", (20, 20), (200, 200, 200))
    curve = ToneCurve(rgb=[(200, 230)])  # 入力200付近の出力を230に持ち上げる
    out = apply_adjustments(img, AdjustmentSettings(tone_curve=curve))
    arr = np.array(out)
    assert arr.mean() > 200


# --- TC-47: RチャンネルだけのカーブはG/Bチャンネルに影響しない ---
def test_tone_curve_r_channel_only_affects_red():
    from wallpaper_editor.image_ops import ToneCurve

    img = Image.new("RGB", (20, 20), (100, 100, 100))
    curve = ToneCurve(r=[(100, 180)])
    out = apply_adjustments(img, AdjustmentSettings(tone_curve=curve))
    arr = np.array(out)
    assert arr[..., 0].mean() > 150
    assert abs(arr[..., 1].mean() - 100) < 2
    assert abs(arr[..., 2].mean() - 100) < 2


# --- TC-48: build_lutは折れ線ではなくなめらかに変化する（隣接値の急激な飛びがない） ---
def test_build_lut_is_smooth():
    from wallpaper_editor.image_ops import build_lut

    lut = build_lut([(64, 90), (128, 140), (192, 170)])
    diffs = [abs(lut[i + 1] - lut[i]) for i in range(255)]
    assert max(diffs) < 10  # なめらかな曲線なら隣接値の差は小さいはず


# --- TC-49: HSL個別調整は、対象の色相帯だけ彩度を変える ---
def test_hsl_band_desaturates_only_target_hue():
    from wallpaper_editor.image_ops import HslBand

    w, h = 40, 20
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, : w // 2] = [255, 0, 0]   # 赤（色相0度）
    arr[:, w // 2 :] = [0, 0, 255]   # 青（色相240度）
    img = Image.fromarray(arr, mode="RGB")

    band = HslBand(hue_deg=0, saturation=-100, lightness=0)
    out = apply_adjustments(img, AdjustmentSettings(hsl_bands=[band]))
    out_arr = np.array(out).astype(float)

    red_spread = (out_arr[:, : w // 2].max(axis=2) - out_arr[:, : w // 2].min(axis=2)).mean()
    blue_spread = (out_arr[:, w // 2 :].max(axis=2) - out_arr[:, w // 2 :].min(axis=2)).mean()
    assert red_spread < 100  # 赤は彩度が落ちてグレーに近づく
    assert blue_spread > 200  # 青はほぼそのまま鮮やか


# --- TC-50: HSL個別調整で彩度・明度とも0の帯は何も変えない ---
def test_hsl_band_zero_is_noop():
    from wallpaper_editor.image_ops import HslBand

    img = colorful_image()
    band = HslBand(hue_deg=0, saturation=0, lightness=0)
    out = apply_adjustments(img, AdjustmentSettings(hsl_bands=[band]))
    assert np.array_equal(np.array(img), np.array(out))


# --- TC-51: ノイズ除去（denoise）をかけると、ざらつき（ノイズ）のばらつきが減る ---
def test_denoise_reduces_noise_variance():
    rng = np.random.default_rng(0)
    base = np.full((40, 40, 3), 128, dtype=np.int16)
    noise = rng.integers(-40, 40, size=(40, 40, 3))
    arr = np.clip(base + noise, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr, mode="RGB")

    out = apply_adjustments(img, AdjustmentSettings(denoise=80))
    assert np.array(out).astype(float).std() < arr.astype(float).std()


# --- TC-52: denoise=0は無加工（no-op） ---
def test_denoise_zero_is_noop():
    img = colorful_image()
    out = apply_adjustments(img, AdjustmentSettings(denoise=0))
    assert np.array_equal(np.array(img), np.array(out))


# --- TC-53: 高精度アップスケール有効時、拡大先はちょうど指定サイズになる ---
def test_upscale_enabled_hits_exact_target_size():
    img = colorful_image(size=(60, 40))
    out = apply_adjustments(
        img, AdjustmentSettings(super_res_enabled=True, resize_w=300, resize_h=200)
    )
    assert out.size == (300, 200)


# --- TC-54: 高精度アップスケール有効/無効で、拡大結果の画素が異なる（何らかの後処理が効いている） ---
def test_upscale_enabled_differs_from_plain_resize():
    # 滑らかなグラデーションだとぼかし/シャープの効果が丸め誤差に埋もれてしまうため、
    # 高周波成分（市松模様）を含む画像で検証する。
    arr = np.zeros((40, 60, 3), dtype=np.uint8)
    arr[::2, ::2] = 255
    arr[1::2, 1::2] = 255
    img = Image.fromarray(arr, mode="RGB")

    plain = apply_adjustments(img, AdjustmentSettings(resize_w=240, resize_h=160))
    enhanced = apply_adjustments(
        img, AdjustmentSettings(super_res_enabled=True, resize_w=240, resize_h=160)
    )
    assert not np.array_equal(np.array(plain), np.array(enhanced))
