import json
import os
from dataclasses import asdict
from pathlib import Path

from wallpaper_editor.image_ops import AdjustmentSettings, HslBand, ToneCurve

SETTINGS_FILENAME = "last_settings.json"


def settings_path() -> Path:
    appdata = os.environ.get("APPDATA", str(Path.home()))
    return Path(appdata) / "WallpaperEditor" / SETTINGS_FILENAME


def load_settings(path: Path | None = None) -> AdjustmentSettings:
    """直近の調整値を読み込む。ファイルが無い/壊れている場合は初期値を返す（起動は失敗させない）。"""
    path = path or settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {f for f in AdjustmentSettings.__dataclass_fields__}
        fields = {k: v for k, v in data.items() if k in known}
        if fields.get("crop_rect") is not None:
            fields["crop_rect"] = tuple(fields["crop_rect"])
        if fields.get("hsl_bands") is not None:
            fields["hsl_bands"] = [HslBand(**b) for b in fields["hsl_bands"]]
        if fields.get("tone_curve") is not None:
            curve = fields["tone_curve"]
            fields["tone_curve"] = ToneCurve(**{
                ch: [tuple(p) for p in curve.get(ch, [])] for ch in ("rgb", "r", "g", "b")
            })
        return AdjustmentSettings(**fields)
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return AdjustmentSettings()


def save_settings(settings: AdjustmentSettings, path: Path | None = None) -> None:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
