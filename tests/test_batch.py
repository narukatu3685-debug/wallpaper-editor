"""batch.py のテスト（TC-10〜TC-15）。docs/04-implementation/impl-notes.md 参照。"""
import hashlib

from PIL import Image

from wallpaper_editor.batch import process_folder
from wallpaper_editor.image_ops import AdjustmentSettings


def make_jpg(path, color=(120, 140, 160), size=(20, 20)):
    Image.new("RGB", size, color).save(path, "JPEG")


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- TC-10: 対象拡張子の画像すべてが出力フォルダに生成される ---
def test_process_folder_writes_all_images(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    for i in range(3):
        make_jpg(src / f"wallpaper_{i:03d}.jpg")
    out = tmp_path / "output"

    result = process_folder(src, out, AdjustmentSettings(brightness=120))

    assert result.total == 3
    assert result.succeeded == 3
    assert len(list(out.glob("*.jpg"))) == 3


# --- TC-11: 元フォルダ（source_dir）のファイルは一切変更されない ---
def test_process_folder_does_not_modify_source(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    make_jpg(src / "a.jpg")
    before_hash = file_hash(src / "a.jpg")
    out = tmp_path / "output"

    process_folder(src, out, AdjustmentSettings(brightness=150, vignette=60))

    after_hash = file_hash(src / "a.jpg")
    assert before_hash == after_hash


# --- TC-12: 画像以外の拡張子（例: .html）は対象外で、処理件数にも含まれない ---
def test_process_folder_ignores_non_target_extensions(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    make_jpg(src / "a.jpg")
    (src / "index.html").write_text("<html></html>")
    out = tmp_path / "output"

    result = process_folder(src, out, AdjustmentSettings())

    assert result.total == 1
    assert not (out / "index.html").exists()


# --- TC-13: 壊れた画像ファイルが1つあっても、他のファイルは処理が継続する ---
def test_process_folder_continues_after_one_failure(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    make_jpg(src / "good.jpg")
    (src / "broken.jpg").write_bytes(b"not a real jpg")
    out = tmp_path / "output"

    result = process_folder(src, out, AdjustmentSettings())

    assert result.total == 2
    assert result.succeeded == 1
    assert len(result.failed) == 1
    assert result.failed[0][0] == "broken.jpg"
    assert (out / "wallpaper_002.jpg").exists()  # broken.jpgが1番、good.jpgが2番（名前順）でリネームされる


# --- TC-14: サブフォルダ内の画像は対象外（直下のみ処理する） ---
def test_process_folder_ignores_subfolders(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    make_jpg(src / "top.jpg")
    sub = src / "sub"
    sub.mkdir()
    make_jpg(sub / "nested.jpg")
    out = tmp_path / "output"

    result = process_folder(src, out, AdjustmentSettings())

    assert result.total == 1
    assert not (out / "nested.jpg").exists()


# --- TC-15: 出力先フォルダが存在しない場合は自動作成する ---
def test_process_folder_creates_output_dir(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    make_jpg(src / "a.jpg")
    out = tmp_path / "does" / "not" / "exist" / "yet"

    process_folder(src, out, AdjustmentSettings())

    assert out.exists()
    assert (out / "wallpaper_001.jpg").exists()


# --- TC-38: 出力形式をpngに指定すると、拡張子pngで保存される ---
def test_process_folder_output_format_png(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    make_jpg(src / "a.jpg")
    out = tmp_path / "output"

    result = process_folder(src, out, AdjustmentSettings(), output_format="png", rename_prefix="w_", rename_start=1, rename_digits=2)

    assert result.succeeded == 1
    assert (out / "w_01.png").exists()
    assert Image.open(out / "w_01.png").format == "PNG"


# --- TC-39: バッチリネームは元ファイル名の順に連番を振る ---
def test_process_folder_batch_rename_sequential(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    make_jpg(src / "b.jpg", color=(10, 10, 10))
    make_jpg(src / "a.jpg", color=(200, 200, 200))
    out = tmp_path / "output"

    process_folder(
        src, out, AdjustmentSettings(),
        output_format="jpg", rename_prefix="wallpaper_", rename_start=5, rename_digits=3,
    )

    assert (out / "wallpaper_005.jpg").exists()  # a.jpg（名前順で先）
    assert (out / "wallpaper_006.jpg").exists()  # b.jpg


# --- TC-40: RGBA画像をjpgで出力してもクラッシュせず保存できる（アルファは破棄） ---
def test_process_folder_flattens_alpha_for_jpg(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    Image.new("RGBA", (20, 20), (10, 20, 30, 128)).save(src / "a.png")
    out = tmp_path / "output"

    result = process_folder(src, out, AdjustmentSettings(), output_format="jpg", extensions=(".png",))

    assert result.succeeded == 1
    assert Image.open(out / "wallpaper_001.jpg").mode == "RGB"
