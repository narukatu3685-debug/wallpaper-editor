import ctypes

SPI_SETDESKWALLPAPER = 20
SPIF_UPDATEINIFILE_SENDCHANGE = 3  # 設定をレジストリに保存 + 全ウィンドウへ変更通知


class WallpaperError(Exception):
    """壁紙の設定に失敗したときに送出する。"""


def _get_user32():
    return ctypes.windll.user32  # Windows専用（ctypes.windll はWindowsにしか存在しない）


def set_desktop_wallpaper(image_path) -> None:
    """Windows のデスクトップ壁紙を image_path に設定する。失敗時は WallpaperError を送出する。"""
    path_str = str(image_path)
    user32 = _get_user32()
    result = user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, path_str, SPIF_UPDATEINIFILE_SENDCHANGE
    )
    if not result:
        raise WallpaperError(f"デスクトップ壁紙の設定に失敗しました: {path_str}")
