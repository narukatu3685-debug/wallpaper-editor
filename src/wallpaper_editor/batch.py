from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from wallpaper_editor.image_ops import AdjustmentSettings, apply_adjustments


@dataclass
class BatchResult:
    total: int
    succeeded: int
    failed: list[tuple[str, str]] = field(default_factory=list)
    output_dir: Path | None = None


_PIL_FORMATS = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}


def process_folder(
    source_dir: Path,
    output_dir: Path,
    settings: AdjustmentSettings,
    output_format: str = "jpg",       # F-20: "jpg" | "png" | "webp"
    output_quality: int = 92,
    rename_prefix: str = "wallpaper_",  # F-27
    rename_start: int = 1,
    rename_digits: int = 3,
    extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png"),
) -> BatchResult:
    """source_dir 直下（サブフォルダは含めない）の対象拡張子の画像すべてに
    apply_adjustments を適用し、output_dir に
    f"{rename_prefix}{n:0{rename_digits}d}.{output_format}" として保存する。
    source_dir の内容は一切変更しない。1枚失敗しても残りの処理は継続する。
    """
    source_dir = Path(source_dir)
    output_dir = Path(output_dir)

    targets = sorted(
        p for p in source_dir.iterdir()
        if p.is_file() and p.suffix.lower() in extensions
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    pil_format = _PIL_FORMATS.get(output_format.lower(), "JPEG")
    ext = output_format.lower()

    succeeded = 0
    failed: list[tuple[str, str]] = []
    number = rename_start

    for path in targets:
        out_name = f"{rename_prefix}{number:0{rename_digits}d}.{ext}"
        try:
            with Image.open(path) as img:
                img.load()
                processed = apply_adjustments(img, settings)
            if pil_format == "JPEG" and processed.mode != "RGB":
                processed = processed.convert("RGB")
            save_kwargs = {"quality": output_quality} if pil_format in ("JPEG", "WEBP") else {}
            processed.save(output_dir / out_name, pil_format, **save_kwargs)
            succeeded += 1
        except (UnidentifiedImageError, OSError) as e:
            failed.append((path.name, str(e)))
        finally:
            number += 1

    return BatchResult(
        total=len(targets),
        succeeded=succeeded,
        failed=failed,
        output_dir=output_dir,
    )
