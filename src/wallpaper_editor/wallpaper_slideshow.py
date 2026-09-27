"""Windows標準の「デスクトップの背景」スライドショー機能を、IDesktopWallpaper COMインターフェース
（CLSID_DesktopWallpaper、Windows 8以降）経由で設定する（対応: F-10）。

pywin32 / comtypes 等の追加依存を避けるため、wallpaper.py と同じ方針でctypesのみを使う。
IDesktopWallpaperはIDispatchベースではないネイティブCOMインターフェースのため、vtable（関数
ポインタテーブル）を手動で定義し、直接呼び出す。

【重要】GUID・vtableの並び順・列挙値はWindows SDKの`shobjidl.h`に基づく値だが、この開発環境では
実機のCOM呼び出しを検証できない（`CLAUDE.md`「動作確認・起動方法」参照）。ホスト（Windows）で
実際に動作確認すること。単体テスト（`tests/test_wallpaper_slideshow.py`）は `_create_desktop_wallpaper_com`
をモックし、上位関数がCOMラッパーに対して正しい引数・順序で呼び出しているかのみを検証している。
"""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# --- COM定数（shobjidl.h、要ホスト実機確認） ---
CLSID_DesktopWallpaper = "{C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD}"
IID_IDesktopWallpaper = "{B92B56A9-8B55-4E14-9A89-0199BBB6F93B}"
IID_IShellItem = "{43826D1E-E718-42EE-BC55-A1E261C37BFE}"
IID_IShellItemArray = "{B63EA76D-1F85-456F-A19C-48159EFA858B}"

CLSCTX_LOCAL_SERVER = 0x4

DSO_SHUFFLEIMAGES = 0x01  # SetSlideshowOptionsの表示順オプション（シャッフル有効）
DSS_ENABLED = 0x01        # GetStatusの戻り値ビット（スライドショー動作中）

# IDesktopWallpaperのvtableインデックス（IUnknownの3つ + 以下の順、shobjidl.h準拠）
_VT_RELEASE = 2
_VT_SET_WALLPAPER = 3
_VT_SET_SLIDESHOW = 12
_VT_SET_SLIDESHOW_OPTIONS = 14
_VT_GET_SLIDESHOW_OPTIONS = 15
_VT_GET_STATUS = 17
_VT_ENABLE = 18


class SlideshowError(Exception):
    """スライドショーの設定・取得に失敗したときに送出する。"""


@dataclass
class SlideshowStatus:
    enabled: bool
    interval_minutes: Optional[int]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_uint8 * 8),
    ]

    @classmethod
    def from_string(cls, guid_str: str) -> "GUID":
        guid = cls()
        ole32 = _get_ole32()
        hr = ole32.CLSIDFromString(guid_str, ctypes.byref(guid))
        if hr != 0:
            raise OSError(f"GUIDの解析に失敗しました: {guid_str}（HRESULT=0x{hr & 0xFFFFFFFF:08X}）")
        return guid


def _get_ole32():
    return ctypes.windll.ole32


def _get_shell32():
    return ctypes.windll.shell32


def _hresult_check(hr: int, message: str) -> None:
    # COMの規約上、HRESULTの成否は符号ビットで決まる（FAILED(hr) は hr < 0）。
    # S_FALSE（0x00000001）等の非0でも成功を表すコードがあるため、hr != 0 では誤判定する。
    if hr < 0:
        raise OSError(f"{message}（HRESULT=0x{hr & 0xFFFFFFFF:08X}）")


def _com_call(this: int, index: int, restype, argtypes, *args):
    """COMオブジェクトポインタ `this` のvtableの`index`番目のメソッドを、指定シグネチャで呼び出す。"""
    vtable_ptr = ctypes.cast(this, ctypes.POINTER(ctypes.c_void_p)).contents.value
    slot = vtable_ptr + index * ctypes.sizeof(ctypes.c_void_p)
    func_ptr = ctypes.cast(slot, ctypes.POINTER(ctypes.c_void_p)).contents.value
    func_type = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    func = func_type(func_ptr)
    return func(this, *args)


def _create_slideshow_item_array(folder: Path) -> ctypes.c_void_p:
    """フォルダ1つを表す IShellItemArray（1要素）を作る。SetSlideshow に渡すと、
    そのフォルダ内の画像すべてがスライドショーの対象になる。"""
    shell32 = _get_shell32()
    item_ptr = ctypes.c_void_p()
    iid_item = GUID.from_string(IID_IShellItem)
    hr = shell32.SHCreateItemFromParsingName(
        str(folder), None, ctypes.byref(iid_item), ctypes.byref(item_ptr)
    )
    _hresult_check(hr, f"SHCreateItemFromParsingNameに失敗しました: {folder}")
    try:
        array_ptr = ctypes.c_void_p()
        iid_array = GUID.from_string(IID_IShellItemArray)
        hr = shell32.SHCreateShellItemArrayFromShellItem(
            item_ptr, ctypes.byref(iid_array), ctypes.byref(array_ptr)
        )
        _hresult_check(hr, "SHCreateShellItemArrayFromShellItemに失敗しました")
        return array_ptr
    finally:
        _com_call(item_ptr, _VT_RELEASE, ctypes.c_long, [])


class _DesktopWallpaperCom:
    """IDesktopWallpaperのvtable呼び出しを、Python的なメソッド名でラップする薄いクラス。
    実際のCOM呼び出しの詳細（vtable順序・引数マーシャリング）をここに閉じ込め、
    上位関数（enable_slideshow等）はこのクラスのメソッドだけを呼ぶ。"""

    def __init__(self, ptr: ctypes.c_void_p):
        self._ptr = ptr

    def set_slideshow_folder(self, folder: Path) -> None:
        item_array = _create_slideshow_item_array(folder)
        try:
            hr = _com_call(
                self._ptr, _VT_SET_SLIDESHOW, ctypes.c_long, [ctypes.c_void_p], item_array
            )
            _hresult_check(hr, f"SetSlideshowに失敗しました: {folder}")
        finally:
            _com_call(item_array, _VT_RELEASE, ctypes.c_long, [])

    def set_slideshow_options(self, shuffle: bool, tick_ms: int) -> None:
        options = DSO_SHUFFLEIMAGES if shuffle else 0
        hr = _com_call(
            self._ptr, _VT_SET_SLIDESHOW_OPTIONS, ctypes.c_long,
            [ctypes.c_int, ctypes.c_uint], options, tick_ms,
        )
        _hresult_check(hr, "SetSlideshowOptionsに失敗しました")

    def get_slideshow_options(self) -> tuple[bool, int]:
        options = ctypes.c_int()
        tick_ms = ctypes.c_uint()
        hr = _com_call(
            self._ptr, _VT_GET_SLIDESHOW_OPTIONS, ctypes.c_long,
            [ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_uint)],
            ctypes.byref(options), ctypes.byref(tick_ms),
        )
        _hresult_check(hr, "GetSlideshowOptionsに失敗しました")
        return bool(options.value & DSO_SHUFFLEIMAGES), tick_ms.value

    def enable(self, flag: bool) -> None:
        hr = _com_call(self._ptr, _VT_ENABLE, ctypes.c_long, [ctypes.c_int], int(flag))
        _hresult_check(hr, "Enableに失敗しました")

    def set_wallpaper(self, path: Optional[str]) -> None:
        hr = _com_call(
            self._ptr, _VT_SET_WALLPAPER, ctypes.c_long,
            [wintypes.LPCWSTR, wintypes.LPCWSTR], None, path,
        )
        _hresult_check(hr, f"SetWallpaperに失敗しました: {path}")

    def get_status(self) -> int:
        state = ctypes.c_int()
        hr = _com_call(
            self._ptr, _VT_GET_STATUS, ctypes.c_long,
            [ctypes.POINTER(ctypes.c_int)], ctypes.byref(state),
        )
        _hresult_check(hr, "GetStatusに失敗しました")
        return state.value

    def release(self) -> None:
        _com_call(self._ptr, _VT_RELEASE, ctypes.c_long, [])


def _ensure_com_initialized() -> None:
    # 既に別スレッド/ライブラリでCOM初期化済みの場合（S_FALSE, RPC_E_CHANGED_MODE）は無視する。
    _get_ole32().CoInitialize(None)


def _create_desktop_wallpaper_com() -> _DesktopWallpaperCom:
    """CLSID_DesktopWallpaperのインスタンスを生成し、IDesktopWallpaperのvtable呼び出しをラップした
    _DesktopWallpaperComを返す。失敗時はOSErrorを送出する。テストではこの関数自体をモックする。"""
    _ensure_com_initialized()
    ole32 = _get_ole32()
    clsid = GUID.from_string(CLSID_DesktopWallpaper)
    iid = GUID.from_string(IID_IDesktopWallpaper)
    ptr = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(
        ctypes.byref(clsid), None, CLSCTX_LOCAL_SERVER, ctypes.byref(iid), ctypes.byref(ptr)
    )
    _hresult_check(hr, "IDesktopWallpaperの生成に失敗しました")
    return _DesktopWallpaperCom(ptr)


def is_slideshow_supported() -> bool:
    """このWindows環境でIDesktopWallpaper（Windows 8以降）が利用できるか判定する。"""
    try:
        com = _create_desktop_wallpaper_com()
    except OSError:
        return False
    com.release()
    return True


def enable_slideshow(folder: Path, interval_minutes: int) -> None:
    """指定フォルダ内の画像すべてを対象に、Windows標準のデスクトップスライドショーを
    ランダム順・指定間隔でONにする。失敗時は SlideshowError を送出する。"""
    if interval_minutes <= 0:
        raise SlideshowError(f"切り替え間隔は1分以上を指定してください: {interval_minutes}")
    try:
        com = _create_desktop_wallpaper_com()
    except OSError as e:
        raise SlideshowError(f"スライドショー機能の初期化に失敗しました: {e}") from e
    try:
        com.set_slideshow_folder(folder)
        com.set_slideshow_options(shuffle=True, tick_ms=interval_minutes * 60 * 1000)
        com.enable(True)
    except OSError as e:
        raise SlideshowError(f"スライドショーの設定に失敗しました: {e}") from e
    finally:
        com.release()


def disable_slideshow(fallback_wallpaper: Path) -> None:
    """スライドショーをOFFにする。`fallback_wallpaper` を単一の壁紙として設定することで、
    Windows側の実装上スライドショーモードから自動的に抜ける。"""
    try:
        com = _create_desktop_wallpaper_com()
    except OSError as e:
        raise SlideshowError(f"スライドショー機能の初期化に失敗しました: {e}") from e
    try:
        com.set_wallpaper(str(fallback_wallpaper))
    except OSError as e:
        raise SlideshowError(f"スライドショーの解除に失敗しました: {e}") from e
    finally:
        com.release()


def get_slideshow_status() -> SlideshowStatus:
    """現在Windows側でスライドショーが有効かどうか・間隔を取得する（アプリ起動時のUI復元用）。"""
    try:
        com = _create_desktop_wallpaper_com()
    except OSError as e:
        raise SlideshowError(f"スライドショー機能の初期化に失敗しました: {e}") from e
    try:
        state = com.get_status()
        enabled = bool(state & DSS_ENABLED)
        if enabled:
            _shuffle, tick_ms = com.get_slideshow_options()
            interval_minutes = max(1, tick_ms // 60000)
        else:
            interval_minutes = None
        return SlideshowStatus(enabled=enabled, interval_minutes=interval_minutes)
    except OSError as e:
        raise SlideshowError(f"スライドショーの状態取得に失敗しました: {e}") from e
    finally:
        com.release()
