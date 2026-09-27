# API仕様

## 前提: Web APIではなく、内部モジュールの関数インターフェース（変更なし）

このアプリはローカル完結のデスクトップツールであり、ネットワーク越しのAPI（REST等）は存在しない。ここではGUI層が呼び出す内部モジュールの公開関数を「API」として定義する（`/implement` はこのインターフェースに従ってTDDで実装する）。

**2026-08-30更新**: F-07・F-09・F-13〜F-28（F-17・F-22・F-24・F-25を除く）を反映し全面改訂。既存の `image_ops.py` にあるVibrance/Clarity実装（F-11/F-12）はそのまま踏襲する。

**2026-09-01更新**: F-10（壁紙のスライドショー化・US-15）を反映し `wallpaper_slideshow.py` を追加。

## モジュール構成（変更なし＋新規2本）

```
src/
├── image_ops.py     … 画像1枚に対する加工処理（純粋関数・単体テストしやすい）
├── auto_correct.py  … 自動補正4パターンの解析・適用（新規）
├── batch.py         … フォルダ単位の一括処理
├── wallpaper.py      … Windowsデスクトップ壁紙の設定（単発の静止画、F-06）
├── wallpaper_slideshow.py … Windows標準スライドショー機能の設定（新規、F-10）
├── settings.py       … 直近の調整値の保存・読込（db-design.md 参照）
└── gui.py            … Tkinter GUI（エントリポイント。上記モジュールを呼び出す）
```

自動補正だけを独立モジュールに切り出す理由: 4アルゴリズムは「画像を解析して`AdjustmentSettings`の一部を算出する」という、他の加工関数（値を受け取って画像に適用する）とは逆方向の処理であり、テスト観点（入力画像→期待される補正値の傾向）も異なるため。

## `image_ops.py`（対応: F-01, F-04, F-07, F-09, F-11〜F-16, F-21, F-23）

```python
@dataclass
class HslBand:
    hue_deg: int          # 帯の中心角度（固定・8帯）
    saturation: int = 0   # -100-100
    lightness: int = 0    # -100-100

@dataclass
class ToneCurve:
    # 各チャンネルの制御点。空リスト = 無調整（対角線）。x,yとも0-255
    rgb: list[tuple[int, int]] = field(default_factory=list)
    r: list[tuple[int, int]] = field(default_factory=list)
    g: list[tuple[int, int]] = field(default_factory=list)
    b: list[tuple[int, int]] = field(default_factory=list)

@dataclass
class AdjustmentSettings:
    saturate: int = 100
    brightness: int = 100
    contrast: int = 100
    hue: int = 0
    sharpen: int = 0
    warmth: int = 0
    vignette: int = 0
    vibrance: int = 0        # 既存実装（F-11）を踏襲
    clarity: int = 0         # 既存実装（F-12）を踏襲
    denoise: int = 0         # F-26
    blur: int = 0             # F-09。0-20（ガウスぼかし半径に相当）
    filter_preset: str = "none"   # F-07: "none" | "mono" | "sepia" | "vintage"

    flip_h: bool = False      # F-13
    flip_v: bool = False      # F-13
    rotate: int = 0            # F-14。0/90/180/270
    crop_rect: tuple[float, float, float, float] | None = None  # F-15（相対座標 x0,y0,x1,y1）
    frame_width: int = 0       # F-16
    frame_color: str = "#e0913a"  # F-16

    hsl_bands: list[HslBand] = field(default_factory=default_hsl_bands)  # F-23
    tone_curve: ToneCurve = field(default_factory=ToneCurve)              # F-21

    resize_w: int | None = None
    resize_h: int | None = None


def apply_adjustments(img: PIL.Image.Image, settings: AdjustmentSettings) -> PIL.Image.Image:
    """次の順序で適用する。元の img は変更しない（新しい Image を返す）。

    1. 反転・回転（flip_h, flip_v, rotate）… 以降の処理を正しい向きに対して行うため最初に行う
    2. トリミング（crop_rect）
    3. プリセットフィルター（filter_preset）… ベースの色調を決めてから細部を微調整するため早めに適用
    4. 色相 → 色温度 → 彩度 → 自然な彩度(Vibrance) → HSL個別調整
    5. トーンカーブ（各チャンネルのLUT適用）
    6. 明るさ → コントラスト → 明瞭度(Clarity)
    7. シャープネス → ノイズ除去 → 全体ぼかし（denoiseとblurは目的が逆なので同時に強くかける想定はしないが、両方0でなければ両方適用する）
    8. ビネット
    9. フレーム（frame_width）… 縁取りは他の加工の影響を受けないよう最後に追加する
    10. リサイズ（resize_w, resize_h）… 縁取り込みの最終サイズを決めるため最後
    """
```

### トーンカーブの適用（F-21、RV-02・RV-06）

```python
def build_lut(points: list[tuple[int, int]]) -> list[int]:
    """制御点からCatmull-Romスプラインで256階調のLUT（0-255→0-255の対応表）を作る。
    points が空なら恒等LUT（[0,1,2,...,255]）を返す。
    points は (0,0)と(255,255)を暗黙の両端アンカーとして補間する（ユーザーが明示的に
    端点を動かした場合はその点を優先する）。出力は0-255にクリップする。"""

def apply_tone_curve(img: PIL.Image.Image, curve: ToneCurve) -> PIL.Image.Image:
    """rgb LUTを全チャンネルに適用した後、r/g/b LUTをそれぞれの単一チャンネルに追加適用する。
    Pillowの Image.point() にチャンネルごとのLUT（長さ256のリスト）を渡す方式で実装する
    （im.split()で分解 → 各バンドに point() → Image.merge() で再結合）。"""
```

- 折れ線ではなく必ずスプライン補間でLUTを生成すること（RV-06）。補間方法はCatmull-Rom→3次多項式のサンプリングとする（プロトタイプの`strokeSmoothPath`と同じ考え方をLUT生成に置き換える）。

### プリセットフィルター（F-07）

```python
def apply_filter_preset(img: PIL.Image.Image, preset: str) -> PIL.Image.Image:
    """
    "none": 何もしない
    "mono": グレースケール化 (ImageOps.grayscale) してRGBに戻す
    "sepia": グレースケール化した後、セピア色（#704214系）とアルファ合成でデュオトーン化する
    "vintage": sepia相当の弱め合成（30%程度）+ コントラストをやや下げる + 明るさをやや上げる
               （色褪せたような質感。既存のvignette機能と組み合わせて使われる想定）
    """
```

### 反転・回転・トリミング・フレーム（F-13〜F-16）

```python
def flip_image(img, flip_h: bool, flip_v: bool) -> PIL.Image.Image:
    """Image.transpose(FLIP_LEFT_RIGHT) / transpose(FLIP_TOP_BOTTOM) を必要な分だけ適用。"""

def rotate_image(img, degrees: int) -> PIL.Image.Image:
    """Image.rotate(-degrees, expand=True)。90度単位のみ許可（0/90/180/270）。"""

def crop_image(img, rect: tuple[float, float, float, float]) -> PIL.Image.Image:
    """rect は元画像に対する相対座標(x0,y0,x1,y1、0.0-1.0)。img.size を掛けてピクセル座標に
    変換してから img.crop() する。プレビュー用サンプル画像と一括処理対象画像でピクセルサイズが
    異なるため、相対座標で保持する（db-design.md参照）。"""

def add_frame(img, width: int, color: str) -> PIL.Image.Image:
    """ImageOps.expand(img, border=width, fill=color)。"""
```

### HSL個別調整（F-23）

```python
def adjust_hsl_band(img: PIL.Image.Image, band: HslBand, band_width_deg: int = 30) -> PIL.Image.Image:
    """img をHSVに変換し、色相(H)が band.hue_deg ± band_width_deg/2 の範囲にある画素だけを
    対象に、彩度(S)・明度(V)を band.saturation / band.lightness の割合で補正する。
    対象外の画素は変更しない。境界付近は急激な変化を避けるため、band_width_deg の外側
    5度程度でなめらかにフェードアウトするマスクを使う（矩形マスクではなくガウシアン的な重み）。
    numpyでHSV配列を直接操作する（既存の _adjust_hue と同じ実装パターンを流用できる）。"""
```

### ぼかし・ノイズ除去（F-09, F-26）

```python
def apply_blur(img, amount: int) -> PIL.Image.Image:
    """ImageFilter.GaussianBlur(radius=amount * 0.4) 程度の係数で適用（0-20 → 半径0-8px）。"""

def apply_denoise(img, amount: int) -> PIL.Image.Image:
    """ImageFilter.MedianFilter または GaussianBlur の弱いものと、_adjust_clarity の逆方向
    （エッジは保ちつつ平坦部だけ均す）を組み合わせた簡易ノイズ除去。本格的なノイズ除去
    （非局所平均法等）はPillow単体では困難なため、V1では簡易実装にとどめる。"""
```

## `auto_correct.py`（対応: F-18、RV-07で4パターンに拡張）

```python
def auto_contrast(img: PIL.Image.Image, cutoff: float = 1.0) -> AdjustmentSettings:
    """① オートコントラスト。PillowのImageOps.autocontrast(img, cutoff=cutoff)相当の
    考え方で、上下cutoff%の外れ値を無視して明暗レンジを0-255に引き伸ばす係数を算出し、
    brightness / contrast の値として返す（実際の適用はapply_adjustmentsに委ねる）。"""

def auto_white_balance(img: PIL.Image.Image) -> AdjustmentSettings:
    """② オートホワイトバランス（グレーワールド法）。R/G/Bチャンネルの平均値を求め、
    3チャンネルの平均が揃うようウォームス（warmth）ではなく実際のチャンネルゲイン差として
    hue/warmthではなく専用の white_balance_gain（r_gain, g_gain, b_gain）を算出し、
    apply_adjustments とは別に img に直接ゲインを掛けて返す。
    ※デモのCSS近似（warmthスライダーの流用）とは異なり、本実装ではチャンネルごとの
    実ゲイン補正を行う（より正確な色かぶり補正のため）。"""

def adaptive_tone(img: PIL.Image.Image) -> AdjustmentSettings:
    """③ 適応的トーン補正。CLAHEそのものは追加ライブラリ（OpenCV）が必要になり
    依存関係が増えるため、V1では「明瞭度(clarity)」の自動版として実装する: 画像の
    コントラスト分布を解析し、レンジが狭い（＝眠い写り）ほどclarity値を強めに算出して返す。
    本格的なCLAHEへの置き換えは次期検討（opencv-python追加が前提になるため、
    導入するかどうかは別途ユーザーに確認する）。"""

def vivid_preset() -> AdjustmentSettings:
    """④ おまかせ強調（Vivid）。画像解析を行わず、brightness=104, contrast=108,
    saturate=112, vibrance=40 の固定値を返す。"""
```

- いずれの関数も「補正後の画像」ではなく「`AdjustmentSettings`の一部（または差分）」を返し、GUI側でスライダーへ反映してから`apply_adjustments`で実際に適用する設計とする（ui-spec.md §4.5の「自動補正はスライダーの初期値決めの補助」という位置づけに合わせるため。ユーザーは自動補正後もスライダーで微調整できる）。

## `batch.py`（対応: F-03, F-05, F-20, F-27, F-28）

```python
@dataclass
class BatchResult:
    total: int
    succeeded: int
    failed: list[tuple[str, str]]
    output_dir: Path

def process_folder(
    source_dir: Path,
    output_dir: Path,
    settings: AdjustmentSettings,
    output_format: str = "jpg",       # "jpg" | "png" | "webp"
    output_quality: int = 92,
    rename_prefix: str = "wallpaper_",
    rename_start: int = 1,
    rename_digits: int = 3,
    super_res_enabled: bool = False,   # F-28。下記「AIによる高画質化」参照
    extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png"),
) -> BatchResult:
    """source_dir 直下（サブフォルダは含めない）の対象拡張子の画像をファイル名でソートし、
    連番で apply_adjustments を適用、output_dir に
    f"{rename_prefix}{n:0{rename_digits}d}.{output_format}" として保存する。
    jpg保存時はアルファチャンネルを持たないためRGBに変換してから保存する。
    source_dir 内のファイルは一切変更・削除しない。1枚失敗しても処理は継続する。"""
```

- 出力先フォルダ名は `<source_dir>_edited_<YYYYMMDD_HHMMSS>` のまま変更なし。

### AIによる高画質化（F-28）— 技術選定の結論（questions.md Q-01で確定）

外部モデル（例: Real-ESRGAN）を使った真のAI超解像は、追加の重いライブラリ・モデルファイルのダウンロードが必要になり、実装コスト・ディスク容量への影響が大きい。Q-01の回答「A（現実的な可能な範囲での高精度化を実現して）」を受け、V1では**軽量な依存関係のまま、現実的に達成できる最高品質のアップスケール**を目指す。

```python
def upscale(img: PIL.Image.Image, scale: int) -> PIL.Image.Image:
    """super_res_enabled=True のとき呼ばれる。追加のAIモデルは使わず、Pillow/numpyの
    範囲で現実的に可能な最高品質のアップスケールを行う:

    1. 元画像にごく弱いノイズ低減（GaussianBlur radius=0.4程度）をかけ、
       JPEG圧縮ノイズがアップスケールで強調されるのを事前に抑える
    2. Image.resize(new_size, Image.LANCZOS) で拡大する（Pillowの補間方式の中で
       最も高品質。単純な線形補間よりシャープに拡大できる）
    3. 拡大後に ImageFilter.UnsharpMask（radius=2, percent=120程度）で
       輪郭を軽く強調し、Lanczos拡大特有の眠さを補う

    これは「AIによる画像生成的な超解像」ではなく、Pillow単体でできる範囲の
    高精度リサイズであることをUIのトグル説明文に明記すること
    （例:「現実的に可能な範囲で高精度にアップスケールします（AIモデルは使用しません）」）。
    本物のAI超解像（別モデル・別ライブラリが必要）は次期検討とする。"""
```

- 3ステップ（弱ノイズ低減→Lanczos拡大→アンシャープマスク）の組み合わせは、追加ライブラリなしで実現できる中では現実的に最も高品質な結果になる、という設計判断。それでも真のAI超解像（学習済みモデルによる情報補完）には及ばない点は、UI文言で正直に伝える。

## `wallpaper.py`（対応: F-06、変更なし）

```python
def set_desktop_wallpaper(image_path: Path) -> None:
    """Windows の SystemParametersInfoW(SPI_SETDESKWALLPAPER) を ctypes 経由で呼び出す。
    失敗時は WallpaperError を送出する。"""

class WallpaperError(Exception):
    ...
```

## `wallpaper_slideshow.py`（新規、対応: F-10）

```python
@dataclass
class SlideshowStatus:
    enabled: bool             # Windows側で現在スライドショー動作中か
    interval_minutes: int | None  # 動作中の場合の現在の間隔（不明な場合None）

def is_slideshow_supported() -> bool:
    """Windows 8以降（IDesktopWallpaper COMインターフェースが存在するバージョン）かどうかを判定する。"""

def enable_slideshow(folder: Path, interval_minutes: int) -> None:
    """指定フォルダ内の画像すべてを対象に、Windows標準のデスクトップスライドショーをランダム順・
    指定間隔でONにする。失敗時は SlideshowError を送出する。"""

def disable_slideshow() -> None:
    """スライドショーをOFFにする（直前の壁紙1枚の静止表示に戻す）。"""

def get_slideshow_status() -> SlideshowStatus:
    """現在Windows側でスライドショーが有効かどうか・間隔を取得する。
    アプリ起動時にUIのON/OFF表示・間隔プルダウンの初期状態を復元するために使う。"""

class SlideshowError(Exception):
    ...
```

### 実現方式（技術検討結果）

- Windows標準の「デスクトップの背景」スライドショー機能は、`IDesktopWallpaper` COMインターフェース（`CLSID_DesktopWallpaper`、Windows 8以降）で制御する。レジストリを直接書き換える方式は、実際のスライドショー状態が `%APPDATA%\Microsoft\Windows\Themes\slideshow.ini` 等の非公開バイナリ形式にも依存しており不安定なため採用しない。
- `IDesktopWallpaper` はIDispatchベースではないネイティブCOMインターフェースのため、`pywin32`/`comtypes` は追加せず、既存の `wallpaper.py`（`SystemParametersInfoW`をctypesで直接呼ぶ）と同じ方針で、**ctypes単体でvtable（関数ポインタテーブル）を直接呼び出す**実装にする（依存パッケージを増やさない）。
- 使用するメンバ（`shobjidl.h` のvtable順、実装時は必ずWindows SDKヘッダのバージョンで順序を確認すること）:
  1. `SetSlideshow(IShellItemArray* items)` — スライドショー対象を設定。対象は「個々のファイルの配列」ではなく、**対象フォルダ1つを表す `IShellItemArray`**を渡す。これにより「フォルダ内の画像すべて」が対象になり、個々のファイルを列挙する必要がない。**実装時の変更**: `SHParseDisplayName`＋`SHCreateShellItemArrayFromIDLists`（PIDL経由）ではなく、より単純な`SHCreateItemFromParsingName`（フォルダパスから直接`IShellItem`を取得）＋`SHCreateShellItemArrayFromShellItem`（1要素の配列に変換）の組み合わせで実装した（同じ結果をより少ないAPI呼び出しで得られるための実装判断）
  2. `SetSlideshowOptions(DSD_SHUFFLE, tickMS)` — 表示順は要件（Q-20）によりシャッフル固定。`tickMS` は `interval_minutes * 60 * 1000`
  3. `Enable(TRUE)` — デスクトップ壁紙機能の有効化（通常は既にTRUEだが明示的に呼ぶ）
  4. OFF時は `SetWallpaper(NULL, 直前の壁紙パス)` を呼ぶ（単一画像を指定すると、Windowsの実装上スライドショーモードから自動的に抜ける）
  5. `GetStatus(&state)` で `DWDSB_STATE`（`DWDSB_ENABLED`/`DWDSB_DISABLED`/`DWDSB_TEMPORARILY_DISABLED`）を取得し `get_slideshow_status()` の`enabled`に、`GetSlideshowOptions(&options, &tickMS)` の`tickMS`を分に変換して`interval_minutes`に使う
- `is_slideshow_supported()` は `platform.win32_ver()` 等でOSバージョンを見るか、`CoCreateInstance` が `CLASS_E_CLASSNOTREGISTERED` を返すかで判定する。非対応OS（Windows 7以前）ではF-10のUI自体を無効化し、その旨をヒント文言で表示する（`/implement`でUI側に反映）
- COM呼び出し全般（`CoInitialize`/`CoCreateInstance`/`CoUninitialize`、GUID定義、vtable構造体定義）は `wallpaper_slideshow.py` 内に閉じ込め、`gui.py` からは上記の公開関数のみを呼ぶ

## `gui.py`

上記モジュールを呼び出すTkinterアプリ。`ui-spec.md` §1のデザイン言語（4グループ×固有色のインジケーター、数値の等幅表示）は、ttkのスタイル機能（`ttk.Style`）で近い見た目を再現する。Tkinter標準ウィジェットでは`prototype/index.html`ほどの視覚的作り込みは難しいため、**色分けされたグループ見出し（各グループタイトルの前に色付きの小さなラベル/丸を置く）と、スライダー値のモノスペース表示の2点は必須で再現し、それ以外（グラデーション枠線等）は簡略化してよい**。ロジックは可能な限り各モジュールに寄せ、`gui.py` はイベントハンドリングと表示のみを担う。
