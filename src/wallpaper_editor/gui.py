import datetime
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from wallpaper_editor import auto_correct
from wallpaper_editor.batch import process_folder
from wallpaper_editor.image_ops import AdjustmentSettings, apply_adjustments, build_lut
from wallpaper_editor.settings import load_settings, save_settings
from wallpaper_editor.wallpaper import WallpaperError, set_desktop_wallpaper
from wallpaper_editor.wallpaper_slideshow import (
    SlideshowError,
    disable_slideshow,
    enable_slideshow,
    get_slideshow_status,
    is_slideshow_supported,
)

SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "samples"


def default_source_dir() -> Path:
    """起動時に開くフォルダ。環境変数 WALLPAPER_SOURCE_DIR → 開発時の対象フォルダ →
    同梱のサンプル画像フォルダの順に、存在するものを使う（別PCでもそのまま起動できるように）。"""
    candidates = [
        os.environ.get("WALLPAPER_SOURCE_DIR"),
        r"C:\壁紙\backup\ver3",
        SAMPLES_DIR,
    ]
    for c in candidates:
        if c and Path(c).is_dir():
            return Path(c)
    return SAMPLES_DIR


DEFAULT_SOURCE_DIR = default_source_dir()
TARGET_EXTENSIONS = (".jpg", ".jpeg", ".png")
PREVIEW_MAX_SIDE = 640
THUMB_SIZE = (110, 62)
MONO_FONT = ("Consolas", 9)

# 調整グループごとの識別色（ui-spec.md §1「暗室のカラーグレーディング卓」を
# Tkinterのラベル文字色として簡略再現したもの。詳細な暗室UIはprototype限りとする）
GROUP_COLORS = {
    "明るさ系": "#c9761e",     # 現像=アンバー
    "色系": "#a3457f",         # 色素浴=マゼンタ
    "質感・効果系": "#2b8a8f",  # 停止液=シアン
    "変形・仕上げ系": "#5866b8",  # 定着=インディゴ
}

# (グループ名, [(設定のフィールド名, 表示ラベル, 最小値, 最大値), ...])  Q-09の回答によりグループ分け表示
# ハイライト/シャドウは本来トーンカーブ（F-21、Should）に統合予定だが、
# トーンカーブは今回のMust実装範囲外のため、置き換わるまで一時的に維持する。
SLIDER_GROUPS = [
    ("明るさ系", [
        ("brightness", "明るさ", 0, 200),
        ("contrast", "コントラスト", 0, 200),
        ("highlights", "ハイライト", -50, 50),
        ("shadows", "シャドウ", -50, 50),
    ]),
    ("色系", [
        ("saturate", "彩度", 0, 200),
        ("vibrance", "自然な彩度（Vibrance）", 0, 100),
        ("hue", "色相", -180, 180),
        ("warmth", "色温度（寒色 ← → 暖色）", -100, 100),
    ]),
    ("質感・効果系", [
        ("sharpen", "シャープネス", 0, 100),
        ("clarity", "明瞭度", 0, 100),
        ("blur", "全体ぼかし", 0, 20),
        ("denoise", "ノイズ除去（上級）", 0, 100),
        ("vignette", "ビネット（周辺減光）", 0, 100),
    ]),
]
SLIDERS = [s for _group, items in SLIDER_GROUPS for s in items]

FILTER_PRESETS = [
    ("none", "なし"),
    ("mono", "モノクロ"),
    ("sepia", "セピア"),
    ("vintage", "ビンテージ"),
]

AUTO_CORRECT_MODES = [
    ("auto_contrast", "① オートコントラスト"),
    ("auto_white_balance", "② オートホワイトバランス"),
    ("adaptive_tone", "③ 適応的トーン補正"),
    ("vivid", "④ おまかせ強調（Vivid）"),
]

FRAME_COLORS = ["#ffffff", "#000000", "#e0913a", "#5866b8", "#74bf7e"]

HUE_BAND_COLORS = ["#ff5b5b", "#ff9d5b", "#ffe15b", "#7be27b", "#5bd0c9", "#5b9dff", "#9d6bff", "#ff5bd6"]
HUE_BAND_NAMES = ["赤", "橙", "黄", "緑", "青緑", "青", "紫", "マゼンタ"]

CURVE_CHANNELS = [("rgb", "全体"), ("r", "R"), ("g", "G"), ("b", "B")]
CURVE_CHANNEL_COLORS = {"rgb": "#e0913a", "r": "#ff5b5b", "g": "#5bd97b", "b": "#5bb0ff"}
CURVE_W, CURVE_H = 260, 150

RESIZE_PRESETS = [
    ("FHD (1920×1080)", 1920, 1080),
    ("4K (3840×2160)", 3840, 2160),
    ("元のサイズ", None, None),
]

# F-10: スライドショー間隔の選択肢（表示名, 分）。対象フォルダ・表示順（ランダム固定）は
# questions.md ラウンド5 Q-18・Q-20の回答により選択肢を出さない。
SLIDESHOW_INTERVAL_OPTIONS = [
    ("1分ごと", 1),
    ("10分ごと", 10),
    ("30分ごと", 30),
    ("1時間ごと", 60),
    ("6時間ごと", 360),
    ("1日ごと", 1440),
]
SLIDESHOW_DEFAULT_LABEL = "30分ごと"


class WallpaperEditorApp:
    def __init__(self, root: tk.Tk, source_dir: Path = DEFAULT_SOURCE_DIR):
        self.root = root
        self.root.title("壁紙加工ツール")
        self._set_window_icon()

        self.source_dir = Path(source_dir)
        self.settings = load_settings()
        self.image_paths: list[Path] = []
        self.current_index = 0
        self.lock_aspect = tk.BooleanVar(value=True)
        self._thumb_photo_refs: list[ImageTk.PhotoImage] = []
        self._preview_photo = None
        self._slider_vars: dict[str, tk.IntVar] = {}
        self._value_entry_vars: dict[str, tk.StringVar] = {}
        self._crop_mode = False
        self._crop_rect_id = None
        self._crop_start_xy = None
        self._preview_img_box = (0, 0, 0, 0)  # (x, y, w, h) キャンバス上の画像描画位置・サイズ
        self._preview_orig_size = (1, 1)
        self._before_after = tk.BooleanVar(value=False)
        self._hsl_band_index = 0
        self._curve_channel = "rgb"
        self._curve_drag = None  # (channel, index)
        self._last_output_dir: Path | None = None  # F-10: 直近の一括適用(F-03)の出力先
        self._slideshow_on = False

        self._build_layout()
        self.load_folder(self.source_dir)
        self._init_slideshow_state()

        # マウスホイールでのスクロール（サムネイル一覧・調整パネル共通）。
        # キャンバス個別にEnter/Leaveで判定すると、内部の子ウィジェット（サムネイル画像等）に
        # カーソルが乗った瞬間にLeave扱いになり効かなくなるため、ルート全体で一括受け取り、
        # カーソル直下のウィジェットの先祖をたどって対象キャンバスを判定する方式にする。
        self.root.bind_all("<MouseWheel>", self._on_global_mousewheel)

        # pack済みウィジェットの要求サイズに引きずられて自動収縮しないよう、
        # レイアウト構築後に明示的なウィンドウサイズを再設定する（Tkinterの既知の挙動への対処）。
        self.root.update_idletasks()
        self.root.minsize(1100, 640)
        self.root.geometry("1400x900")

    # ------------------------------------------------------------------
    # レイアウト構築（docs/03-design/screen-flow.md のワイヤーフレームに対応）
    # ------------------------------------------------------------------
    def _build_layout(self):
        top = ttk.Frame(self.root, padding=6)
        top.pack(side="top", fill="x")
        ttk.Button(top, text="対象フォルダを開く…", command=self._choose_folder).pack(side="left")
        self.folder_label = ttk.Label(top, text=str(self.source_dir))
        self.folder_label.pack(side="left", padx=8)

        # docs/03-design/screen-flow.md のレイアウト（2026-08-30改訂）:
        # 調整パネル（右列）はウィンドウ上端から下端までフルハイト。
        # アクションバー（一括適用・壁紙設定・出力設定）は、右列の下まで回り込まず
        # 対象画像一覧＋プレビュー（左列）の下にのみ配置する。
        main = ttk.Frame(self.root)
        main.pack(side="top", fill="both", expand=True, padx=6)

        self._build_adjust_panel(main)  # 先にpackして右側の幅を確保（フルハイト）

        left_col = ttk.Frame(main)
        left_col.pack(side="left", fill="both", expand=True)

        content = ttk.Frame(left_col)
        content.pack(side="top", fill="both", expand=True)
        self._build_thumb_panel(content)
        self._build_preview_panel(content)

        bottom = ttk.Frame(left_col, padding=8)
        bottom.pack(side="bottom", fill="x")
        self._build_action_bar(bottom)

    def _build_action_bar(self, bottom):
        buttons_row = ttk.Frame(bottom)
        buttons_row.pack(fill="x")
        ttk.Button(
            buttons_row, text="この設定を対象フォルダの全画像に一括適用", command=self._apply_all
        ).pack(side="left")
        ttk.Button(
            buttons_row, text="この画像をデスクトップ壁紙に設定", command=self._set_wallpaper
        ).pack(side="left", padx=8)
        self.progress = ttk.Progressbar(buttons_row, mode="indeterminate", length=160)
        self.status_label = ttk.Label(buttons_row, text="")
        self.status_label.pack(side="right", padx=8)

        # F-10: スライドショー（壁紙設定ボタンの下、ui-spec.md §9）
        slideshow_row = ttk.Frame(bottom)
        slideshow_row.pack(fill="x", pady=(6, 0))
        ttk.Label(slideshow_row, text="スライドショー（F-10）").pack(side="left")
        self.slideshow_interval_label = tk.StringVar(value=SLIDESHOW_DEFAULT_LABEL)
        self.slideshow_combo = ttk.Combobox(
            slideshow_row, state="readonly", width=10,
            values=[label for label, _minutes in SLIDESHOW_INTERVAL_OPTIONS],
            textvariable=self.slideshow_interval_label,
        )
        self.slideshow_combo.pack(side="left", padx=(6, 6))
        self.slideshow_combo.bind("<<ComboboxSelected>>", self._on_slideshow_interval_change)
        self.slideshow_toggle_btn = ttk.Button(
            slideshow_row, text="スライドショー OFF", command=self._toggle_slideshow
        )
        self.slideshow_toggle_btn.pack(side="left")
        self.slideshow_hint_label = ttk.Label(slideshow_row, text="", foreground="#6b6455")
        self.slideshow_hint_label.pack(side="left", padx=8)

        # F-20: 出力形式 / F-27: バッチリネーム
        output_row = ttk.Frame(bottom)
        output_row.pack(fill="x", pady=(8, 0))

        fmt_box = ttk.LabelFrame(output_row, text="出力形式（F-20）")
        fmt_box.pack(side="left", padx=(0, 12))
        self.output_format = tk.StringVar(value="jpg")
        for fmt in ("jpg", "png", "webp"):
            ttk.Radiobutton(fmt_box, text=fmt, value=fmt, variable=self.output_format).pack(
                side="left", padx=4
            )

        rename_box = ttk.LabelFrame(output_row, text="バッチリネーム（F-27）")
        rename_box.pack(side="left", padx=(0, 12))
        self.rename_prefix = tk.StringVar(value="wallpaper_")
        self.rename_start = tk.StringVar(value="1")
        self.rename_digits = tk.StringVar(value="3")
        ttk.Entry(rename_box, textvariable=self.rename_prefix, width=12).pack(side="left", padx=2)
        ttk.Entry(rename_box, textvariable=self.rename_start, width=4).pack(side="left", padx=2)
        ttk.Entry(rename_box, textvariable=self.rename_digits, width=3).pack(side="left", padx=2)
        self.rename_preview_label = ttk.Label(rename_box, font=MONO_FONT)
        self.rename_preview_label.pack(side="left", padx=6)
        for var in (self.output_format, self.rename_prefix, self.rename_start, self.rename_digits):
            var.trace_add("write", lambda *_: self._update_rename_preview())
        self._update_rename_preview()

        superres_box = ttk.LabelFrame(output_row, text="高画質化（F-28、上級）")
        superres_box.pack(side="left")
        self.super_res_var = tk.BooleanVar(value=self.settings.super_res_enabled)
        ttk.Checkbutton(
            superres_box, text="有効にする（AIモデルは使用しません）",
            variable=self.super_res_var, command=self._on_super_res_change,
        ).pack(side="left", padx=4)

    def _on_super_res_change(self):
        self.settings.super_res_enabled = self.super_res_var.get()
        self._update_preview()

    def _update_rename_preview(self):
        try:
            digits = int(self.rename_digits.get() or "1")
            start = int(self.rename_start.get() or "1")
            name = f"{self.rename_prefix.get()}{start:0{digits}d}.{self.output_format.get()}"
        except ValueError:
            name = "(入力を確認してください)"
        self.rename_preview_label.config(text=f"例: {name}")

    def _set_window_icon(self):
        icon_path = Path(__file__).resolve().parent.parent.parent / "app_icon.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(str(icon_path))
            except tk.TclError:
                pass

    def _on_global_mousewheel(self, event):
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        target = self._scrollable_canvas_of(widget)
        if target is not None:
            target.yview_scroll(-int(event.delta / 40), "units")

    def _scrollable_canvas_of(self, widget):
        """widget自身、またはその祖先を辿って、対応するスクロール用Canvasを返す（無ければNone）。"""
        w = widget
        while w is not None:
            if w is getattr(self, "thumb_canvas", None):
                return self.thumb_canvas
            if w is getattr(self, "adjust_canvas", None):
                return self.adjust_canvas
            w = w.master
        return None

    def _build_thumb_panel(self, parent):
        outer = ttk.Frame(parent, width=160)
        outer.pack(side="left", fill="y")
        outer.pack_propagate(False)
        ttk.Label(outer, text="対象画像").pack(anchor="w")

        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.thumb_frame = ttk.Frame(canvas)
        self.thumb_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.thumb_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.thumb_canvas = canvas

    def _build_preview_panel(self, parent):
        center = ttk.Frame(parent)
        center.pack(side="left", fill="both", expand=True, padx=8)

        toolbar = ttk.Frame(center)
        toolbar.pack(fill="x", pady=(0, 4))
        ttk.Checkbutton(
            toolbar, text="Before / After 比較（F-19）", variable=self._before_after,
            command=self._update_preview,
        ).pack(side="left")

        self.preview_canvas = tk.Canvas(center, background="black", highlightthickness=0)
        self.preview_canvas.pack(fill="both", expand=True)
        self.preview_name_label = ttk.Label(center, text="")
        self.preview_name_label.pack(anchor="w")

        # トリミングモード中（F-15）は、プレビュー上のドラッグが範囲選択として使われる。
        self.preview_canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.preview_canvas.bind("<B1-Motion>", self._on_canvas_drag)

        # ウィンドウを拡大/最大化したら、プレビューもその分大きく表示する（画面に収まるサイズまで）。
        # リサイズ中に何度も再処理しないよう、最後のイベントから少し待って更新する（デバウンス）。
        self._preview_area = (PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE)
        self._resize_after_id = None
        self.preview_canvas.bind("<Configure>", self._on_preview_area_resize)

    def _on_preview_area_resize(self, event):
        self._preview_area = (max(event.width, 100), max(event.height, 100))
        if self._resize_after_id is not None:
            self.root.after_cancel(self._resize_after_id)
        self._resize_after_id = self.root.after(120, self._update_preview)

    # ------------------------------------------------------------------
    # F-15: トリミング（プレビュー上のドラッグ操作）
    # ------------------------------------------------------------------
    def _on_canvas_press(self, event):
        if self._crop_mode:
            self._crop_start_xy = (event.x, event.y)
            if self._crop_rect_id is not None:
                self.preview_canvas.delete(self._crop_rect_id)
                self._crop_rect_id = None

    def _on_canvas_drag(self, event):
        if self._crop_mode and self._crop_start_xy is not None:
            x0, y0 = self._crop_start_xy
            if self._crop_rect_id is not None:
                self.preview_canvas.delete(self._crop_rect_id)
            self._crop_rect_id = self.preview_canvas.create_rectangle(
                x0, y0, event.x, event.y, outline="#e0913a", width=2, dash=(4, 2)
            )

    def _crop_start(self):
        self._crop_mode = True
        self.status_label.config(text="トリミング範囲をプレビュー上でドラッグして指定してください")

    def _crop_confirm(self):
        if self._crop_start_xy is None or self._crop_rect_id is None:
            self.status_label.config(text="先にプレビュー上でドラッグして範囲を指定してください")
            return
        coords = self.preview_canvas.coords(self._crop_rect_id)
        if len(coords) != 4:
            return
        cx0, cy0, cx1, cy1 = coords
        cx0, cx1 = sorted((cx0, cx1))
        cy0, cy1 = sorted((cy0, cy1))

        img_x, img_y, img_w, img_h = self._preview_img_box
        if img_w <= 0 or img_h <= 0:
            return
        # キャンバス座標 → 表示中画像内の相対座標（0.0-1.0）。表示中画像は既にflip/rotateが
        # 適用済みなので、この相対座標はflip/rotate後の画像に対するcrop_rectとして扱う。
        rx0 = min(1.0, max(0.0, (cx0 - img_x) / img_w))
        ry0 = min(1.0, max(0.0, (cy0 - img_y) / img_h))
        rx1 = min(1.0, max(0.0, (cx1 - img_x) / img_w))
        ry1 = min(1.0, max(0.0, (cy1 - img_y) / img_h))
        if rx1 - rx0 < 0.02 or ry1 - ry0 < 0.02:
            self.status_label.config(text="範囲が小さすぎます。もう一度ドラッグしてください")
            return

        self.settings.crop_rect = (rx0, ry0, rx1, ry1)
        self._crop_mode = False
        self.preview_canvas.delete(self._crop_rect_id)
        self._crop_rect_id = None
        self._crop_start_xy = None
        self._update_preview()
        self.status_label.config(text="トリミングを確定しました")

    def _crop_clear(self):
        self._crop_mode = False
        self.settings.crop_rect = None
        if self._crop_rect_id is not None:
            self.preview_canvas.delete(self._crop_rect_id)
            self._crop_rect_id = None
        self._crop_start_xy = None
        self._update_preview()

    def _build_adjust_panel(self, parent):
        outer = ttk.Frame(parent, width=320)
        outer.pack(side="right", fill="y")
        outer.pack_propagate(False)

        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        panel = ttk.Frame(canvas, padding=(0, 0, 8, 0))
        panel.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=panel, anchor="nw", width=300)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.adjust_canvas = canvas

        ttk.Label(panel, text="調整", font=("", 10, "bold")).pack(anchor="w", pady=(0, 4))
        for group_name, items in SLIDER_GROUPS:
            self._build_group_title(panel, group_name)
            for key, label, lo, hi in items:
                self._build_slider_row(panel, key, label, lo, hi)
            if group_name == "明るさ系":
                self._build_tone_curve_row(panel)
            if group_name == "色系":
                self._build_hsl_row(panel)
            if group_name == "質感・効果系":
                self._build_filter_preset_row(panel)

        self._build_transform_group(panel)

        ttk.Button(panel, text="この画像の調整をリセット", command=self._reset_adjustments).pack(
            fill="x", pady=(6, 12)
        )

        ttk.Label(panel, text="リサイズ", font=("", 10, "bold")).pack(anchor="w")
        preset_row = ttk.Frame(panel)
        preset_row.pack(fill="x", pady=4)
        for label, w, h in RESIZE_PRESETS:
            ttk.Button(preset_row, text=label, command=lambda w=w, h=h: self._apply_preset(w, h)).pack(
                side="left", padx=2
            )

        size_row = ttk.Frame(panel)
        size_row.pack(fill="x", pady=4)
        self.width_var = tk.StringVar()
        self.height_var = tk.StringVar()
        w_entry = ttk.Entry(size_row, textvariable=self.width_var, width=7)
        w_entry.pack(side="left")
        ttk.Label(size_row, text="×").pack(side="left", padx=2)
        h_entry = ttk.Entry(size_row, textvariable=self.height_var, width=7)
        h_entry.pack(side="left")
        ttk.Checkbutton(size_row, text="比率固定", variable=self.lock_aspect).pack(side="left", padx=6)
        w_entry.bind("<KeyRelease>", lambda e: self._on_resize_field_change("w"))
        h_entry.bind("<KeyRelease>", lambda e: self._on_resize_field_change("h"))

    def _build_slider_row(self, parent, key, label, lo, hi):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        header = ttk.Frame(row)
        header.pack(fill="x")
        ttk.Label(header, text=label).pack(side="left")

        var = tk.IntVar(value=getattr(self.settings, key))
        entry_var = tk.StringVar(value=str(var.get()))
        self._slider_vars[key] = var
        self._value_entry_vars[key] = entry_var

        value_entry = ttk.Entry(header, textvariable=entry_var, width=5, font=MONO_FONT, justify="right")
        value_entry.pack(side="right")

        def on_change(v, key=key, var=var, entry_var=entry_var):
            iv = int(float(v))
            var.set(iv)
            entry_var.set(str(iv))
            setattr(self.settings, key, iv)
            self._update_preview()

        def commit_entry(_event=None, key=key, lo=lo, hi=hi, var=var, entry_var=entry_var):
            try:
                iv = min(max(int(float(entry_var.get())), lo), hi)
            except ValueError:
                entry_var.set(str(var.get()))
                return
            var.set(iv)
            entry_var.set(str(iv))
            setattr(self.settings, key, iv)
            self._update_preview()

        value_entry.bind("<Return>", commit_entry)
        value_entry.bind("<FocusOut>", commit_entry)

        scale_row = ttk.Frame(row)
        scale_row.pack(fill="x")
        ttk.Label(scale_row, text=str(lo), font=("", 8), foreground="#888").pack(side="left")
        scale = ttk.Scale(scale_row, from_=lo, to=hi, variable=var, command=on_change)
        scale.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Label(scale_row, text=str(hi), font=("", 8), foreground="#888").pack(side="left")

    def _build_group_title(self, parent, group_name):
        """ui-spec.md §1のグループ識別色を、Tkinterではラベル文字色として簡略再現する。"""
        ttk.Label(
            parent, text=f"● {group_name}", font=("", 9, "bold"), foreground=GROUP_COLORS[group_name]
        ).pack(anchor="w", pady=(8, 2))

    # ------------------------------------------------------------------
    # F-07: プリセットフィルター
    # ------------------------------------------------------------------
    def _build_filter_preset_row(self, parent):
        ttk.Label(parent, text="プリセットフィルター").pack(anchor="w", pady=(4, 2))
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 4))
        self.filter_preset_var = tk.StringVar(value=self.settings.filter_preset)
        for value, label in FILTER_PRESETS:
            ttk.Radiobutton(
                row, text=label, value=value, variable=self.filter_preset_var,
                command=self._on_filter_preset_change,
            ).pack(side="left", padx=2)

    def _on_filter_preset_change(self):
        self.settings.filter_preset = self.filter_preset_var.get()
        self._update_preview()

    # ------------------------------------------------------------------
    # F-23: HSL個別調整
    # ------------------------------------------------------------------
    def _build_hsl_row(self, parent):
        ttk.Label(parent, text="HSL個別調整（上級）").pack(anchor="w", pady=(4, 2))
        band_row = ttk.Frame(parent)
        band_row.pack(fill="x", pady=(0, 2))
        self._hsl_band_buttons = []
        for i, color in enumerate(HUE_BAND_COLORS):
            btn = tk.Button(
                band_row, bg=color, width=2, relief="solid" if i == 0 else "flat",
                command=lambda i=i: self._on_hsl_band_select(i),
            )
            btn.pack(side="left", padx=1)
            self._hsl_band_buttons.append(btn)

        self.hsl_s_var = tk.IntVar(value=self.settings.hsl_bands[0].saturation)
        self.hsl_l_var = tk.IntVar(value=self.settings.hsl_bands[0].lightness)

        s_row = ttk.Frame(parent)
        s_row.pack(fill="x", pady=1)
        ttk.Label(s_row, text="この色域の彩度").pack(side="left")
        self.hsl_s_label = ttk.Label(s_row, text=str(self.hsl_s_var.get()), font=MONO_FONT)
        self.hsl_s_label.pack(side="right")
        ttk.Scale(parent, from_=-100, to=100, variable=self.hsl_s_var, command=self._on_hsl_s_change).pack(fill="x")

        l_row = ttk.Frame(parent)
        l_row.pack(fill="x", pady=1)
        ttk.Label(l_row, text="この色域の明度").pack(side="left")
        self.hsl_l_label = ttk.Label(l_row, text=str(self.hsl_l_var.get()), font=MONO_FONT)
        self.hsl_l_label.pack(side="right")
        ttk.Scale(parent, from_=-100, to=100, variable=self.hsl_l_var, command=self._on_hsl_l_change).pack(
            fill="x", pady=(0, 4)
        )

    def _on_hsl_band_select(self, index):
        self._hsl_band_index = index
        for i, btn in enumerate(self._hsl_band_buttons):
            btn.config(relief="solid" if i == index else "flat")
        band = self.settings.hsl_bands[index]
        self.hsl_s_var.set(band.saturation)
        self.hsl_l_var.set(band.lightness)
        self.hsl_s_label.config(text=str(band.saturation))
        self.hsl_l_label.config(text=str(band.lightness))

    def _on_hsl_s_change(self, v):
        value = int(float(v))
        self.hsl_s_var.set(value)
        self.hsl_s_label.config(text=str(value))
        self.settings.hsl_bands[self._hsl_band_index].saturation = value
        self._update_preview()

    def _on_hsl_l_change(self, v):
        value = int(float(v))
        self.hsl_l_var.set(value)
        self.hsl_l_label.config(text=str(value))
        self.settings.hsl_bands[self._hsl_band_index].lightness = value
        self._update_preview()

    # ------------------------------------------------------------------
    # F-21: トーンカーブ（本格エディタ）
    # ------------------------------------------------------------------
    def _build_tone_curve_row(self, parent):
        ttk.Label(parent, text="トーンカーブ（上級）").pack(anchor="w", pady=(4, 2))
        channel_row = ttk.Frame(parent)
        channel_row.pack(fill="x", pady=(0, 2))
        self._curve_channel_buttons = {}
        for key, label in CURVE_CHANNELS:
            btn = ttk.Button(
                channel_row, text=label, width=4,
                command=lambda k=key: self._on_curve_channel_select(k),
            )
            btn.pack(side="left", padx=1)
            self._curve_channel_buttons[key] = btn
        self._update_curve_channel_selection()

        self.curve_canvas = tk.Canvas(
            parent, width=CURVE_W, height=CURVE_H, background="#14161a", highlightthickness=0
        )
        self.curve_canvas.pack(fill="x", pady=(0, 2))
        self.curve_canvas.bind("<Button-1>", self._on_curve_click)
        self.curve_canvas.bind("<B1-Motion>", self._on_curve_drag)
        self.curve_canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "_curve_drag", None))
        self.curve_canvas.bind("<Double-Button-1>", self._on_curve_double_click)

        ttk.Label(
            parent, text="クリックで点を追加・ドラッグで移動・ダブルクリックで削除",
            font=("", 8), foreground="#888",
        ).pack(anchor="w")
        ttk.Button(parent, text="このチャンネルのカーブをリセット", command=self._curve_reset).pack(
            fill="x", pady=(2, 4)
        )
        self._redraw_curve()

    def _curve_points_of(self, channel):
        return getattr(self.settings.tone_curve, channel)

    def _on_curve_channel_select(self, channel):
        self._curve_channel = channel
        self._update_curve_channel_selection()
        self._redraw_curve()

    def _update_curve_channel_selection(self):
        for key, btn in self._curve_channel_buttons.items():
            btn.state(["pressed"] if key == self._curve_channel else ["!pressed"])

    def _curve_to_canvas(self, x, y):
        return x / 255 * CURVE_W, CURVE_H - (y / 255 * CURVE_H)

    def _canvas_to_curve(self, cx, cy):
        x = max(0, min(255, round(cx / CURVE_W * 255)))
        y = max(0, min(255, round((CURVE_H - cy) / CURVE_H * 255)))
        return x, y

    def _find_near_curve_point(self, channel, cx, cy, radius=8):
        pts = self._curve_points_of(channel)
        for i, (x, y) in enumerate(pts):
            px, py = self._curve_to_canvas(x, y)
            if (px - cx) ** 2 + (py - cy) ** 2 <= radius ** 2:
                return i
        return None

    def _on_curve_click(self, event):
        channel = self._curve_channel
        idx = self._find_near_curve_point(channel, event.x, event.y)
        if idx is not None:
            self._curve_drag = (channel, idx)
        else:
            x, y = self._canvas_to_curve(event.x, event.y)
            self._curve_points_of(channel).append((x, y))
            self._curve_drag = (channel, len(self._curve_points_of(channel)) - 1)
            self._redraw_curve()
            self._update_preview()

    def _on_curve_drag(self, event):
        if self._curve_drag is None:
            return
        channel, idx = self._curve_drag
        pts = self._curve_points_of(channel)
        if idx >= len(pts):
            return
        x, y = self._canvas_to_curve(event.x, event.y)
        pts[idx] = (x, y)
        self._redraw_curve()
        self._update_preview()

    def _on_curve_double_click(self, event):
        channel = self._curve_channel
        idx = self._find_near_curve_point(channel, event.x, event.y)
        if idx is not None:
            del self._curve_points_of(channel)[idx]
            self._curve_drag = None
            self._redraw_curve()
            self._update_preview()

    def _curve_reset(self):
        setattr(self.settings.tone_curve, self._curve_channel, [])
        self._redraw_curve()
        self._update_preview()

    def _redraw_curve(self):
        canvas = self.curve_canvas
        canvas.delete("all")
        canvas.create_line(0, CURVE_H, CURVE_W, 0, fill="#3a3e47")

        for key, _label in CURVE_CHANNELS:
            pts = self._curve_points_of(key)
            is_active = key == self._curve_channel
            if not is_active and not pts:
                continue
            lut = build_lut(pts)
            color = CURVE_CHANNEL_COLORS[key]
            coords = []
            for x in range(0, 256, 4):
                cx, cy = self._curve_to_canvas(x, lut[x])
                coords.extend([cx, cy])
            if len(coords) >= 4:
                canvas.create_line(*coords, fill=color, width=2 if is_active else 1)
            if is_active:
                for x, y in pts:
                    cx, cy = self._curve_to_canvas(x, y)
                    canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill=color, outline="")

    # ------------------------------------------------------------------
    # 変形・仕上げ系（新設グループ）: F-13反転 / F-14回転 / F-15トリミング / F-18自動補正
    # ------------------------------------------------------------------
    def _build_transform_group(self, parent):
        self._build_group_title(parent, "変形・仕上げ系")

        ttk.Label(parent, text="反転").pack(anchor="w", pady=(4, 2))
        flip_row = ttk.Frame(parent)
        flip_row.pack(fill="x", pady=(0, 4))
        self.flip_h_var = tk.BooleanVar(value=self.settings.flip_h)
        self.flip_v_var = tk.BooleanVar(value=self.settings.flip_v)
        ttk.Checkbutton(
            flip_row, text="左右反転", variable=self.flip_h_var, command=self._on_flip_change
        ).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(
            flip_row, text="上下反転", variable=self.flip_v_var, command=self._on_flip_change
        ).pack(side="left")

        ttk.Label(parent, text="回転").pack(anchor="w", pady=(4, 2))
        rotate_row = ttk.Frame(parent)
        rotate_row.pack(fill="x", pady=(0, 4))
        ttk.Button(rotate_row, text="↺ 90°", command=lambda: self._on_rotate(-90)).pack(side="left", padx=(0, 4))
        ttk.Button(rotate_row, text="↻ 90°", command=lambda: self._on_rotate(90)).pack(side="left")
        self.rotate_label = ttk.Label(rotate_row, text=f"（現在: {self.settings.rotate}°）", font=MONO_FONT)
        self.rotate_label.pack(side="left", padx=6)

        ttk.Label(parent, text="トリミング").pack(anchor="w", pady=(4, 2))
        crop_row = ttk.Frame(parent)
        crop_row.pack(fill="x", pady=(0, 4))
        ttk.Button(crop_row, text="開始", command=self._crop_start).pack(side="left", padx=(0, 4))
        ttk.Button(crop_row, text="確定", command=self._crop_confirm).pack(side="left", padx=(0, 4))
        ttk.Button(crop_row, text="解除", command=self._crop_clear).pack(side="left")
        ttk.Label(
            parent, text="プレビュー上をドラッグして範囲を指定してください", font=("", 8), foreground="#888"
        ).pack(anchor="w", pady=(0, 4))

        ttk.Label(parent, text="フレーム（縁取り、上級）").pack(anchor="w", pady=(4, 2))
        self._build_slider_row(parent, "frame_width", "太さ", 0, 30)
        frame_swatch_row = ttk.Frame(parent)
        frame_swatch_row.pack(fill="x", pady=(0, 4))
        self._frame_swatch_buttons = []
        for color in FRAME_COLORS:
            btn = tk.Button(
                frame_swatch_row, bg=color, width=2, relief="flat",
                command=lambda c=color: self._on_frame_color_change(c),
            )
            btn.pack(side="left", padx=2)
            self._frame_swatch_buttons.append((color, btn))
        self._update_frame_swatch_selection()

        ttk.Label(parent, text="自動補正（F-18）").pack(anchor="w", pady=(4, 2))
        for mode_key, mode_label in AUTO_CORRECT_MODES:
            ttk.Button(
                parent, text=mode_label, command=lambda m=mode_key: self._apply_auto_correct(m)
            ).pack(fill="x", pady=1)

    def _on_frame_color_change(self, color):
        self.settings.frame_color = color
        self._update_frame_swatch_selection()
        self._update_preview()

    def _update_frame_swatch_selection(self):
        for color, btn in self._frame_swatch_buttons:
            btn.config(relief="solid" if color == self.settings.frame_color else "flat")

    def _on_flip_change(self):
        self.settings.flip_h = self.flip_h_var.get()
        self.settings.flip_v = self.flip_v_var.get()
        self._update_preview()

    def _on_rotate(self, delta):
        self.settings.rotate = (self.settings.rotate + delta) % 360
        self.rotate_label.config(text=f"（現在: {self.settings.rotate}°）")
        self._update_preview()

    def _apply_auto_correct(self, mode_key):
        if not self.image_paths:
            return
        path = self.image_paths[self.current_index]
        with Image.open(path) as img:
            source = img.convert("RGB")

        if mode_key == "vivid":
            result = auto_correct.vivid_preset()
        else:
            result = getattr(auto_correct, mode_key)(source)

        for key in ("brightness", "contrast", "saturate", "vibrance", "warmth", "clarity"):
            value = getattr(result, key)
            default_value = getattr(AdjustmentSettings(), key)
            if value != default_value:
                setattr(self.settings, key, value)
                if key in self._slider_vars:
                    self._slider_vars[key].set(value)
                    self._value_entry_vars[key].set(str(value))

        self._update_preview()
        label = dict(AUTO_CORRECT_MODES)[mode_key]
        self.status_label.config(text=f"自動補正「{label}」を適用しました")

    # ------------------------------------------------------------------
    # データ読み込み・表示更新
    # ------------------------------------------------------------------
    def _choose_folder(self):
        chosen = filedialog.askdirectory(initialdir=str(self.source_dir))
        if chosen:
            self.load_folder(Path(chosen))

    def load_folder(self, folder: Path):
        self.source_dir = folder
        self.folder_label.config(text=str(folder))
        self.image_paths = sorted(
            p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in TARGET_EXTENSIONS
        ) if folder.exists() else []

        for child in self.thumb_frame.winfo_children():
            child.destroy()
        self._thumb_photo_refs.clear()

        for i, path in enumerate(self.image_paths):
            self._add_thumb(path, i)

        if self.image_paths:
            self.select_image(0)
        else:
            self.status_label.config(text="対象フォルダに画像が見つかりません")

    def _add_thumb(self, path: Path, index: int):
        try:
            with Image.open(path) as img:
                thumb = img.copy()
                thumb.thumbnail(THUMB_SIZE)
                photo = ImageTk.PhotoImage(thumb)
        except Exception:
            return
        self._thumb_photo_refs.append(photo)

        btn = ttk.Frame(self.thumb_frame, relief="flat", borderwidth=2)
        btn.pack(fill="x", pady=2)
        lbl_img = ttk.Label(btn, image=photo)
        lbl_img.pack()
        lbl_text = ttk.Label(btn, text=path.name, font=("", 7))
        lbl_text.pack()
        for widget in (btn, lbl_img, lbl_text):
            widget.bind("<Button-1>", lambda e, i=index: self.select_image(i))

    def select_image(self, index: int):
        self.current_index = index
        self.preview_name_label.config(text=self.image_paths[index].name)
        self._update_preview()

    def _update_preview(self, *_):
        if not self.image_paths:
            return
        path = self.image_paths[self.current_index]
        with Image.open(path) as img:
            orig = img.convert("RGB")

        area_w, area_h = self._preview_area
        ow, oh = orig.size
        self._preview_orig_size = (ow, oh)
        scale = min(area_w / ow, area_h / oh, 1.0)  # 画面に収まるサイズ（ネイティブ超の拡大はしない）

        target_w = max(20, round(ow * scale))
        target_h = max(20, round(oh * scale))
        longest = max(target_w, target_h)
        if longest > 4000:  # 極端な拡大でメモリを使いすぎないための上限
            cap = 4000 / longest
            target_w = max(20, round(target_w * cap))
            target_h = max(20, round(target_h * cap))

        resized = orig.resize((target_w, target_h), Image.LANCZOS)
        processed = apply_adjustments(resized, self.settings)

        if self._before_after.get():
            # F-19: 加工前（構図系＝反転/回転/トリミング/リサイズは揃えたまま、色・質感の調整だけ外す）と
            # 加工後を左右に並べる。structural transformを揃えるのは、サイズを一致させて
            # 単純に左右合成できるようにするため。
            baseline = AdjustmentSettings(
                flip_h=self.settings.flip_h, flip_v=self.settings.flip_v, rotate=self.settings.rotate,
                crop_rect=self.settings.crop_rect,
                resize_w=self.settings.resize_w, resize_h=self.settings.resize_h,
            )
            before_img = apply_adjustments(resized, baseline)
            display_img = processed.copy()
            half = display_img.width // 2
            if half > 0 and before_img.size == display_img.size:
                display_img.paste(before_img.crop((0, 0, half, before_img.height)), (0, 0))
        else:
            display_img = processed

        # プレビューは常にプレビュー欄に収まるサイズで表示する。resize_w/resize_h（リサイズ）が
        # プレビュー欄より大きい値のときも、実際の出力画素数で描画すると欄からはみ出してしまうため、
        # 表示専用にここでさらに縮小する（settings・出力結果には影響しない）。
        dw, dh = display_img.size
        if dw > area_w or dh > area_h:
            disp_fit = min(area_w / dw, area_h / dh)
            display_img = display_img.resize(
                (max(1, round(dw * disp_fit)), max(1, round(dh * disp_fit))), Image.LANCZOS
            )

        self._preview_photo = ImageTk.PhotoImage(display_img)

        canvas = self.preview_canvas
        canvas.delete("all")
        cw = canvas.winfo_width() or area_w
        ch = canvas.winfo_height() or area_h
        disp_w, disp_h = display_img.size
        x = max((cw - disp_w) // 2, 0)
        y = max((ch - disp_h) // 2, 0)
        canvas.create_image(x, y, anchor="nw", image=self._preview_photo)
        if self._before_after.get():
            canvas.create_line(x + disp_w // 2, y, x + disp_w // 2, y + disp_h, fill="#e0913a", width=2)
        canvas.configure(scrollregion=(0, 0, max(cw, disp_w), max(ch, disp_h)))
        self._preview_img_box = (x, y, disp_w, disp_h)

    def _reset_adjustments(self):
        defaults = AdjustmentSettings(resize_w=self.settings.resize_w, resize_h=self.settings.resize_h)
        self.settings = defaults
        for key, var in self._slider_vars.items():
            var.set(getattr(self.settings, key))
            self._value_entry_vars[key].set(str(getattr(self.settings, key)))
        self.filter_preset_var.set(self.settings.filter_preset)
        self.flip_h_var.set(self.settings.flip_h)
        self.flip_v_var.set(self.settings.flip_v)
        self.rotate_label.config(text=f"（現在: {self.settings.rotate}°）")
        self._update_frame_swatch_selection()
        self._on_hsl_band_select(self._hsl_band_index)
        self._curve_channel = "rgb"
        self._update_curve_channel_selection()
        self._redraw_curve()
        self.super_res_var.set(self.settings.super_res_enabled)
        self._crop_clear()
        self._update_preview()

    # ------------------------------------------------------------------
    # リサイズ
    # ------------------------------------------------------------------
    def _apply_preset(self, w, h):
        self.settings.resize_w = w
        self.settings.resize_h = h
        self.width_var.set(str(w) if w else "")
        self.height_var.set(str(h) if h else "")
        self._update_preview()

    def _on_resize_field_change(self, changed: str):
        if not self.image_paths:
            return
        try:
            with Image.open(self.image_paths[self.current_index]) as img:
                ratio = img.width / img.height
        except Exception:
            ratio = 16 / 9

        if changed == "w" and self.width_var.get().isdigit():
            w = int(self.width_var.get())
            self.settings.resize_w = w
            if self.lock_aspect.get():
                h = round(w / ratio)
                self.height_var.set(str(h))
                self.settings.resize_h = h
        elif changed == "h" and self.height_var.get().isdigit():
            h = int(self.height_var.get())
            self.settings.resize_h = h
            if self.lock_aspect.get():
                w = round(h * ratio)
                self.width_var.set(str(w))
                self.settings.resize_w = w
        self._update_preview()

    # ------------------------------------------------------------------
    # F-03: 一括適用 / F-06: 壁紙設定
    # ------------------------------------------------------------------
    def _apply_all(self):
        if not self.image_paths:
            messagebox.showinfo("壁紙加工ツール", "対象フォルダに画像がありません")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = self.source_dir.parent / f"{self.source_dir.name}_edited_{timestamp}"

        try:
            rename_start = int(self.rename_start.get())
            rename_digits = int(self.rename_digits.get())
        except ValueError:
            rename_start, rename_digits = 1, 3

        self.status_label.config(text="処理中…")
        self.progress.pack(side="right")
        self.progress.start(12)

        def worker():
            result = process_folder(
                self.source_dir, output_dir, self.settings,
                output_format=self.output_format.get(),
                rename_prefix=self.rename_prefix.get(),
                rename_start=rename_start,
                rename_digits=rename_digits,
            )
            self.root.after(0, lambda: self._on_apply_all_done(result))

        threading.Thread(target=worker, daemon=True).start()

    def _on_apply_all_done(self, result):
        self.progress.stop()
        self.progress.pack_forget()
        save_settings(self.settings)
        self._last_output_dir = result.output_dir  # F-10: スライドショーの対象フォルダとして使う
        msg = f"成功 {result.succeeded}/{result.total} 件、保存先: {result.output_dir}"
        if result.failed:
            msg += f"（失敗: {len(result.failed)}件）"
        self.status_label.config(text=msg)
        messagebox.showinfo("一括適用が完了しました", msg)

    def _set_wallpaper(self):
        if not self.image_paths:
            return
        path = self.image_paths[self.current_index]
        if not messagebox.askyesno(
            "デスクトップ壁紙に設定",
            f"「{path.name}」を、現在の調整内容で加工してデスクトップ壁紙に設定します。よろしいですか？",
        ):
            return

        try:
            with Image.open(path) as img:
                processed = apply_adjustments(img, self.settings)
            tmp_path = self.source_dir.parent / "_wallpaper_editor_tmp.jpg"
            processed.convert("RGB").save(tmp_path, "JPEG", quality=95)
            set_desktop_wallpaper(tmp_path.resolve())
            save_settings(self.settings)
            messagebox.showinfo("壁紙加工ツール", "デスクトップ壁紙を設定しました")
        except WallpaperError as e:
            messagebox.showerror("壁紙加工ツール", str(e))

    # ------------------------------------------------------------------
    # F-10: 壁紙のスライドショー化（Windows標準のスライドショー機能を設定する）
    # ------------------------------------------------------------------
    def _init_slideshow_state(self):
        """起動時にWindows側の対応状況・現在の状態を確認し、UIに反映する
        （docs/03-design/screen-flow.md「起動時の処理フロー（F-10分の追記）」参照）。"""
        if not is_slideshow_supported():
            self.slideshow_combo.config(state="disabled")
            self.slideshow_toggle_btn.config(state="disabled")
            self.slideshow_hint_label.config(
                text="このWindowsのバージョンでは使用できません"
            )
            return
        try:
            status = get_slideshow_status()
        except SlideshowError as e:
            self.slideshow_hint_label.config(text=f"状態取得に失敗しました: {e}")
            return
        if status.enabled and status.interval_minutes is not None:
            self._slideshow_on = True
            self.slideshow_toggle_btn.config(text="スライドショー ON")
            label = self._label_for_minutes(status.interval_minutes)
            if label is not None:
                self.slideshow_interval_label.set(label)

    def _selected_slideshow_minutes(self) -> int:
        label = self.slideshow_interval_label.get()
        for opt_label, minutes in SLIDESHOW_INTERVAL_OPTIONS:
            if opt_label == label:
                return minutes
        return 30

    def _label_for_minutes(self, minutes: int) -> str | None:
        for opt_label, opt_minutes in SLIDESHOW_INTERVAL_OPTIONS:
            if opt_minutes == minutes:
                return opt_label
        return None

    def _toggle_slideshow(self):
        if not self._slideshow_on:
            if self._last_output_dir is None:
                messagebox.showinfo(
                    "壁紙加工ツール",
                    "先に「この設定を対象フォルダの全画像に一括適用」を実行してください",
                )
                return
            try:
                enable_slideshow(self._last_output_dir, self._selected_slideshow_minutes())
            except SlideshowError as e:
                messagebox.showerror("壁紙加工ツール", str(e))
                return
            self._slideshow_on = True
            self.slideshow_toggle_btn.config(text="スライドショー ON")
            self.status_label.config(text=f"スライドショーをONにしました（{self._last_output_dir}）")
        else:
            fallback = (
                self.image_paths[self.current_index]
                if self.image_paths
                else self.source_dir
            )
            try:
                disable_slideshow(fallback)
            except SlideshowError as e:
                messagebox.showerror("壁紙加工ツール", str(e))
                return
            self._slideshow_on = False
            self.slideshow_toggle_btn.config(text="スライドショー OFF")
            self.status_label.config(text="スライドショーをOFFにしました")

    def _on_slideshow_interval_change(self, _event=None):
        if not self._slideshow_on or self._last_output_dir is None:
            return
        try:
            enable_slideshow(self._last_output_dir, self._selected_slideshow_minutes())
        except SlideshowError as e:
            messagebox.showerror("壁紙加工ツール", str(e))


def main():
    root = tk.Tk()
    WallpaperEditorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
