"""settings.py のテスト（TC-18〜TC-19）。docs/04-implementation/impl-notes.md 参照。"""
from wallpaper_editor.image_ops import AdjustmentSettings
from wallpaper_editor.settings import load_settings, save_settings


# --- TC-18: 保存した設定を読み込むと同じ内容が復元される ---
def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    original = AdjustmentSettings(saturate=120, vignette=40, resize_w=1920, resize_h=1080)

    save_settings(original, path)
    loaded = load_settings(path)

    assert loaded == original


# --- TC-19: ファイルが無い/壊れている場合は初期値にフォールバックする ---
def test_load_settings_falls_back_to_default_when_missing_or_corrupt(tmp_path):
    missing = tmp_path / "missing.json"
    assert load_settings(missing) == AdjustmentSettings()

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not valid json", encoding="utf-8")
    assert load_settings(corrupt) == AdjustmentSettings()


# --- TC-41: crop_rect（タプル）を保存・読込しても型が壊れず一致する ---
def test_save_and_load_roundtrip_with_crop_rect(tmp_path):
    path = tmp_path / "settings.json"
    original = AdjustmentSettings(crop_rect=(0.1, 0.2, 0.8, 0.9), filter_preset="sepia", flip_h=True, rotate=90)

    save_settings(original, path)
    loaded = load_settings(path)

    assert loaded == original
    assert isinstance(loaded.crop_rect, tuple)


# --- TC-55: hsl_bands・tone_curve（ネストしたdataclass）を保存・読込しても型が壊れず一致する ---
def test_save_and_load_roundtrip_with_nested_dataclasses(tmp_path):
    from wallpaper_editor.image_ops import HslBand, ToneCurve

    path = tmp_path / "settings.json"
    original = AdjustmentSettings(
        hsl_bands=[HslBand(hue_deg=0, saturation=40, lightness=-10)],
        tone_curve=ToneCurve(rgb=[(100, 130)], r=[(50, 70)]),
    )

    save_settings(original, path)
    loaded = load_settings(path)

    assert loaded == original
    assert isinstance(loaded.hsl_bands[0], HslBand)
    assert isinstance(loaded.tone_curve, ToneCurve)
    assert isinstance(loaded.tone_curve.rgb[0], tuple)
