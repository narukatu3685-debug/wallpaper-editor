"""wallpaper_slideshow.py のテスト（TC-56〜TC-65）。docs/04-implementation/impl-notes.md 参照。
IDesktopWallpaperの実際のCOM呼び出し（ctypesのvtable部分）は実機Windowsでしか検証できないため、
`_create_desktop_wallpaper_com` をモックし、上位関数が正しい引数・順序で呼び出しているかのみを
検証する（tests/test_wallpaper.py と同じ方針）。
"""
from unittest.mock import MagicMock, call

import pytest

from wallpaper_editor.wallpaper_slideshow import (
    SlideshowError,
    SlideshowStatus,
    disable_slideshow,
    enable_slideshow,
    get_slideshow_status,
    is_slideshow_supported,
)


def _patch_com(monkeypatch, mock_com):
    monkeypatch.setattr(
        "wallpaper_editor.wallpaper_slideshow._create_desktop_wallpaper_com", lambda: mock_com
    )


# --- TC-56: enable_slideshowは正しい順序・引数でCOMラッパーを呼ぶ ---
def test_enable_slideshow_calls_com_with_correct_args(monkeypatch):
    mock_com = MagicMock()
    _patch_com(monkeypatch, mock_com)

    enable_slideshow("C:\\out\\ver3_edited_20260901_000000", 30)

    mock_com.set_slideshow_folder.assert_called_once_with(
        "C:\\out\\ver3_edited_20260901_000000"
    )
    mock_com.set_slideshow_options.assert_called_once_with(shuffle=True, tick_ms=30 * 60 * 1000)
    mock_com.enable.assert_called_once_with(True)
    mock_com.release.assert_called_once()
    # フォルダ設定→間隔設定→有効化、の順で呼ばれていること
    assert [c[0] for c in mock_com.method_calls[:3]] == [
        "set_slideshow_folder", "set_slideshow_options", "enable"
    ]


# --- TC-57: interval_minutesが0以下ならCOMを呼ばずSlideshowErrorを送出する ---
def test_enable_slideshow_rejects_non_positive_interval(monkeypatch):
    mock_com = MagicMock()
    _patch_com(monkeypatch, mock_com)

    with pytest.raises(SlideshowError):
        enable_slideshow("C:\\out", 0)

    mock_com.set_slideshow_folder.assert_not_called()


# --- TC-58: COMオブジェクトの生成自体が失敗したらSlideshowErrorを送出する ---
def test_enable_slideshow_wraps_com_creation_failure(monkeypatch):
    def raise_oserror():
        raise OSError("class not registered")

    monkeypatch.setattr(
        "wallpaper_editor.wallpaper_slideshow._create_desktop_wallpaper_com", raise_oserror
    )

    with pytest.raises(SlideshowError):
        enable_slideshow("C:\\out", 30)


# --- TC-59: COMメソッド呼び出し中の失敗でもreleaseは必ず呼ばれる ---
def test_enable_slideshow_releases_com_even_on_failure(monkeypatch):
    mock_com = MagicMock()
    mock_com.set_slideshow_options.side_effect = OSError("SetSlideshowOptions failed")
    _patch_com(monkeypatch, mock_com)

    with pytest.raises(SlideshowError):
        enable_slideshow("C:\\out", 30)

    mock_com.release.assert_called_once()


# --- TC-60: disable_slideshowはフォールバック画像でset_wallpaperを呼ぶ ---
def test_disable_slideshow_sets_fallback_wallpaper(monkeypatch):
    mock_com = MagicMock()
    _patch_com(monkeypatch, mock_com)

    disable_slideshow("C:\\out\\wallpaper_001.jpg")

    mock_com.set_wallpaper.assert_called_once_with("C:\\out\\wallpaper_001.jpg")
    mock_com.release.assert_called_once()


# --- TC-61: disable_slideshow中の失敗はSlideshowErrorにラップされる ---
def test_disable_slideshow_wraps_failure(monkeypatch):
    mock_com = MagicMock()
    mock_com.set_wallpaper.side_effect = OSError("SetWallpaper failed")
    _patch_com(monkeypatch, mock_com)

    with pytest.raises(SlideshowError):
        disable_slideshow("C:\\out\\wallpaper_001.jpg")

    mock_com.release.assert_called_once()


# --- TC-62: get_slideshow_statusはON中なら間隔(分)も返す ---
def test_get_slideshow_status_when_enabled(monkeypatch):
    mock_com = MagicMock()
    mock_com.get_status.return_value = 0x01  # DSS_ENABLED
    mock_com.get_slideshow_options.return_value = (True, 30 * 60 * 1000)
    _patch_com(monkeypatch, mock_com)

    status = get_slideshow_status()

    assert status == SlideshowStatus(enabled=True, interval_minutes=30)


# --- TC-63: get_slideshow_statusはOFF中はget_slideshow_optionsを呼ばずinterval_minutes=None ---
def test_get_slideshow_status_when_disabled(monkeypatch):
    mock_com = MagicMock()
    mock_com.get_status.return_value = 0x00
    _patch_com(monkeypatch, mock_com)

    status = get_slideshow_status()

    assert status == SlideshowStatus(enabled=False, interval_minutes=None)
    mock_com.get_slideshow_options.assert_not_called()


# --- TC-64: is_slideshow_supportedはCOM生成に成功すればTrue（releaseも呼ぶ） ---
def test_is_slideshow_supported_true(monkeypatch):
    mock_com = MagicMock()
    _patch_com(monkeypatch, mock_com)

    assert is_slideshow_supported() is True
    mock_com.release.assert_called_once()


# --- TC-65: is_slideshow_supportedはCOM生成が失敗すればFalse ---
def test_is_slideshow_supported_false(monkeypatch):
    def raise_oserror():
        raise OSError("class not registered")

    monkeypatch.setattr(
        "wallpaper_editor.wallpaper_slideshow._create_desktop_wallpaper_com", raise_oserror
    )

    assert is_slideshow_supported() is False
