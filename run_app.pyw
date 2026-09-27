"""デスクトップアイコンからの起動用エントリーポイント（コンソール非表示）。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from wallpaper_editor.gui import main  # noqa: E402

if __name__ == "__main__":
    main()
