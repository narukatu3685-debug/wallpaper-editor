"""wallpaper.py のテスト（TC-16〜TC-17）。docs/04-implementation/impl-notes.md 参照。
ctypes.windll は実際には呼ばず、モックして呼び出し引数・エラーハンドリングだけを検証する。
"""
from unittest.mock import MagicMock

import pytest

from wallpaper_editor.wallpaper import SPI_SETDESKWALLPAPER, WallpaperError, set_desktop_wallpaper


# --- TC-16: 正しい定数・パスで SystemParametersInfoW が呼ばれる ---
def test_set_desktop_wallpaper_calls_winapi_with_correct_args(monkeypatch):
    mock_user32 = MagicMock()
    mock_user32.SystemParametersInfoW.return_value = 1  # 成功
    monkeypatch.setattr("wallpaper_editor.wallpaper._get_user32", lambda: mock_user32)

    set_desktop_wallpaper("C:\\dummy\\path\\image.jpg")

    mock_user32.SystemParametersInfoW.assert_called_once_with(
        SPI_SETDESKWALLPAPER, 0, "C:\\dummy\\path\\image.jpg", 3
    )


# --- TC-17: WinAPIが失敗（戻り値0）を返したら WallpaperError を送出する ---
def test_set_desktop_wallpaper_raises_on_failure(monkeypatch):
    mock_user32 = MagicMock()
    mock_user32.SystemParametersInfoW.return_value = 0  # 失敗
    monkeypatch.setattr("wallpaper_editor.wallpaper._get_user32", lambda: mock_user32)

    with pytest.raises(WallpaperError):
        set_desktop_wallpaper("C:\\dummy\\path\\image.jpg")
