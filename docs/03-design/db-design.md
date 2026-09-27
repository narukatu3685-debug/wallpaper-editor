# DB設計

## 結論: DBは使わない（変更なし）

このアプリは「ローカルフォルダの画像を読み込み→加工→別フォルダに保存／壁紙設定」を行う一回完結ツールであり、複数ユーザーや履歴管理・検索機能を持たない。機能数はF-07〜F-28まで増えたが、性質は変わらないためDB（SQLite等）は導入しない。

対応機能: なし（すべてDBを必要としない）

## 唯一の永続化: 直近の調整値（利便性のための任意機能）

次回起動時に前回の調整値を復元できると便利なため、DBではなく単純なJSONファイルに保存する（方針は変更なし）。

- 保存先: `%APPDATA%\WallpaperEditor\last_settings.json`
- 対応機能: F-01, F-07, F-09, F-11〜F-27（利便性向上のための付加仕様）
- **2026-08-30更新**: F-13〜F-28追加に伴いスキーマを拡張。ハイライト/シャドウ（`highlights`/`shadows`）はトーンカーブに統合されたため削除（RV-05）。

```json
{
  "saturate": 100,
  "brightness": 100,
  "contrast": 100,
  "hue": 0,
  "sharpen": 0,
  "warmth": 0,
  "vignette": 0,
  "vibrance": 0,
  "clarity": 0,
  "denoise": 0,
  "blur": 0,
  "filter_preset": "none",

  "flip_h": false,
  "flip_v": false,
  "rotate": 0,
  "crop_rect": null,
  "frame_width": 0,
  "frame_color": "#e0913a",

  "hsl_bands": [
    { "hue_deg": 0,   "saturation": 0, "lightness": 0 },
    { "hue_deg": 45,  "saturation": 0, "lightness": 0 },
    { "hue_deg": 90,  "saturation": 0, "lightness": 0 },
    { "hue_deg": 135, "saturation": 0, "lightness": 0 },
    { "hue_deg": 180, "saturation": 0, "lightness": 0 },
    { "hue_deg": 225, "saturation": 0, "lightness": 0 },
    { "hue_deg": 270, "saturation": 0, "lightness": 0 },
    { "hue_deg": 315, "saturation": 0, "lightness": 0 }
  ],

  "tone_curve": {
    "rgb": [],
    "r": [],
    "g": [],
    "b": []
  },

  "resize_w": null,
  "resize_h": null,
  "lock_aspect": true,

  "output_format": "jpg",
  "output_quality": 92,
  "rename_prefix": "wallpaper_",
  "rename_start": 1,
  "rename_digits": 3,
  "super_res_enabled": false,

  "slideshow_interval_minutes": 30
}
```

- `slideshow_interval_minutes`: F-10（スライドショー）の間隔プルダウンの最後に選んだ値（分）。次回起動時にプルダウンの初期値として復元する。**ON/OFFの状態そのものは保存しない**（実際にONかどうかはWindows側の状態が正であるため、起動時に`wallpaper_slideshow.get_status()`で問い合わせてUIに反映する。2026-09-01、F-10・US-15追加）。
  - **実装時の変更**: 実装では、既存の`output_format`/`rename_*`と同じ理由（「画像ごとの調整値」ではなく「バッチ実行時の設定」であり`AdjustmentSettings`の性質と異なるため、`impl-notes.md`「設計からの変更点」参照）により、`last_settings.json`（`AdjustmentSettings`）には含めず、GUI側のセッション内変数（Tkinter変数、既定値: 30分）として実装した。次回起動時は既定値に戻る（ON/OFFの状態はWindows側から復元するが、間隔の記憶は次回起動まで持ち越さない）。

- `crop_rect`: `null`（クロップなし）または `[x0, y0, x1, y1]`（元画像に対する0.0〜1.0の相対座標）。相対値にする理由は、プレビュー用サンプル画像と一括処理対象の実画像でピクセルサイズが異なるため（`api-spec.md` §crop参照）。
- `hsl_bands`: 8つの色相帯（赤・橙・黄・緑・青緑・青・紫・マゼンタ、45度刻み）ごとの彩度・明度の補正値。`hue_deg` は帯の中心角度で固定し、UIからは変更しない。
- `tone_curve.*`: 各チャンネルのカーブ制御点。`[[x, y], ...]`（x, yとも0〜255）のリストで、空配列は「そのチャンネルは無調整（対角線のまま）」を意味する。
- 読み込み失敗時（ファイルが無い・壊れている・スキーマが古い）は、`ui-spec.md` に定義された初期値にフォールバックする。キー単位で存在しないものはデフォルト値を補う（後方互換）。
- 保存タイミングは変更なし（アプリ終了時、または「一括適用」実行時）。
