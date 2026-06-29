# -*- coding: utf-8 -*-
"""
CardBox v13

カード型の情報を、タイトル・タグ・説明・メディア付きで管理するローカルGUIツール。
PySide6 + SQLite で動作します。

必要環境:
    pip install PySide6 opencv-python

保存場所:
    スクリプトと同じフォルダに cardbox.db と assets/ を作成します。prompt_organizer.db がある場合は初回起動時に cardbox.db へコピー移行します。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import tempfile
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Callable, Iterable, Optional, Sequence

try:
    from PySide6.QtCore import QEvent, QLockFile, QMimeData, QObject, QPoint, QRect, QSize, Qt, QThread, QTimer, QUrl, Signal
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtGui import QAction, QActionGroup, QBrush, QColor, QCursor, QDrag, QFont, QGuiApplication, QIcon, QImage, QKeySequence, QPainter, QPixmap, QPixmapCache
    from PySide6.QtWidgets import (
        QApplication,
        QAbstractItemView,
        QCheckBox,
        QColorDialog,
        QComboBox,
        QDialog,
        QFileDialog,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLayout,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QProgressDialog,
        QScrollArea,
        QSizePolicy,
        QSplitter,
        QSpinBox,
        QStatusBar,
        QStyle,
        QStyledItemDelegate,
        QStyleOptionViewItem,
        QSystemTrayIcon,
        QTabWidget,
        QTextEdit,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except Exception as exc:  # pragma: no cover - 実行環境向けメッセージ
    print("PySide6 が見つかりません。以下を実行してください:")
    print("pip install PySide6")
    print(f"詳細: {exc}")
    sys.exit(1)


APP_NAME = "CardBox"
APP_VERSION = "v1.1.1"
APP_AUTHOR = "MF235"
APP_CONTACT_X = "https://x.com/MF235XBR"
APP_REPOSITORY = "https://github.com/mf235/cardbox"
APP_USER_MODEL_ID = "chappy.cardbox"
APP_IPC_SERVER_NAME = "chappy.cardbox.ipc"
GLOBAL_HOTKEY_ID = 0x4131
GLOBAL_HOTKEY_SETTING_KEY = "global_hotkey_shift_alt_a"
STARTUP_ARG = "--startup"
STARTUP_SHORTCUT_NAME = "CardBox.lnk"
WINDOW_ICON_RELATIVE = ("resources", "icons", "window.png")
EXE_ICON_RELATIVE = ("resources", "icons", "app.ico")
DB_FILENAME = "cardbox.db"
LEGACY_DB_FILENAME = "prompt_organizer.db"
INTERNAL_MATERIAL_DRAG_MIME = "application/x-cardbox-material-drag"
BACKUP_DIR_NAME = "_backup"
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".ico", ".svg", ".tif", ".tiff", ".tga"}
SUPPORTED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
SUPPORTED_MEDIA_EXTS = SUPPORTED_IMAGE_EXTS | SUPPORTED_VIDEO_EXTS
ARCHIVE_EXTS = {".zip", ".7z", ".rar", ".tar", ".gz"}
AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
TEXT_EXTS = {".txt", ".md", ".json", ".csv", ".yaml", ".yml", ".xml", ".html", ".css", ".js", ".py"}
DOCUMENT_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}
CODE_EXTS = {".py", ".js", ".ts", ".html", ".css", ".cpp", ".c", ".h", ".cs", ".java", ".rs", ".go"}


def format_extension_list(exts: set[str]) -> str:
    return " ".join(sorted(exts))


def normalize_prompt_sort_mode(value: str) -> str:
    value = str(value or "").strip()
    if value in PROMPT_SORT_LABELS:
        return value
    return DEFAULT_PROMPT_SORT_MODE


def supported_media_formats_text() -> str:
    return (
        "登録できるファイル\n"
        "  基本的にすべてのファイルをメディアとして登録できます。\n"
        "  未分類のファイルはカードに添付し、OSの関連付けで開きます。\n"
        "\n"
        "画像として扱う形式\n"
        f"  {format_extension_list(SUPPORTED_IMAGE_EXTS)}\n"
        "  サムネイル作成、画像ビュアー表示の対象です。\n"
        "\n"
        "動画として扱う形式\n"
        f"  {format_extension_list(SUPPORTED_VIDEO_EXTS)}\n"
        "  動画コピー登録、またはフレーム画像登録の対象です。\n"
        "\n"
        "その他の主な分類\n"
        f"  音声: {format_extension_list(AUDIO_EXTS)}\n"
        f"  圧縮: {format_extension_list(ARCHIVE_EXTS)}\n"
        f"  文書: {format_extension_list(DOCUMENT_EXTS)}\n"
        f"  テキスト: {format_extension_list(TEXT_EXTS)}\n"
        f"  コード: {format_extension_list(CODE_EXTS)}\n"
        "\n"
        "補足\n"
        "  上記以外の拡張子も登録できます。\n"
        "  ただし、サムネイルや専用プレビューは形式により作成できない場合があります。"
    )


IMAGE_VIEWER_RESIZE_METHODS = [
    ("nearest", "Nearest（軽量）"),
    ("smooth", "Smooth（標準）"),
    ("bicubic", "Bicubic（高品質）"),
    ("lanczos", "Lanczos（最高品質）"),
]
IMAGE_VIEWER_RESIZE_METHOD_KEYS = {key for key, _label in IMAGE_VIEWER_RESIZE_METHODS}
DEFAULT_IMAGE_VIEWER_RESIZE_METHOD = "bicubic"
PROMPT_SORT_UPDATED = "updated_desc"
PROMPT_SORT_TITLE = "title_asc"
DEFAULT_PROMPT_SORT_MODE = PROMPT_SORT_UPDATED
PROMPT_SORT_LABELS = {
    PROMPT_SORT_UPDATED: "更新日時",
    PROMPT_SORT_TITLE: "タイトル",
}
IMAGE_VIEWER_TILE_GAP = 8
IMAGE_VIEWER_TILE_MIN_CLIENT_WIDTH = 80
IMAGE_VIEWER_TILE_MIN_CLIENT_HEIGHT = 60
LEFT_TAG_FILTER_DEFAULT_HEIGHT = 260
LEFT_TAG_FILTER_MIN_HEIGHT = 120
LEFT_PINNED_PROMPT_MIN_HEIGHT = 0
LEFT_PROMPT_LIST_MIN_HEIGHT = 120

DEFAULT_MATERIAL_LABEL_COLORS = {
    1: ("#ffffff", "#d32f2f"),
    2: ("#ffffff", "#f57c00"),
    3: ("#222222", "#fbc02d"),
    4: ("#ffffff", "#388e3c"),
    5: ("#ffffff", "#1976d2"),
    6: ("#ffffff", "#7b1fa2"),
    7: ("#ffffff", "#5d4037"),
    8: ("#222222", "#cfd8dc"),
    9: ("#ffffff", "#455a64"),
}


DEFAULT_CATEGORY_COLORS = {
    "メディア": "#4f8cff",
    "用途": "#b26cff",
    "状態": "#ff9f43",
    "プロジェクト": "#35b779",
    "AI": "#00a6b8",
    "custom": "#777777",
}


DEFAULT_TAG_CATEGORIES = {
    "メディア": ["テキスト", "動画", "画像", "音楽"],
    "用途": ["README", "えっち", "アニメ", "カメラ", "キャラ", "セリフ", "ポーズ", "ロゴ", "体型", "動画モーション", "構図", "衣装", "表情", "質感"],
    "プロジェクト": ["ちゃっぴー"],
    "AI": ["ChatGPT", "Gemini", "Grok", "Midjourney", "Stable Diffusion", "Flux", "Suno", "Kling", "Runway", "Google Flow"],
}


DEFAULT_TAG_PRESETS = {
    "画像生成基本": ["画像"],
    "動画生成基本": ["動画", "動画モーション", "カメラ"],
    "ポーズ研究": ["画像", "ポーズ", "構図"],
    "キャラ設定": ["画像", "キャラ", "表情"],
    "ちゃっぴー": ["ちゃっぴー", "キャラ"],
}

META_OPTION_FIELDS = ("engine", "model", "project")
META_OPTION_LABELS = {
    "engine": "生成AI",
    "model": "モデル",
    "project": "プロジェクト",
}
META_OPTION_FIELDS_BY_LABEL = {value: key for key, value in META_OPTION_LABELS.items()}

DEFAULT_WORKSPACE_NAME = "メディア管理"
DEFAULT_WORKSPACE_SETTINGS = {
    "show_card_thumbnail": 1,
    "select_field_1_label": "使用AI",
    "select_field_2_label": "モデル",
    "select_field_3_label": "プロジェクト",
    "text_field_1_label": "プロンプト",
    "text_field_2_label": "ネガティブ / 補助プロンプト",
    "text_field_3_label": "説明 / メモ",
}
WORKSPACE_LABEL_FIELDS = (
    "select_field_1_label",
    "select_field_2_label",
    "select_field_3_label",
    "text_field_1_label",
    "text_field_2_label",
    "text_field_3_label",
)


@dataclass
class PromptRow:
    id: int
    workspace_id: int
    title: str
    prompt: str
    negative_prompt: str
    description: str
    engine: str
    model: str
    project: str
    rating: int
    favorite: int
    pinned: int
    tags: list[str]
    cover_thumb: str
    updated_at: str




@dataclass
class WorkspaceDeletePlan:
    workspace_id: int
    workspace_name: str
    fallback_workspace_id: int
    prompt_count: int
    tag_count: int
    tag_preset_count: int
    media_count: int
    asset_target_paths: list[Path]
    asset_file_count: int
    asset_total_bytes: int


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                show_card_thumbnail INTEGER NOT NULL DEFAULT 1,
                select_field_1_label TEXT NOT NULL DEFAULT '使用AI',
                select_field_2_label TEXT NOT NULL DEFAULT 'モデル',
                select_field_3_label TEXT NOT NULL DEFAULT 'プロジェクト',
                text_field_1_label TEXT NOT NULL DEFAULT 'プロンプト',
                text_field_2_label TEXT NOT NULL DEFAULT 'ネガティブ / 補助プロンプト',
                text_field_3_label TEXT NOT NULL DEFAULT '説明 / メモ',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.ensure_default_workspace()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL DEFAULT 1,
                title TEXT NOT NULL DEFAULT '',
                prompt TEXT NOT NULL DEFAULT '',
                negative_prompt TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                engine TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                project TEXT NOT NULL DEFAULT '',
                rating INTEGER NOT NULL DEFAULT 0,
                favorite INTEGER NOT NULL DEFAULT 0,
                pinned INTEGER NOT NULL DEFAULT 0,
                parent_prompt_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(parent_prompt_id) REFERENCES prompts(id) ON DELETE SET NULL
            )
            """
        )
        self.ensure_column("prompts", "pinned", "INTEGER NOT NULL DEFAULT 0")
        self.ensure_column("prompts", "workspace_id", "INTEGER NOT NULL DEFAULT 1")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tag_categories (
                name TEXT PRIMARY KEY,
                color TEXT NOT NULL DEFAULT '#777777'
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL DEFAULT 1,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'custom',
                color TEXT NOT NULL DEFAULT '',
                UNIQUE(workspace_id, name)
            )
            """
        )
        self.ensure_tags_workspace_schema()
        self.ensure_column("tags", "visible", "INTEGER NOT NULL DEFAULT 1")
        self.ensure_column("tag_categories", "workspace_id", "INTEGER NOT NULL DEFAULT 1")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS prompt_tags (
                prompt_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY(prompt_id, tag_id),
                FOREIGN KEY(prompt_id) REFERENCES prompts(id) ON DELETE CASCADE,
                FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                thumbnail_path TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                caption TEXT NOT NULL DEFAULT '',
                is_cover INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(prompt_id) REFERENCES prompts(id) ON DELETE CASCADE
            )
            """
        )
        self.ensure_column("images", "media_type", "TEXT NOT NULL DEFAULT 'image'")
        self.ensure_column("images", "original_name", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("images", "label_id", "INTEGER NOT NULL DEFAULT 0")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tag_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL DEFAULT 1,
                name TEXT NOT NULL UNIQUE,
                tags_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS meta_options (
                field TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(field, value)
            )
            """
        )
        self.ensure_tag_presets_workspace_schema()
        self.ensure_column("tag_presets", "workspace_id", "INTEGER NOT NULL DEFAULT 1")
        self.ensure_prompt_workspace_ids()
        self.ensure_tag_workspace_ids()
        self.conn.commit()
        self.seed_defaults_if_needed()
        self.seed_meta_options_from_prompts_if_needed()

    def ensure_default_workspace(self) -> int:
        now = self.now()
        row = self.conn.execute("SELECT id FROM workspaces ORDER BY id ASC LIMIT 1").fetchone()
        if row:
            return int(row["id"])
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO workspaces(
                name, show_card_thumbnail,
                select_field_1_label, select_field_2_label, select_field_3_label,
                text_field_1_label, text_field_2_label, text_field_3_label,
                sort_order, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                DEFAULT_WORKSPACE_NAME,
                int(DEFAULT_WORKSPACE_SETTINGS["show_card_thumbnail"]),
                DEFAULT_WORKSPACE_SETTINGS["select_field_1_label"],
                DEFAULT_WORKSPACE_SETTINGS["select_field_2_label"],
                DEFAULT_WORKSPACE_SETTINGS["select_field_3_label"],
                DEFAULT_WORKSPACE_SETTINGS["text_field_1_label"],
                DEFAULT_WORKSPACE_SETTINGS["text_field_2_label"],
                DEFAULT_WORKSPACE_SETTINGS["text_field_3_label"],
                0,
                now,
                now,
            ),
        )
        return int(cur.lastrowid)

    def ensure_prompt_workspace_ids(self) -> None:
        default_id = self.ensure_default_workspace()
        self.conn.execute("UPDATE prompts SET workspace_id = ? WHERE workspace_id IS NULL OR workspace_id <= 0", (default_id,))

    def ensure_tag_workspace_ids(self) -> None:
        default_id = self.ensure_default_workspace()
        for table in ("tags", "tag_presets"):
            try:
                self.conn.execute(f"UPDATE {table} SET workspace_id = ? WHERE workspace_id IS NULL OR workspace_id <= 0", (default_id,))
            except sqlite3.OperationalError:
                pass

    def ensure_tags_workspace_schema(self) -> None:
        columns = {str(row["name"]) for row in self.conn.execute("PRAGMA table_info(tags)").fetchall()}
        if "workspace_id" in columns:
            return
        cur = self.conn.cursor()
        cur.execute("PRAGMA foreign_keys = OFF")
        try:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tags_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id INTEGER NOT NULL DEFAULT 1,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'custom',
                    color TEXT NOT NULL DEFAULT '',
                    visible INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(workspace_id, name)
                )
                """
            )
            existing_columns = columns
            visible_expr = "visible" if "visible" in existing_columns else "1"
            cur.execute(
                f"""
                INSERT INTO tags_new(id, workspace_id, name, category, color, visible)
                SELECT id, 1, name, category, color, {visible_expr}
                FROM tags
                ORDER BY id ASC
                """
            )
            cur.execute("DROP TABLE tags")
            cur.execute("ALTER TABLE tags_new RENAME TO tags")
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.execute("PRAGMA foreign_keys = ON")

    def ensure_tag_presets_workspace_schema(self) -> None:
        columns = {str(row["name"]) for row in self.conn.execute("PRAGMA table_info(tag_presets)").fetchall()}
        if "workspace_id" in columns:
            return
        cur = self.conn.cursor()
        cur.execute("PRAGMA foreign_keys = OFF")
        try:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tag_presets_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id INTEGER NOT NULL DEFAULT 1,
                    name TEXT NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(workspace_id, name)
                )
                """
            )
            cur.execute(
                """
                INSERT INTO tag_presets_new(id, workspace_id, name, tags_json, created_at, updated_at)
                SELECT id, 1, name, tags_json, created_at, updated_at
                FROM tag_presets
                ORDER BY id ASC
                """
            )
            cur.execute("DROP TABLE tag_presets")
            cur.execute("ALTER TABLE tag_presets_new RENAME TO tag_presets")
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.execute("PRAGMA foreign_keys = ON")

    def list_workspaces(self) -> list[sqlite3.Row]:
        self.ensure_default_workspace()
        return self.conn.execute(
            "SELECT * FROM workspaces ORDER BY sort_order ASC, id ASC"
        ).fetchall()

    def get_workspace(self, workspace_id: int | None) -> sqlite3.Row | None:
        if workspace_id is None:
            workspace_id = self.current_workspace_id()
        return self.conn.execute("SELECT * FROM workspaces WHERE id = ?", (int(workspace_id),)).fetchone()

    def current_workspace_id(self) -> int:
        default_id = self.ensure_default_workspace()
        raw = self.get_setting("current_workspace_id", str(default_id))
        workspace_id = safe_int(raw, default_id)
        row = self.conn.execute("SELECT id FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
        if not row:
            workspace_id = default_id
            self.set_setting("current_workspace_id", str(workspace_id))
        return int(workspace_id)

    def set_current_workspace_id(self, workspace_id: int) -> None:
        row = self.get_workspace(int(workspace_id))
        if row is None:
            raise ValueError("workspace not found")
        self.set_setting("current_workspace_id", str(int(workspace_id)))

    def create_workspace(self, name: str | None = None) -> int:
        base_name = normalize_workspace_name(name or "新規ワークスペース") or "新規ワークスペース"
        existing = {str(row["name"]).casefold() for row in self.list_workspaces()}
        name_value = base_name
        index = 2
        while name_value.casefold() in existing:
            name_value = f"{base_name} {index}"
            index += 1
        max_sort_row = self.conn.execute("SELECT COALESCE(MAX(sort_order), -1) AS max_sort FROM workspaces").fetchone()
        sort_order = int(max_sort_row["max_sort"]) + 1 if max_sort_row else 0
        now = self.now()
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO workspaces(
                name, show_card_thumbnail,
                select_field_1_label, select_field_2_label, select_field_3_label,
                text_field_1_label, text_field_2_label, text_field_3_label,
                sort_order, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name_value,
                int(DEFAULT_WORKSPACE_SETTINGS["show_card_thumbnail"]),
                DEFAULT_WORKSPACE_SETTINGS["select_field_1_label"],
                DEFAULT_WORKSPACE_SETTINGS["select_field_2_label"],
                DEFAULT_WORKSPACE_SETTINGS["select_field_3_label"],
                DEFAULT_WORKSPACE_SETTINGS["text_field_1_label"],
                DEFAULT_WORKSPACE_SETTINGS["text_field_2_label"],
                DEFAULT_WORKSPACE_SETTINGS["text_field_3_label"],
                sort_order,
                now,
                now,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_workspace(self, workspace_id: int, data: dict) -> None:
        name = normalize_workspace_name(str(data.get("name", "") or ""))
        if not name:
            raise ValueError("ワークスペース名が空です。")
        show_thumb = 1 if bool(data.get("show_card_thumbnail", True)) else 0
        labels = []
        for field in WORKSPACE_LABEL_FIELDS:
            value = str(data.get(field, "") or "").strip()
            if not value:
                value = str(DEFAULT_WORKSPACE_SETTINGS[field])
            labels.append(value)
        self.conn.execute(
            """
            UPDATE workspaces
            SET name = ?, show_card_thumbnail = ?,
                select_field_1_label = ?, select_field_2_label = ?, select_field_3_label = ?,
                text_field_1_label = ?, text_field_2_label = ?, text_field_3_label = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (name, show_thumb, *labels, self.now(), int(workspace_id)),
        )
        self.conn.commit()

    def seed_defaults_if_needed(self) -> None:
        """Seed default tags only for a brand-new database.

        Older versions called seed_defaults() on every startup. That meant
        a user-deleted default tag was silently recreated after restart.
        If this database already has any tags or presets, treat it as an
        existing user database and only mark the seed as completed.
        """
        seeded = self.get_setting("defaults_seeded_v1", "")
        if seeded == "1":
            return

        tag_count = int(self.conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0])
        preset_count = int(self.conn.execute("SELECT COUNT(*) FROM tag_presets").fetchone()[0])
        if tag_count > 0 or preset_count > 0:
            self.set_setting("defaults_seeded_v1", "1")
            return

        self.seed_defaults()
        self.set_setting("defaults_seeded_v1", "1")

    def ensure_column(self, table: str, column: str, definition: str) -> None:
        existing = {str(row["name"]) for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def seed_defaults(self) -> None:
        for category, color in DEFAULT_CATEGORY_COLORS.items():
            self.ensure_category(category, color)
        for category, names in DEFAULT_TAG_CATEGORIES.items():
            for name in names:
                self.ensure_tag(name, category)
        for name, tags in DEFAULT_TAG_PRESETS.items():
            if not self.get_tag_preset_by_name(name):
                self.save_tag_preset(None, name, tags)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def backup_to(self, dest_path: Path) -> None:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn.commit()
        backup_conn = sqlite3.connect(str(dest_path))
        try:
            self.conn.backup(backup_conn)
        finally:
            backup_conn.close()

    def now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        return str(row["value"])

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    def ensure_category(self, name: str, color: str = "") -> None:
        name = normalize_category(name)
        if not name:
            name = "custom"
        color = normalize_hex_color(color) or DEFAULT_CATEGORY_COLORS.get(name, "#777777")
        self.conn.execute(
            "INSERT OR IGNORE INTO tag_categories(name, color) VALUES(?, ?)",
            (name, color),
        )

    def set_category_color(self, name: str, color: str) -> None:
        name = normalize_category(name) or "custom"
        color = normalize_hex_color(color) or DEFAULT_CATEGORY_COLORS.get(name, "#777777")
        self.conn.execute(
            "INSERT INTO tag_categories(name, color) VALUES(?, ?) ON CONFLICT(name) DO UPDATE SET color = excluded.color",
            (name, color),
        )
        self.conn.commit()

    def get_category_color(self, name: str) -> str:
        name = normalize_category(name) or "custom"
        row = self.conn.execute("SELECT color FROM tag_categories WHERE name = ?", (name,)).fetchone()
        if row:
            return str(row["color"])
        return DEFAULT_CATEGORY_COLORS.get(name, "#777777")

    def list_categories(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT name, color FROM tag_categories ORDER BY name COLLATE NOCASE").fetchall()

    def find_tag_by_name_nocase(self, name: str, workspace_id: int | None = None) -> sqlite3.Row | None:
        name = normalize_tag(name)
        if not name:
            return None
        workspace_id = self.current_workspace_id() if workspace_id is None else int(workspace_id)
        return self.conn.execute(
            "SELECT id, name FROM tags WHERE workspace_id = ? AND name = ? COLLATE NOCASE ORDER BY id LIMIT 1",
            (workspace_id, name),
        ).fetchone()

    def canonical_tag_name(self, name: str, workspace_id: int | None = None) -> str:
        name = normalize_tag(name)
        if not name:
            return ""
        row = self.find_tag_by_name_nocase(name, workspace_id=workspace_id)
        if row:
            return str(row["name"])
        return name

    def ensure_tag(self, name: str, category: str = "custom", color: str = "", workspace_id: int | None = None) -> int:
        name = normalize_tag(name)
        if not name:
            raise ValueError("empty tag")
        workspace_id = self.current_workspace_id() if workspace_id is None else int(workspace_id)
        category = normalize_category(category) or "custom"
        self.ensure_category(category, DEFAULT_CATEGORY_COLORS.get(category, "#777777"))
        color = normalize_hex_color(color)
        cur = self.conn.cursor()
        row = self.find_tag_by_name_nocase(name, workspace_id=workspace_id)
        if row:
            return int(row["id"])
        cur.execute("INSERT INTO tags(workspace_id, name, category, color) VALUES(?, ?, ?, ?)", (workspace_id, name, category, color))
        return int(cur.lastrowid)

    def update_tag(self, tag_id: Optional[int], name: str, category: str, color: str = "", visible: bool = True) -> int:
        name = normalize_tag(name)
        if not name:
            raise ValueError("タグ名が空です。")
        category = normalize_category(category) or "custom"
        color = normalize_hex_color(color)
        visible_value = 1 if visible else 0
        self.ensure_category(category)
        workspace_id = self.current_workspace_id()
        cur = self.conn.cursor()
        if tag_id is None:
            row = self.find_tag_by_name_nocase(name, workspace_id=workspace_id)
            if row:
                tag_id = int(row["id"])
                cur.execute("UPDATE tags SET category = ?, color = ?, visible = ? WHERE id = ?", (category, color, visible_value, tag_id))
            else:
                cur.execute("INSERT INTO tags(workspace_id, name, category, color, visible) VALUES(?, ?, ?, ?, ?)", (workspace_id, name, category, color, visible_value))
                tag_id = int(cur.lastrowid)
        else:
            cur.execute("UPDATE tags SET name = ?, category = ?, color = ?, visible = ? WHERE id = ?", (name, category, color, visible_value, tag_id))
        self.conn.commit()
        return int(tag_id)

    def delete_tag(self, tag_id: int) -> None:
        row = self.conn.execute("SELECT name FROM tags WHERE id = ?", (tag_id,)).fetchone()
        tag_name = normalize_tag(str(row["name"])) if row else ""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM tags WHERE id = ?", (tag_id,))

        # Also remove the deleted tag name from presets. Otherwise applying
        # an old preset later would recreate the tag via ensure_tag().
        if tag_name:
            preset_rows = cur.execute("SELECT id, tags_json FROM tag_presets WHERE workspace_id = ?", (self.current_workspace_id(),)).fetchall()
            for preset in preset_rows:
                try:
                    tags = json.loads(str(preset["tags_json"] or "[]"))
                except Exception:
                    tags = []
                cleaned = [t for t in tags if normalize_tag(str(t)) != tag_name]
                if cleaned != tags:
                    cur.execute(
                        "UPDATE tag_presets SET tags_json = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(cleaned, ensure_ascii=False), self.now(), int(preset["id"])),
                    )
        self.conn.commit()

    def get_tag(self, tag_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()

    def get_effective_tag_color(self, tag_name: str) -> str:
        row = self.conn.execute(
            """
            SELECT t.color AS color, c.color AS category_color
            FROM tags t
            LEFT JOIN tag_categories c ON c.name = t.category
            WHERE t.workspace_id = ? AND t.name = ?
            """,
            (self.current_workspace_id(), tag_name),
        ).fetchone()
        if not row:
            return DEFAULT_CATEGORY_COLORS.get("custom", "#777777")
        return normalize_hex_color(str(row["color"] or "")) or normalize_hex_color(str(row["category_color"] or "")) or "#777777"

    def set_prompt_tags(self, prompt_id: int, tag_names: Iterable[str]) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM prompt_tags WHERE prompt_id = ?", (prompt_id,))
        seen: set[str] = set()
        for tag_name in tag_names:
            tag_name = self.canonical_tag_name(str(tag_name), workspace_id=self.current_workspace_id())
            key = tag_name.casefold()
            if not tag_name or key in seen:
                continue
            seen.add(key)
            tag_id = self.ensure_tag(tag_name, workspace_id=self.current_workspace_id())
            cur.execute("INSERT OR IGNORE INTO prompt_tags(prompt_id, tag_id) VALUES(?, ?)", (prompt_id, tag_id))
        self.conn.commit()

    def create_prompt(
        self,
        title: str = "新規カード",
        prompt: str = "",
        negative_prompt: str = "",
        description: str = "",
        engine: str = "",
        model: str = "",
        project: str = "",
        rating: int = 0,
        favorite: int = 0,
        pinned: int = 0,
        parent_prompt_id: Optional[int] = None,
        workspace_id: int | None = None,
    ) -> int:
        now = self.now()
        workspace_id = self.current_workspace_id() if workspace_id is None else int(workspace_id)
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO prompts(workspace_id, title, prompt, negative_prompt, description, engine, model, project, rating, favorite, pinned, parent_prompt_id, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (workspace_id, title, prompt, negative_prompt, description, engine, model, project, rating, favorite, pinned, parent_prompt_id, now, now),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_prompt(self, prompt_id: int, data: dict) -> None:
        fields = [
            "title",
            "prompt",
            "negative_prompt",
            "description",
            "engine",
            "model",
            "project",
            "rating",
            "favorite",
        ]
        values = [data.get(field, "") for field in fields]
        values.append(self.now())
        values.append(prompt_id)
        sql = """
            UPDATE prompts
            SET title = ?, prompt = ?, negative_prompt = ?, description = ?, engine = ?, model = ?, project = ?,
                rating = ?, favorite = ?, updated_at = ?
            WHERE id = ?
        """
        self.conn.execute(sql, values)
        self.conn.commit()

    def touch_prompt(self, prompt_id: int, commit: bool = True) -> None:
        self.conn.execute("UPDATE prompts SET updated_at = ? WHERE id = ?", (self.now(), int(prompt_id)))
        if commit:
            self.conn.commit()

    def set_prompt_pinned(self, prompt_id: int, pinned: bool) -> None:
        self.conn.execute("UPDATE prompts SET pinned = ? WHERE id = ?", (1 if pinned else 0, prompt_id))
        self.conn.commit()

    def delete_prompt(self, prompt_id: int) -> None:
        self.conn.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
        self.conn.commit()

    def get_prompt(self, prompt_id: int) -> sqlite3.Row | None:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
        return cur.fetchone()

    def prompt_row_from_sql_row(self, row: sqlite3.Row) -> PromptRow:
        prompt_id = int(row["id"])
        cover_row = self.conn.execute(
            """
            SELECT thumbnail_path FROM images
            WHERE prompt_id = ?
            ORDER BY is_cover DESC, sort_order ASC, id ASC
            LIMIT 1
            """,
            (prompt_id,),
        ).fetchone()
        return PromptRow(
            id=prompt_id,
            workspace_id=int(row["workspace_id"] if "workspace_id" in row.keys() else self.current_workspace_id()),
            title=str(row["title"]),
            prompt=str(row["prompt"]),
            negative_prompt=str(row["negative_prompt"]),
            description=str(row["description"]),
            engine=str(row["engine"]),
            model=str(row["model"]),
            project=str(row["project"]),
            rating=int(row["rating"]),
            favorite=int(row["favorite"]),
            pinned=int(row["pinned"]),
            tags=self.list_prompt_tags(prompt_id),
            cover_thumb=str(cover_row["thumbnail_path"] if cover_row else ""),
            updated_at=str(row["updated_at"]),
        )

    def get_prompt_row(self, prompt_id: int) -> PromptRow | None:
        row = self.get_prompt(prompt_id)
        if row is None:
            return None
        return self.prompt_row_from_sql_row(row)

    def list_prompt_tags(self, prompt_id: int) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT t.name FROM tags t
            JOIN prompt_tags pt ON pt.tag_id = t.id
            WHERE pt.prompt_id = ?
            ORDER BY t.category, t.name
            """,
            (prompt_id,),
        ).fetchall()
        return [str(row["name"]) for row in rows]

    def list_tags_with_counts(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT t.id, t.name, t.category, t.color, t.visible, COALESCE(c.color, '#777777') AS category_color,
                   COUNT(p.id) AS count
            FROM tags t
            LEFT JOIN prompt_tags pt ON pt.tag_id = t.id
            LEFT JOIN prompts p ON p.id = pt.prompt_id AND p.workspace_id = t.workspace_id
            LEFT JOIN tag_categories c ON c.name = t.category
            WHERE t.workspace_id = ?
            GROUP BY t.id
            ORDER BY CASE t.category
                WHEN 'メディア' THEN 0
                WHEN '用途' THEN 1
                WHEN '状態' THEN 2
                WHEN 'プロジェクト' THEN 3
                WHEN 'AI' THEN 4
                ELSE 5
            END, t.name COLLATE NOCASE
            """,
            (self.current_workspace_id(),),
        ).fetchall()

    def list_prompts(self, sort_mode: str = DEFAULT_PROMPT_SORT_MODE) -> list[PromptRow]:
        sort_mode = normalize_prompt_sort_mode(sort_mode)
        if sort_mode == PROMPT_SORT_TITLE:
            order_sql = "ORDER BY p.title COLLATE NOCASE ASC, p.updated_at DESC, p.id DESC"
        else:
            order_sql = "ORDER BY p.updated_at DESC, p.id DESC"
        rows = self.conn.execute(
            f"""
            SELECT p.*,
                   COALESCE((
                       SELECT i.thumbnail_path FROM images i
                       WHERE i.prompt_id = p.id
                       ORDER BY i.is_cover DESC, i.sort_order ASC, i.id ASC
                       LIMIT 1
                   ), '') AS cover_thumb
            FROM prompts p
            WHERE p.workspace_id = ?
            {order_sql}
            """
        , (self.current_workspace_id(),)).fetchall()
        result: list[PromptRow] = []
        for row in rows:
            tags = self.list_prompt_tags(int(row["id"]))
            result.append(
                PromptRow(
                    id=int(row["id"]),
                    workspace_id=int(row["workspace_id"] if "workspace_id" in row.keys() else self.current_workspace_id()),
                    title=str(row["title"]),
                    prompt=str(row["prompt"]),
                    negative_prompt=str(row["negative_prompt"]),
                    description=str(row["description"]),
                    engine=str(row["engine"]),
                    model=str(row["model"]),
                    project=str(row["project"]),
                    rating=int(row["rating"]),
                    favorite=int(row["favorite"]),
                    pinned=int(row["pinned"]),
                    tags=tags,
                    cover_thumb=str(row["cover_thumb"] or ""),
                    updated_at=str(row["updated_at"]),
                )
            )
        return result

    def add_image(
        self,
        prompt_id: int,
        file_path: str,
        thumbnail_path: str = "",
        caption: str = "",
        is_cover: int = 0,
        media_type: str = "image",
        original_name: str = "",
    ) -> int:
        cur = self.conn.cursor()
        max_sort = cur.execute("SELECT COALESCE(MAX(sort_order), -1) AS max_sort FROM images WHERE prompt_id = ?", (prompt_id,)).fetchone()["max_sort"]
        count = cur.execute("SELECT COUNT(*) AS c FROM images WHERE prompt_id = ?", (prompt_id,)).fetchone()["c"]
        if count == 0:
            is_cover = 1
        cur.execute(
            """
            INSERT INTO images(prompt_id, file_path, thumbnail_path, sort_order, caption, is_cover, created_at, media_type, original_name)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (prompt_id, file_path, thumbnail_path, int(max_sort) + 1, caption, is_cover, self.now(), media_type, original_name),
        )
        self.touch_prompt(prompt_id, commit=False)
        self.conn.commit()
        return int(cur.lastrowid)

    def update_image_thumbnail(self, image_id: int, thumbnail_path: str) -> None:
        self.conn.execute("UPDATE images SET thumbnail_path = ? WHERE id = ?", (thumbnail_path, image_id))
        self.conn.commit()

    def update_image_file_path(self, image_id: int, file_path: str, touch: bool = True) -> None:
        row = self.get_image(image_id)
        if not row:
            return
        self.conn.execute("UPDATE images SET file_path = ? WHERE id = ?", (file_path, image_id))
        if touch:
            self.touch_prompt(int(row["prompt_id"]), commit=False)
        self.conn.commit()

    def update_image_label(self, image_id: int, label_id: int) -> None:
        row = self.get_image(image_id)
        if not row:
            return
        label_id = max(0, min(9, int(label_id)))
        self.conn.execute("UPDATE images SET label_id = ? WHERE id = ?", (label_id, image_id))
        self.touch_prompt(int(row["prompt_id"]), commit=False)
        self.conn.commit()

    def move_image_to_prompt(self, image_id: int, target_prompt_id: int, file_path: str, thumbnail_path: str) -> None:
        row = self.get_image(image_id)
        if not row:
            return
        source_prompt_id = int(row["prompt_id"])
        target_prompt_id = int(target_prompt_id)
        cur = self.conn.cursor()
        target_count = cur.execute("SELECT COUNT(*) AS c FROM images WHERE prompt_id = ?", (target_prompt_id,)).fetchone()["c"]
        max_sort = cur.execute("SELECT COALESCE(MAX(sort_order), -1) AS max_sort FROM images WHERE prompt_id = ?", (target_prompt_id,)).fetchone()["max_sort"]
        is_cover = 1 if int(target_count) == 0 else 0
        cur.execute(
            """
            UPDATE images
            SET prompt_id = ?, file_path = ?, thumbnail_path = ?, sort_order = ?, is_cover = ?
            WHERE id = ?
            """,
            (target_prompt_id, file_path, thumbnail_path, int(max_sort) + 1, is_cover, image_id),
        )
        if source_prompt_id != target_prompt_id:
            has_cover = cur.execute(
                "SELECT COUNT(*) AS c FROM images WHERE prompt_id = ? AND is_cover = 1", (source_prompt_id,)
            ).fetchone()["c"]
            if int(has_cover) == 0:
                first = cur.execute(
                    "SELECT id FROM images WHERE prompt_id = ? ORDER BY sort_order ASC, id ASC LIMIT 1",
                    (source_prompt_id,),
                ).fetchone()
                if first:
                    cur.execute("UPDATE images SET is_cover = 1 WHERE id = ?", (int(first["id"]),))
            self.touch_prompt(source_prompt_id, commit=False)
        self.touch_prompt(target_prompt_id, commit=False)
        self.conn.commit()

    def list_images(self, prompt_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM images WHERE prompt_id = ? ORDER BY sort_order ASC, id ASC",
            (prompt_id,),
        ).fetchall()

    def reorder_images(self, prompt_id: int, image_ids: list[int]) -> None:
        cur = self.conn.cursor()
        for sort_order, image_id in enumerate(image_ids):
            cur.execute(
                "UPDATE images SET sort_order = ? WHERE id = ? AND prompt_id = ?",
                (sort_order, int(image_id), prompt_id),
            )
        self.touch_prompt(prompt_id, commit=False)
        self.conn.commit()

    def get_image(self, image_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()

    def delete_image(self, image_id: int) -> None:
        row = self.get_image(image_id)
        if not row:
            return
        prompt_id = int(row["prompt_id"])
        self.conn.execute("DELETE FROM images WHERE id = ?", (image_id,))
        has_cover = self.conn.execute(
            "SELECT COUNT(*) AS c FROM images WHERE prompt_id = ? AND is_cover = 1", (prompt_id,)
        ).fetchone()["c"]
        if int(has_cover) == 0:
            first = self.conn.execute(
                "SELECT id FROM images WHERE prompt_id = ? ORDER BY sort_order ASC, id ASC LIMIT 1", (prompt_id,)
            ).fetchone()
            if first:
                self.conn.execute("UPDATE images SET is_cover = 1 WHERE id = ?", (int(first["id"]),))
        self.touch_prompt(prompt_id, commit=False)
        self.conn.commit()

    def set_cover_image(self, prompt_id: int, image_id: int) -> None:
        self.conn.execute("UPDATE images SET is_cover = 0 WHERE prompt_id = ?", (prompt_id,))
        self.conn.execute("UPDATE images SET is_cover = 1 WHERE id = ? AND prompt_id = ?", (image_id, prompt_id))
        self.touch_prompt(prompt_id, commit=False)
        self.conn.commit()

    def duplicate_prompt(self, prompt_id: int) -> Optional[int]:
        row = self.get_prompt(prompt_id)
        if not row:
            return None
        new_id = self.create_prompt(
            title=f"{row['title']} のコピー",
            prompt=str(row["prompt"]),
            negative_prompt=str(row["negative_prompt"]),
            description=str(row["description"]),
            engine=str(row["engine"]),
            model=str(row["model"]),
            project=str(row["project"]),
            rating=int(row["rating"]),
            favorite=int(row["favorite"]),
            pinned=0,
            parent_prompt_id=prompt_id,
            workspace_id=int(row["workspace_id"] if "workspace_id" in row.keys() else self.current_workspace_id()),
        )
        self.set_prompt_tags(new_id, self.list_prompt_tags(prompt_id))
        return new_id

    def get_tag_preset_by_name(self, name: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM tag_presets WHERE workspace_id = ? AND name = ?",
            (self.current_workspace_id(), name),
        ).fetchone()

    def list_tag_presets(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM tag_presets WHERE workspace_id = ? ORDER BY name COLLATE NOCASE",
            (self.current_workspace_id(),),
        ).fetchall()

    def save_tag_preset(self, preset_id: Optional[int], name: str, tags: Iterable[str]) -> int:
        name = name.strip()
        if not name:
            raise ValueError("プリセット名が空です。")
        tag_list: list[str] = []
        seen_tags: set[str] = set()
        for tag in tags:
            tag_name = self.canonical_tag_name(str(tag), workspace_id=self.current_workspace_id())
            key = tag_name.casefold()
            if tag_name and key not in seen_tags:
                tag_list.append(tag_name)
                seen_tags.add(key)
        for tag in tag_list:
            self.ensure_tag(tag, workspace_id=self.current_workspace_id())
        tags_json = json.dumps(tag_list, ensure_ascii=False)
        now = self.now()
        cur = self.conn.cursor()
        if preset_id is None:
            row = cur.execute("SELECT id FROM tag_presets WHERE workspace_id = ? AND name = ?", (self.current_workspace_id(), name)).fetchone()
            if row:
                preset_id = int(row["id"])
                cur.execute("UPDATE tag_presets SET tags_json = ?, updated_at = ? WHERE id = ?", (tags_json, now, preset_id))
            else:
                cur.execute(
                    "INSERT INTO tag_presets(workspace_id, name, tags_json, created_at, updated_at) VALUES(?, ?, ?, ?, ?)",
                    (self.current_workspace_id(), name, tags_json, now, now),
                )
                preset_id = int(cur.lastrowid)
        else:
            cur.execute("UPDATE tag_presets SET name = ?, tags_json = ?, updated_at = ? WHERE id = ?", (name, tags_json, now, preset_id))
        self.conn.commit()
        return int(preset_id)

    def delete_tag_preset(self, preset_id: int) -> None:
        self.conn.execute("DELETE FROM tag_presets WHERE id = ?", (preset_id,))
        self.conn.commit()

    def seed_meta_options_from_prompts_if_needed(self) -> None:
        if self.get_setting("meta_options_seeded_from_prompts_v1", "") == "1":
            return
        for field in META_OPTION_FIELDS:
            rows = self.conn.execute(
                f"SELECT DISTINCT {field} AS value FROM prompts WHERE TRIM({field}) != ''"
            ).fetchall()
            for row in rows:
                self.ensure_meta_option(field, str(row["value"]), commit=False)
        self.set_setting("meta_options_seeded_from_prompts_v1", "1")
        self.conn.commit()

    def ensure_meta_option(self, field: str, value: str, commit: bool = True) -> None:
        field = normalize_meta_field(field)
        value = normalize_meta_value(value)
        if not field or not value:
            return
        now = self.now()
        self.conn.execute(
            """
            INSERT INTO meta_options(field, value, created_at, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(field, value) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (field, value, now, now),
        )
        if commit:
            self.conn.commit()

    def ensure_meta_options_from_prompt_data(self, data: dict) -> None:
        for field in META_OPTION_FIELDS:
            self.ensure_meta_option(field, str(data.get(field, "") or ""), commit=False)
        self.conn.commit()

    def list_meta_options(self, field: str | None = None) -> list[sqlite3.Row]:
        if field:
            field = normalize_meta_field(field)
            return self.conn.execute(
                "SELECT field, value FROM meta_options WHERE field = ? ORDER BY value COLLATE NOCASE",
                (field,),
            ).fetchall()
        return self.conn.execute(
            "SELECT field, value FROM meta_options ORDER BY field, value COLLATE NOCASE"
        ).fetchall()

    def save_meta_option(self, old_field: str | None, old_value: str | None, field: str, value: str) -> None:
        field = normalize_meta_field(field)
        value = normalize_meta_value(value)
        if not field or not value:
            raise ValueError("入力候補の種類または値が空です。")
        old_field = normalize_meta_field(old_field or "")
        old_value = normalize_meta_value(old_value or "")
        now = self.now()
        cur = self.conn.cursor()
        try:
            if old_field and old_value and (old_field != field or old_value != value):
                cur.execute("DELETE FROM meta_options WHERE field = ? AND value = ?", (old_field, old_value))
                if old_field in META_OPTION_FIELDS and field in META_OPTION_FIELDS:
                    if old_field == field:
                        cur.execute(f"UPDATE prompts SET {old_field} = ? WHERE {old_field} = ?", (value, old_value))
                    else:
                        # 種類（列）を変更する場合は、旧列を空にして新列へ移す。
                        # ただし移動先に既存値があるプロンプトは上書きしない。
                        cur.execute(
                            f"""
                            UPDATE prompts
                            SET {field} = CASE WHEN TRIM({field}) = '' THEN ? ELSE {field} END,
                                {old_field} = ''
                            WHERE {old_field} = ?
                            """,
                            (value, old_value),
                        )
            cur.execute(
                """
                INSERT INTO meta_options(field, value, created_at, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(field, value) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (field, value, now, now),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def delete_meta_option(self, field: str, value: str) -> None:
        field = normalize_meta_field(field)
        value = normalize_meta_value(value)
        if not field or not value:
            return
        self.conn.execute("DELETE FROM meta_options WHERE field = ? AND value = ?", (field, value))
        self.conn.commit()


class FlowLayout(QLayout):
    def __init__(self, parent: Optional[QWidget] = None, margin: int = 0, spacing: int = 6):
        super().__init__(parent)
        self.item_list = []
        self._spacing = spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        while self.count():
            self.takeAt(0)

    def addItem(self, item):  # noqa: N802 - Qt naming
        self.item_list.append(item)

    def count(self) -> int:
        return len(self.item_list)

    def itemAt(self, index: int):  # noqa: N802 - Qt naming
        if 0 <= index < len(self.item_list):
            return self.item_list[index]
        return None

    def takeAt(self, index: int):  # noqa: N802 - Qt naming
        if 0 <= index < len(self.item_list):
            return self.item_list.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802 - Qt naming
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt naming
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt naming
        return self.doLayout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - Qt naming
        super().setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 - Qt naming
        size = QSize()
        for item in self.item_list:
            size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        size += QSize(left + right, top + bottom)
        return size

    def doLayout(self, rect: QRect, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(left, top, -right, -bottom)
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0
        space_x = self._spacing
        space_y = self._spacing

        for item in self.item_list:
            widget_size = item.sizeHint()
            next_x = x + widget_size.width() + space_x
            if next_x - space_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y += line_height + space_y
                next_x = x + widget_size.width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), widget_size))
            x = next_x
            line_height = max(line_height, widget_size.height())
        return y + line_height - rect.y() + bottom


class TagChipEditor(QWidget):
    tagsChanged = Signal()

    def __init__(
        self,
        color_provider: Callable[[str], str],
        parent: Optional[QWidget] = None,
        standalone_layout: bool = True,
        tag_resolver: Optional[Callable[[str], str]] = None,
    ):
        super().__init__(parent)
        self.color_provider = color_provider
        self.tag_resolver = tag_resolver
        self.tags: list[str] = []

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("タグを入力して... / Enter・カンマ区切り可")
        self.add_button = QPushButton("追加")
        self.chip_container = QWidget()
        self.flow = FlowLayout(self.chip_container, margin=0, spacing=6)
        self.chip_container.setLayout(self.flow)
        self.chip_container.setMinimumHeight(30)

        if standalone_layout:
            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(5)
            add_row = QHBoxLayout()
            add_row.setContentsMargins(0, 0, 0, 0)
            add_row.addWidget(self.input_edit, 1)
            add_row.addWidget(self.add_button)
            root.addLayout(add_row)
            root.addWidget(self.chip_container)

        self.input_edit.returnPressed.connect(self.add_from_input)
        self.add_button.clicked.connect(self.add_from_input)

    def resolve_tag_name(self, tag: str) -> str:
        tag = normalize_tag(tag)
        if not tag:
            return ""
        if self.tag_resolver is None:
            return tag
        resolved = normalize_tag(self.tag_resolver(tag))
        return resolved or tag

    def set_tags(self, tags: Iterable[str]) -> None:
        self.tags = []
        seen: set[str] = set()
        for tag in tags:
            tag = self.resolve_tag_name(str(tag))
            key = tag.casefold()
            if tag and key not in seen:
                self.tags.append(tag)
                seen.add(key)
        self.refresh_chips()

    def get_tags(self) -> list[str]:
        return list(self.tags)

    def add_tags(self, tags: Iterable[str]) -> None:
        changed = False
        seen = {tag.casefold() for tag in self.tags}
        for tag in tags:
            tag = self.resolve_tag_name(str(tag))
            key = tag.casefold()
            if tag and key not in seen:
                self.tags.append(tag)
                seen.add(key)
                changed = True
        if changed:
            self.refresh_chips()
            self.tagsChanged.emit()

    def add_from_input(self) -> None:
        tags = parse_tags(self.input_edit.text())
        if not tags:
            return
        self.input_edit.clear()
        self.add_tags(tags)

    def remove_tag(self, tag: str) -> None:
        if tag not in self.tags:
            return
        self.tags.remove(tag)
        self.refresh_chips()
        self.tagsChanged.emit()

    def refresh_chips(self) -> None:
        while self.flow.count():
            item = self.flow.takeAt(0)
            widget = item.widget() if item else None
            if widget:
                widget.deleteLater()
        for tag in self.tags:
            btn = QToolButton()
            btn.setText(f"{tag}  ×")
            btn.setAutoRaise(False)
            btn.setStyleSheet(chip_style(self.color_provider(tag), checked=True))
            btn.clicked.connect(lambda _checked=False, t=tag: self.remove_tag(t))
            self.flow.addWidget(btn)
        self.chip_container.updateGeometry()


class PromptListItemWidget(QWidget):
    def __init__(self, row: PromptRow, icon_size: QSize, parent: Optional[QWidget] = None, show_thumbnail: bool = True):
        super().__init__(parent)
        self.setAutoFillBackground(False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        if show_thumbnail:
            icon_label = QLabel()
            icon_label.setFixedSize(icon_size)
            icon_label.setAlignment(Qt.AlignCenter)
            pix = pixmap_from_path(row.cover_thumb, icon_size)
            if pix is not None:
                icon_label.setPixmap(pix)
            layout.addWidget(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        title = row.title or "(無題)"
        fav = "★ " if row.favorite else ""
        self.title_label = QLabel(f"{fav}{title}")
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setTextInteractionFlags(Qt.NoTextInteraction)
        text_layout.addWidget(self.title_label)

        rating = "★" * row.rating if row.rating else ""
        sub = "  ".join(part for part in [row.project, row.engine, rating] if part)
        if sub:
            sub_label = QLabel(sub)
            sub_label.setTextInteractionFlags(Qt.NoTextInteraction)
            text_layout.addWidget(sub_label)

        tags_label = " / ".join(row.tags[:5])
        if tags_label:
            tag_label = QLabel(tags_label)
            tag_label.setTextInteractionFlags(Qt.NoTextInteraction)
            text_layout.addWidget(tag_label)

        text_layout.addStretch(1)
        layout.addLayout(text_layout, 1)


class PromptListWidget(QListWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_window = main_window
        self.setAcceptDrops(True)
        self.setDragEnabled(False)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setDropIndicatorShown(False)
        self.setDefaultDropAction(Qt.CopyAction)

    def keyPressEvent(self, event):  # noqa: N802 - Qt naming
        modifiers = event.modifiers()
        if event.key() == Qt.Key_Delete and modifiers in (Qt.NoModifier, Qt.KeypadModifier):
            item = self.currentItem()
            if item is not None:
                try:
                    target_prompt_id = int(item.data(Qt.UserRole))
                except Exception:
                    target_prompt_id = None
                if target_prompt_id is not None and self.main_window.current_prompt_id == target_prompt_id:
                    self.main_window.delete_current_prompt()
                    event.accept()
                    return
        super().keyPressEvent(event)

    def event_local_pos(self, event) -> QPoint:
        if hasattr(event, "position"):
            return event.position().toPoint()
        return event.pos()

    def is_material_drop(self, event) -> bool:
        return event.mimeData().hasFormat(INTERNAL_MATERIAL_DRAG_MIME)

    def dragged_material_image_id(self, event) -> Optional[int]:
        if not self.is_material_drop(event):
            return None
        try:
            return int(bytes(event.mimeData().data(INTERNAL_MATERIAL_DRAG_MIME)).decode("utf-8"))
        except Exception:
            return None

    def prompt_item_at_event(self, event) -> Optional[QListWidgetItem]:
        return self.itemAt(self.event_local_pos(event))

    def dragEnterEvent(self, event):  # noqa: N802 - Qt naming
        if self.is_material_drop(event):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802 - Qt naming
        if self.is_material_drop(event) and self.prompt_item_at_event(event) is not None:
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        event.ignore()

    def dropEvent(self, event):  # noqa: N802 - Qt naming
        if not self.is_material_drop(event):
            super().dropEvent(event)
            return
        image_id = self.dragged_material_image_id(event)
        item = self.prompt_item_at_event(event)
        if image_id is None or item is None:
            event.ignore()
            return
        try:
            target_prompt_id = int(item.data(Qt.UserRole))
        except Exception:
            event.ignore()
            return
        copy_mode = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
        if self.main_window.transfer_material_to_prompt(image_id, target_prompt_id, copy_mode=copy_mode):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()


class MaterialListItemDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        view = self.parent()
        main_window = getattr(view, "main_window", None)
        rect = option.rect.adjusted(3, 3, -3, -3)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        has_focus = bool(option.state & QStyle.State_HasFocus)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        if selected:
            painter.setPen(QColor("#0078d7"))
            painter.setBrush(QColor(0, 120, 215, 34))
            painter.drawRoundedRect(rect, 4, 4)
        elif hovered:
            painter.setPen(QColor("#8ab4f8"))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 4, 4)
        elif has_focus:
            painter.setPen(QColor("#0078d7"))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 4, 4)

        icon = index.data(Qt.DecorationRole)
        icon_size = QSize(140, 105)
        icon_rect = QRect(
            rect.left() + max(0, (rect.width() - icon_size.width()) // 2),
            rect.top() + 8,
            icon_size.width(),
            icon_size.height(),
        )
        if isinstance(icon, QIcon) and not icon.isNull():
            pix = icon.pixmap(icon_size)
            if not pix.isNull():
                x = icon_rect.left() + max(0, (icon_rect.width() - pix.width()) // 2)
                y = icon_rect.top() + max(0, (icon_rect.height() - pix.height()) // 2)
                painter.drawPixmap(x, y, pix)

        label_id = safe_int(index.data(Qt.UserRole + 2), 0)
        label_style = main_window.material_label_style(label_id) if main_window is not None else None
        text = str(index.data(Qt.DisplayRole) or "")
        label_rect = QRect(rect.left() + 4, rect.bottom() - 32, rect.width() - 8, 26)

        if label_style:
            fg, bg = label_style
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(bg))
            painter.drawRoundedRect(label_rect, 3, 3)
            text_color = QColor("#000000") if selected else QColor(fg)
        elif selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(210, 232, 255, 220))
            painter.drawRoundedRect(label_rect, 3, 3)
            text_color = QColor("#000000")
        else:
            text_color = option.palette.text().color()

        font = QFont(option.font)
        if selected:
            font.setBold(True)
        painter.setFont(font)
        painter.setPen(text_color)
        metrics = painter.fontMetrics()
        elided = metrics.elidedText(text, Qt.ElideRight, max(10, label_rect.width() - 8))
        painter.drawText(label_rect.adjusted(4, 0, -4, 0), Qt.AlignCenter, elided)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(170, 150)


class ImageListWidget(QListWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_window = main_window
        self._drag_start_pos: Optional[QPoint] = None
        self._drag_start_item: Optional[QListWidgetItem] = None
        self._internal_reorder_done = False
        self._external_drag_visual_timer: Optional[QTimer] = None
        self._external_drag_override_cursor_active = False
        self._drag_active_image_id: Optional[int] = None
        self._drop_indicator_index: Optional[int] = None
        self._drop_indicator_active = False
        # D&D挿入ラインをアイテム境界の外側に自然に出すための左右共通余白。
        # 左端だけを特別扱いしないため、メディア一覧全体の仕様として余白を持つ。
        self.drop_indicator_margin = 10
        self._drop_indicator_widget = QWidget(self.viewport())
        self._drop_indicator_widget.setFixedWidth(5)
        self._drop_indicator_widget.setStyleSheet("background: #005fff; border-left: 1px solid #ffffff; border-right: 1px solid #ffffff;")
        self._drop_indicator_widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._drop_indicator_widget.hide()
        self.setObjectName("materialList")
        self.setItemDelegate(MaterialListItemDelegate(self))
        self.setAcceptDrops(True)
        # Qt標準の内部ドラッグは、外部ファイルD&D用MIMEと競合して
        # 禁止カーソルが出やすい。メディア一覧内の並び替えは自前で追跡し、
        # 一覧外へ出た時だけ外部アプリ向けQDragを開始する。
        self.setDragEnabled(False)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(False)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(140, 105))
        self.setGridSize(QSize(170, 150))
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSpacing(8)
        self.setWordWrap(False)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setMinimumHeight(170)
        self.setStyleSheet(
            f"QListWidget#materialList {{ background: #ffffff; padding-left: {self.drop_indicator_margin}px; padding-right: {self.drop_indicator_margin}px; }}"
        )

    def event_local_pos(self, event) -> QPoint:
        if hasattr(event, "position"):
            return event.position().toPoint()
        return event.pos()

    def mousePressEvent(self, event):  # noqa: N802 - Qt naming
        if event.button() == Qt.LeftButton:
            local_pos = self.event_local_pos(event)
            self._drag_start_pos = local_pos
            self._drag_start_item = self.itemAt(local_pos)
            self._drag_active_image_id = None
            self._internal_reorder_done = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt naming
        if not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        if self._drag_start_pos is None or self._drag_start_item is None:
            super().mouseMoveEvent(event)
            return

        local_pos = self.event_local_pos(event)
        drag_distance = QApplication.startDragDistance() if hasattr(QApplication, "startDragDistance") else QApplication.styleHints().startDragDistance()
        if (local_pos - self._drag_start_pos).manhattanLength() < drag_distance:
            super().mouseMoveEvent(event)
            return

        try:
            image_id = int(self._drag_start_item.data(Qt.UserRole))
        except Exception:
            self.reset_manual_drag_state()
            super().mouseMoveEvent(event)
            return

        self.setCurrentItem(self._drag_start_item)
        self._drag_active_image_id = image_id

        # 一覧内ではQDragを開始しない。OS/QtのD&Dカーソルではなく、
        # 自前の挿入ラインだけで並び替え位置を示す。
        if self.viewport().rect().contains(local_pos):
            self.update_drop_indicator(local_pos)
            event.accept()
            return

        # 一覧外へ出た場合だけ、外部アプリへ渡すファイルD&Dを開始する。
        self.clear_drop_indicator()
        self.start_external_file_drag(image_id)
        self.reset_manual_drag_state()
        event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt naming
        if event.button() == Qt.LeftButton and self._drag_active_image_id is not None:
            local_pos = self.event_local_pos(event)
            image_id = self._drag_active_image_id
            if self.viewport().rect().contains(local_pos):
                self.main_window.reorder_material_by_drop(image_id, self.drop_insert_index(local_pos))
                event.accept()
            self.reset_manual_drag_state()
            return
        self.reset_manual_drag_state()
        super().mouseReleaseEvent(event)

    def start_external_file_drag(self, image_id: int) -> None:
        path = self.main_window.selected_material_path()
        if not path or not path.exists():
            return
        mime = QMimeData()
        file_url = QUrl.fromLocalFile(str(path.resolve()))
        mime.setUrls([file_url])
        # Explorer等への通常ファイルD&D互換を優先する。
        # Windows/QtではCF_HDROPがtext/uri-listと対応しているため、
        # text/uri-listを削るとExplorerへのコピーまで壊れる環境がある。
        # ChromeはFilesがあってもtext/plain/text/uri-listをテキスト欄へ流し込むことがあるため、
        # text/plainには表示されないゼロ幅スペースだけを入れてURL/フルパスの誤挿入を避ける。
        # 自アプリ内テキスト欄への誤ドロップはINTERNAL_MATERIAL_DRAG_MIMEをイベントフィルタで弾く。
        mime.setText("\u200b")
        # 自分自身に戻ってきた場合にコピー登録されないよう識別子は残す。
        mime.setData(INTERNAL_MATERIAL_DRAG_MIME, str(image_id).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        thumb = self.main_window.selected_material_drag_pixmap()
        if thumb is not None and not thumb.isNull():
            drag.setPixmap(thumb)
            drag.setHotSpot(QPoint(min(thumb.width() // 2, 32), min(thumb.height() // 2, 32)))

        # 同じメディア一覧へ戻った時にQt側がIgnoreAction扱いになっても、
        # 実処理は受けられるので禁止カーソルだけを出しっぱなしにしない。
        ignore_cursor = QPixmap(16, 16)
        ignore_cursor.fill(QColor(0, 0, 0, 0))
        drag.setDragCursor(ignore_cursor, Qt.IgnoreAction)

        # 外部アプリへはファイルコピーとして渡す。
        # 自分自身へ戻った場合も、transportとしてはCopyActionを受ける。
        # 実際のメディア一覧内処理はdropEvent側で内部MIMEを見て並び替える。
        self._internal_reorder_done = False

        # Windows/Qt環境によっては、URL付きの自分発QDragを同じ一覧へ戻した時に
        # dragMoveEvent/dropEventが来ず、IgnoreActionの禁止カーソルだけが出ることがある。
        # 実処理はexec後フォールバックで守りつつ、表示だけはカーソル位置を追って補う。
        self.start_external_drag_visual_tracking(image_id)
        result = Qt.IgnoreAction
        try:
            result = drag.exec(Qt.CopyAction, Qt.CopyAction)
        finally:
            self.stop_external_drag_visual_tracking()

        # dropEventまで届かずIgnoreで終わった場合だけ、最終カーソル位置がメディア一覧内なら
        # 手動D&Dの続きとして並び替える。
        if not self._internal_reorder_done and result == Qt.IgnoreAction:
            local_pos = self.viewport().mapFromGlobal(QCursor.pos())
            if self.viewport().rect().contains(local_pos):
                self.main_window.reorder_material_by_drop(image_id, self.drop_insert_index(local_pos))

    def start_external_drag_visual_tracking(self, image_id: int) -> None:
        self.stop_external_drag_visual_tracking()
        self._drag_active_image_id = image_id
        self._external_drag_visual_timer = QTimer(self)
        self._external_drag_visual_timer.setInterval(30)
        self._external_drag_visual_timer.timeout.connect(lambda: self.update_external_drag_visuals(image_id))
        self._external_drag_visual_timer.start()
        self.update_external_drag_visuals(image_id)

    def stop_external_drag_visual_tracking(self) -> None:
        if self._external_drag_visual_timer is not None:
            self._external_drag_visual_timer.stop()
            self._external_drag_visual_timer.deleteLater()
            self._external_drag_visual_timer = None
        self.set_external_drag_override_cursor(False)
        self.clear_drop_indicator()

    def update_external_drag_visuals(self, image_id: int) -> None:
        local_pos = self.viewport().mapFromGlobal(QCursor.pos())
        if self.viewport().rect().contains(local_pos):
            self._drag_active_image_id = image_id
            self.update_drop_indicator(local_pos)
            # QDrag側がIgnoreAction扱いでも、メディア一覧内では実際に並び替え可能なので
            # 禁止カーソルを出しっぱなしにしない。
            self.set_external_drag_override_cursor(True)
        else:
            self.clear_drop_indicator()
            self.set_external_drag_override_cursor(False)

    def set_external_drag_override_cursor(self, enabled: bool) -> None:
        if enabled and not self._external_drag_override_cursor_active:
            QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))
            self._external_drag_override_cursor_active = True
        elif not enabled and self._external_drag_override_cursor_active:
            QApplication.restoreOverrideCursor()
            self._external_drag_override_cursor_active = False

    def reset_manual_drag_state(self) -> None:
        self.clear_drop_indicator()
        self._drag_start_pos = None
        self._drag_start_item = None
        self._drag_active_image_id = None
        self._internal_reorder_done = False

    def keyPressEvent(self, event):  # noqa: N802 - Qt naming
        modifiers = event.modifiers()
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space) and modifiers in (Qt.NoModifier, Qt.KeypadModifier):
            self.main_window.open_selected_image()
            event.accept()
            return
        if event.key() == Qt.Key_C and modifiers == Qt.ControlModifier:
            self.main_window.copy_selected_material_to_clipboard()
            event.accept()
            return
        if event.key() == Qt.Key_V and modifiers == Qt.ControlModifier:
            self.main_window.paste_material_from_clipboard()
            event.accept()
            return
        if event.key() == Qt.Key_Delete and modifiers in (Qt.NoModifier, Qt.KeypadModifier):
            self.main_window.remove_selected_image()
            event.accept()
            return
        if event.key() == Qt.Key_F2:
            self.main_window.rename_selected_image()
            event.accept()
            return
        if modifiers in (Qt.NoModifier, Qt.KeypadModifier):
            key = event.key()
            if Qt.Key_1 <= key <= Qt.Key_9:
                self.main_window.set_selected_material_label(key - Qt.Key_0)
                event.accept()
                return
            if key == Qt.Key_0:
                self.main_window.set_selected_material_label(0)
                event.accept()
                return
        super().keyPressEvent(event)

    def is_internal_material_drag(self, event) -> bool:
        return event.source() is self or event.mimeData().hasFormat(INTERNAL_MATERIAL_DRAG_MIME)

    def dragged_material_image_id(self, event) -> Optional[int]:
        if self.is_internal_material_drag(event):
            try:
                return int(bytes(event.mimeData().data(INTERNAL_MATERIAL_DRAG_MIME)).decode("utf-8"))
            except Exception:
                pass
        if self._drag_active_image_id is not None:
            return self._drag_active_image_id
        if self._drag_start_item is not None:
            try:
                return int(self._drag_start_item.data(Qt.UserRole))
            except Exception:
                pass
        return None

    def dragEnterEvent(self, event):  # noqa: N802 - Qt naming
        if self.is_internal_material_drag(event):
            local_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self.update_drop_indicator(local_pos)
            # 一覧外へ出た時に開始する外部ファイル用QDragはCopyActionなので、
            # 同じメディア一覧へ戻った時もtransportとしてはCopyActionで受ける。
            # dropEvent内では内部MIMEを見て実際には並び替えだけを行う。
            event.setDropAction(Qt.CopyAction)
            event.accept()
        elif has_media_urls(event.mimeData()):
            self.clear_drop_indicator()
            event.acceptProposedAction()
        else:
            self.clear_drop_indicator()
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802 - Qt naming
        if self.is_internal_material_drag(event):
            local_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self.update_drop_indicator(local_pos)
            event.setDropAction(Qt.CopyAction)
            event.accept()
        elif has_media_urls(event.mimeData()):
            self.clear_drop_indicator()
            event.acceptProposedAction()
        else:
            self.clear_drop_indicator()
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):  # noqa: N802 - Qt naming
        self.clear_drop_indicator()
        super().dragLeaveEvent(event)

    def drop_indicator_geometry(self, index: int) -> QRect:
        index = max(0, min(self.count(), int(index)))
        indicator_width = max(5, self._drop_indicator_widget.width() or 5)
        viewport_width = max(indicator_width + self.drop_indicator_margin * 2, self.viewport().width())
        height = max(24, self.viewport().height() - 16)
        edge_margin = max(0, int(self.drop_indicator_margin))
        gap = max(4, self.spacing() // 2)

        def clamped_x(raw_x: int) -> int:
            # 左右に同じD&D用余白を持たせ、挿入ラインは常に表示領域内に収める。
            return max(edge_margin, min(viewport_width - indicator_width - edge_margin, int(raw_x)))

        if self.count() == 0:
            return QRect(clamped_x(edge_margin), 8, indicator_width, height)
        if index >= self.count():
            rect = self.visualItemRect(self.item(self.count() - 1))
            x = clamped_x(rect.right() + gap)
            return QRect(x, rect.top() + 4, indicator_width, max(24, rect.height() - 8))
        rect = self.visualItemRect(self.item(index))
        x = clamped_x(rect.left() - gap)
        return QRect(x, rect.top() + 4, indicator_width, max(24, rect.height() - 8))

    def update_drop_indicator(self, pos: QPoint) -> None:
        index = self.drop_insert_index(pos)
        self._drop_indicator_index = index
        self._drop_indicator_active = True
        self._drop_indicator_widget.setGeometry(self.drop_indicator_geometry(index))
        self._drop_indicator_widget.raise_()
        self._drop_indicator_widget.show()
        self.viewport().update()

    def clear_drop_indicator(self) -> None:
        self._drop_indicator_active = False
        self._drop_indicator_index = None
        self._drop_indicator_widget.hide()
        self.viewport().update()

    def drop_insert_index(self, pos: QPoint) -> int:
        count = self.count()
        if count <= 0:
            return 0

        entries: list[tuple[int, QRect]] = []
        for index in range(count):
            item = self.item(index)
            if item is None:
                continue
            rect = self.visualItemRect(item)
            if rect.isValid():
                entries.append((index, rect))
        if not entries:
            return count

        # アイコン表示では itemAt() だけに頼ると、先頭アイテムの左側などの余白が
        # 「どのアイテムでもない場所」になり、末尾扱いになってしまう。
        # そのため表示中アイテムの行と中心Xから、挿入位置を明示的に計算する。
        spacing = max(1, self.spacing())
        first_top = min(rect.top() for _index, rect in entries)
        last_bottom = max(rect.bottom() for _index, rect in entries)
        if pos.y() < first_top - spacing:
            return entries[0][0]
        if pos.y() > last_bottom + spacing:
            return count

        # 近い行を選ぶ。行内は左から右へ、中心より左ならそのアイテムの前、
        # 中心より右なら次の位置へ挿入する。
        rows: list[list[tuple[int, QRect]]] = []
        for index, rect in sorted(entries, key=lambda e: (e[1].center().y(), e[1].center().x())):
            placed = False
            for row in rows:
                row_center_y = sum(r.center().y() for _i, r in row) / max(1, len(row))
                row_height = max(r.height() for _i, r in row)
                if abs(rect.center().y() - row_center_y) <= max(spacing * 2, row_height * 0.45):
                    row.append((index, rect))
                    placed = True
                    break
            if not placed:
                rows.append([(index, rect)])

        def row_distance(row: list[tuple[int, QRect]]) -> float:
            top = min(rect.top() for _index, rect in row)
            bottom = max(rect.bottom() for _index, rect in row)
            if top - spacing <= pos.y() <= bottom + spacing:
                return 0.0
            center_y = sum(rect.center().y() for _index, rect in row) / max(1, len(row))
            return abs(pos.y() - center_y)

        row = min(rows, key=row_distance)
        row = sorted(row, key=lambda e: e[1].center().x())
        for index, rect in row:
            if pos.x() <= rect.center().x():
                return max(0, min(count, index))
        return max(0, min(count, row[-1][0] + 1))

    def dropEvent(self, event):  # noqa: N802 - Qt naming
        if self.is_internal_material_drag(event):
            image_id = self.dragged_material_image_id(event)
            if image_id is None:
                event.ignore()
                return
            local_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self._internal_reorder_done = True
            self.clear_drop_indicator()
            self.main_window.reorder_material_by_drop(image_id, self.drop_insert_index(local_pos))
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        self.clear_drop_indicator()
        paths = media_paths_from_mime(event.mimeData())
        if paths:
            self.main_window.add_images_from_paths(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)



class ImageViewerWindow(QWidget):
    MODE_FRAMELESS = "frameless"
    MODE_SCROLL = "scroll"
    MODE_LABELS = {
        MODE_FRAMELESS: "フレームレス表示",
        MODE_SCROLL: "通常ウィンドウ表示",
    }
    RESIZE_MARGIN = 8

    def __init__(
        self,
        main_window: "MainWindow",
        image_path: Path,
        mode: str = MODE_FRAMELESS,
        external_image: bool = False,
        source_prompt_id: int | None = None,
        source_image_id: int | None = None,
    ):
        super().__init__()
        self.main_window = main_window
        self.image_path = image_path
        self.external_image = bool(external_image)
        self.source_prompt_id = None if self.external_image else (int(source_prompt_id) if source_prompt_id is not None else None)
        self.source_image_id = None if self.external_image else (int(source_image_id) if source_image_id is not None else None)
        self.pixmap = QPixmap(str(image_path))
        self.mode = mode if mode in self.MODE_LABELS else self.MODE_FRAMELESS
        self.zoom_percent = 100
        self.offset = QPoint(0, 0)
        self._dragging_window = False
        self._dragging_image = False
        self._resizing = False
        self._resize_edges = ""
        self._press_global = QPoint(0, 0)
        self._press_pos = QPoint(0, 0)
        self._press_window_pos = QPoint(0, 0)
        self._press_geom = QRect()
        self._press_offset = QPoint(0, 0)
        self._scaled_pixmap_cache: dict[tuple[str, int, int, int], QPixmap] = {}
        self._scaled_pixmap_cache_order: list[tuple[str, int, int, int]] = []
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumSize(80, 60)
        self.setWindowTitle(image_path.name)
        self.apply_mode(first=True)
        self.resize_to_zoom()
        self.move(self.main_window.next_viewer_position(self.size()))
        self.install_image_viewer_shortcuts()

    def set_shortcut_visible_in_context_menu(self, action: QAction) -> None:
        setter = getattr(action, "setShortcutVisibleInContextMenu", None)
        if callable(setter):
            setter(True)

    def install_image_viewer_shortcuts(self) -> None:
        self.front_image_viewers_action = QAction("前面表示", self)
        self.front_image_viewers_action.setShortcut(QKeySequence("Alt+Z"))
        self.front_image_viewers_action.setShortcutContext(Qt.WindowShortcut)
        self.set_shortcut_visible_in_context_menu(self.front_image_viewers_action)
        self.front_image_viewers_action.triggered.connect(
            lambda _checked=False: self.main_window.bring_visible_image_viewers_to_front()
        )

        self.tile_image_viewers_action = QAction("並べて表示", self)
        self.tile_image_viewers_action.setShortcut(QKeySequence("Alt+A"))
        self.tile_image_viewers_action.setShortcutContext(Qt.WindowShortcut)
        self.set_shortcut_visible_in_context_menu(self.tile_image_viewers_action)
        self.tile_image_viewers_action.triggered.connect(
            lambda _checked=False: self.main_window.tile_visible_image_viewers(self.frameGeometry())
        )

        self.close_all_image_viewers_action = QAction("全て閉じる", self)
        self.close_all_image_viewers_action.setShortcut(QKeySequence("Alt+X"))
        self.close_all_image_viewers_action.setShortcutContext(Qt.WindowShortcut)
        self.set_shortcut_visible_in_context_menu(self.close_all_image_viewers_action)
        self.close_all_image_viewers_action.triggered.connect(
            lambda _checked=False: self.main_window.close_all_image_viewers()
        )

        self.addAction(self.front_image_viewers_action)
        self.addAction(self.tile_image_viewers_action)
        self.addAction(self.close_all_image_viewers_action)

    def is_image_viewer_shortcut_event(self, event) -> bool:
        if not hasattr(event, "key") or not hasattr(event, "modifiers"):
            return False
        if not (event.modifiers() & Qt.AltModifier):
            return False
        return event.key() in (Qt.Key_Z, Qt.Key_A, Qt.Key_X)

    def handle_image_viewer_shortcut_key(self, key: int) -> bool:
        if key == Qt.Key_Z:
            self.main_window.bring_visible_image_viewers_to_front()
            return True
        if key == Qt.Key_A:
            self.main_window.tile_visible_image_viewers(self.frameGeometry())
            return True
        if key == Qt.Key_X:
            self.main_window.close_all_image_viewers()
            return True
        return False

    def handle_image_viewer_shortcut_event(self, event) -> bool:
        if not self.is_image_viewer_shortcut_event(event):
            return False
        if self.handle_image_viewer_shortcut_key(event.key()):
            event.accept()
            return True
        return False

    def is_card_navigation_available(self) -> bool:
        return (not self.external_image) and self.source_prompt_id is not None and self.source_image_id is not None

    def is_viewer_navigation_key(self, key: int, modifiers) -> int:
        no_modifier = modifiers in (Qt.NoModifier, Qt.KeypadModifier)
        alt_only = bool(modifiers & Qt.AltModifier) and not bool(modifiers & (Qt.ControlModifier | Qt.ShiftModifier | Qt.MetaModifier))
        if no_modifier and key in (Qt.Key_Left, Qt.Key_Up):
            return -1
        if no_modifier and key in (Qt.Key_Right, Qt.Key_Down):
            return 1
        if alt_only and key == Qt.Key_Left:
            return -1
        if alt_only and key == Qt.Key_Right:
            return 1
        return 0

    def handle_viewer_navigation_event(self, event) -> bool:
        if not hasattr(event, "key") or not hasattr(event, "modifiers"):
            return False
        direction = self.is_viewer_navigation_key(event.key(), event.modifiers())
        if direction == 0:
            return False
        if self.navigate_card_image(direction):
            event.accept()
            return True
        return False

    def navigate_card_image(self, direction: int) -> bool:
        if not self.is_card_navigation_available():
            return False
        entries = self.main_window.card_image_navigation_entries(int(self.source_prompt_id))
        if not entries:
            return True

        current_index = None
        current_id = int(self.source_image_id) if self.source_image_id is not None else None
        for index, (image_id, _path) in enumerate(entries):
            if current_id is not None and int(image_id) == current_id:
                current_index = index
                break
        if current_index is None:
            current_key = material_path_key(self.image_path)
            for index, (_image_id, path) in enumerate(entries):
                if material_path_key(path) == current_key:
                    current_index = index
                    break
        if current_index is None:
            self.main_window.statusBar().showMessage("この画像の前後移動情報が見つかりません")
            return True

        target_index = current_index + (1 if direction > 0 else -1)
        if target_index < 0 or target_index >= len(entries):
            self.main_window.statusBar().showMessage("前の画像はありません" if direction < 0 else "次の画像はありません")
            return True

        target_image_id, target_path = entries[target_index]
        if self.load_viewer_image(target_path, int(target_image_id)):
            self.main_window.select_material_in_list_if_current_prompt(int(self.source_prompt_id), int(target_image_id))
            self.main_window.statusBar().showMessage(f"画像ビュアー: {target_path.name}")
        return True

    def load_viewer_image(self, image_path: Path, image_id: int | None = None) -> bool:
        if not image_path.exists():
            self.main_window.statusBar().showMessage(f"画像ファイルが見つかりません: {image_path.name}")
            return False
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            self.main_window.statusBar().showMessage(f"画像を表示できません: {image_path.name}")
            return False
        self.image_path = image_path
        if image_id is not None:
            self.source_image_id = int(image_id)
        self.pixmap = pixmap
        self.setWindowTitle(image_path.name)
        self.offset = QPoint(0, 0)
        self.clear_scaled_cache()
        if self.mode == self.MODE_FRAMELESS:
            self.resize_to_zoom()
        else:
            self.center_image_if_needed()
        self.update_cursor(QPoint(self.width() // 2, self.height() // 2))
        self.update()
        return True

    def nativeEvent(self, eventType, message):  # noqa: N802 - Qt naming
        # Windows の Alt+キーは WM_SYSKEYDOWN として処理され、
        # メインウィンドウ最小化中は Qt の QAction / keyPressEvent まで
        # 届かない環境がある。画像ビュアー自身のネイティブイベントでも拾う。
        if sys.platform.startswith("win"):
            try:
                import ctypes
                from ctypes import wintypes

                WM_KEYDOWN = 0x0100
                WM_SYSKEYDOWN = 0x0104
                VK_MENU = 0x12
                VK_Z = 0x5A
                VK_A = 0x41
                VK_X = 0x58
                VK_LEFT = 0x25
                VK_RIGHT = 0x27

                msg = wintypes.MSG.from_address(int(message))
                if int(msg.message) in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    vk = int(msg.wParam)
                    alt_pressed = bool(ctypes.windll.user32.GetAsyncKeyState(VK_MENU) & 0x8000)
                    if vk in (VK_Z, VK_A, VK_X) and alt_pressed:
                        # lParam bit 30 = previous key state. 押しっぱなしリピートは無視。
                        if int(msg.lParam) & (1 << 30):
                            return True, 0
                        qt_key = {VK_Z: Qt.Key_Z, VK_A: Qt.Key_A, VK_X: Qt.Key_X}.get(vk)
                        if qt_key is not None and self.handle_image_viewer_shortcut_key(qt_key):
                            return True, 0
                    if vk in (VK_LEFT, VK_RIGHT) and alt_pressed and self.is_card_navigation_available():
                        if int(msg.lParam) & (1 << 30):
                            return True, 0
                        if self.navigate_card_image(-1 if vk == VK_LEFT else 1):
                            return True, 0
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def clear_scaled_cache(self) -> None:
        self._scaled_pixmap_cache.clear()
        self._scaled_pixmap_cache_order.clear()

    def apply_mode(self, first: bool = False) -> None:
        current_geometry = QRect(self.geometry())
        was_visible = self.isVisible()
        if not first and was_visible:
            self.hide()

        if self.mode == self.MODE_FRAMELESS:
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        else:
            # Let the platform apply the normal decorated window frame.
            # Replacing a frameless top-level window with a newly shown decorated one is
            # more reliable than trying to keep every title/close/minimize hint manually.
            self.setWindowFlags(Qt.Window)
        self.setWindowTitle(self.image_path.name)

        if not first:
            if current_geometry.isValid():
                self.setGeometry(current_geometry)
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def switch_mode(self, mode: str) -> None:
        if mode not in self.MODE_LABELS or mode == self.mode:
            return
        if self.mode == self.MODE_FRAMELESS and mode == self.MODE_SCROLL:
            self.main_window.replace_image_viewer_mode(self, mode)
            return
        self.mode = mode
        self.apply_mode()
        if self.mode == self.MODE_FRAMELESS:
            self.resize_to_zoom()
        else:
            self.center_image_if_needed()
        screen = QGuiApplication.primaryScreen()
        center = screen.geometry().center() if screen is not None else QPoint(0, 0)
        self.update_cursor(self.mapFromGlobal(center))
        self.update()

    def image_size_at_zoom(self) -> QSize:
        if self.pixmap.isNull():
            return QSize(320, 240)
        return QSize(
            max(1, int(round(self.pixmap.width() * self.zoom_percent / 100.0))),
            max(1, int(round(self.pixmap.height() * self.zoom_percent / 100.0))),
        )

    def available_rect(self) -> QRect:
        return best_available_geometry_for_rect(self.frameGeometry())

    def available_size(self) -> QSize:
        rect = self.available_rect()
        return QSize(max(120, rect.width()), max(90, rect.height()))

    def frame_margins(self) -> tuple[int, int, int, int]:
        if self.mode == self.MODE_FRAMELESS:
            return (0, 0, 0, 0)
        frame = self.frameGeometry()
        geom = self.geometry()
        if not frame.isValid() or not geom.isValid():
            return (0, 0, 0, 0)
        left = max(0, geom.left() - frame.left())
        top = max(0, geom.top() - frame.top())
        right = max(0, frame.right() - geom.right())
        bottom = max(0, frame.bottom() - geom.bottom())
        return (left, top, right, bottom)

    def client_geometry_for_frame_rect(self, frame_rect: QRect) -> QRect:
        left, top, right, bottom = self.frame_margins()
        width = max(80, frame_rect.width() - left - right)
        height = max(60, frame_rect.height() - top - bottom)
        return QRect(frame_rect.x() + left, frame_rect.y() + top, width, height)

    def keep_window_frame_on_available_screen(self) -> None:
        # 通常ウィンドウへ戻した直後は、クライアント領域が画面内でも
        # タイトルバー／枠が作業領域外へはみ出すことがある。
        # フレーム外枠を基準に画面内へ収め、必要ならクライアントサイズを縮める。
        frame = QRect(self.frameGeometry())
        if not frame.isValid():
            frame = QRect(self.geometry())
        left, top, right, bottom = self.frame_margins()
        min_frame_width = IMAGE_VIEWER_TILE_MIN_CLIENT_WIDTH + left + right
        min_frame_height = IMAGE_VIEWER_TILE_MIN_CLIENT_HEIGHT + top + bottom
        fixed_frame = keep_rect_on_available_screens(frame, min_frame_width, min_frame_height)
        if self.mode == self.MODE_SCROLL:
            self.setGeometry(self.client_geometry_for_frame_rect(fixed_frame))
        else:
            self.setGeometry(fixed_frame)
        self.center_image_if_needed()
        self.update_cursor(QPoint(self.width() // 2, self.height() // 2))
        self.update()

    def resize_to_zoom(self, clamp_to_screen: bool = True) -> None:
        desired = self.image_size_at_zoom()
        if clamp_to_screen:
            avail = self.available_size()
            if desired.width() > avail.width() or desired.height() > avail.height():
                desired.scale(avail, Qt.KeepAspectRatio)
        if self.mode == self.MODE_FRAMELESS:
            self.resize(desired)
            if clamp_to_screen:
                self.setGeometry(keep_rect_on_available_screens(self.geometry(), 80, 60))
        self.center_image_if_needed()

    def center_image_if_needed(self) -> None:
        img_size = self.image_size_at_zoom()
        x = self.offset.x()
        y = self.offset.y()
        if img_size.width() <= self.width():
            x = (self.width() - img_size.width()) // 2
        else:
            x = min(0, max(self.width() - img_size.width(), x))
        if img_size.height() <= self.height():
            y = (self.height() - img_size.height()) // 2
        else:
            y = min(0, max(self.height() - img_size.height(), y))
        self.offset = QPoint(x, y)

    def set_zoom_percent(self, zoom_percent: int) -> None:
        zoom_percent = max(10, min(2000, int(zoom_percent)))
        if zoom_percent == self.zoom_percent:
            return
        old_zoom = max(1, self.zoom_percent)
        if self.mode == self.MODE_SCROLL and not self.pixmap.isNull():
            center_x = self.width() / 2.0
            center_y = self.height() / 2.0
            source_x = (center_x - self.offset.x()) * 100.0 / old_zoom
            source_y = (center_y - self.offset.y()) * 100.0 / old_zoom
            self.zoom_percent = zoom_percent
            new_x = int(round(center_x - source_x * self.zoom_percent / 100.0))
            new_y = int(round(center_y - source_y * self.zoom_percent / 100.0))
            self.offset = QPoint(new_x, new_y)
            self.center_image_if_needed()
        elif self.mode == self.MODE_FRAMELESS:
            old_center = self.frameGeometry().center()
            self.zoom_percent = zoom_percent
            self.resize_to_zoom(clamp_to_screen=False)
            self.move(old_center - QPoint(self.frameGeometry().width() // 2, self.frameGeometry().height() // 2))
        else:
            self.zoom_percent = zoom_percent
            self.center_image_if_needed()
        self.update()

    def edge_at(self, pos: QPoint) -> str:
        if self.mode != self.MODE_FRAMELESS:
            return ""
        m = self.RESIZE_MARGIN
        edges = ""
        if pos.x() <= m:
            edges += "L"
        elif pos.x() >= self.width() - m:
            edges += "R"
        if pos.y() <= m:
            edges += "T"
        elif pos.y() >= self.height() - m:
            edges += "B"
        return edges

    def update_cursor(self, pos: QPoint) -> None:
        edges = self.edge_at(pos)
        if edges in ("L", "R"):
            self.setCursor(Qt.SizeHorCursor)
        elif edges in ("T", "B"):
            self.setCursor(Qt.SizeVerCursor)
        elif edges in ("LT", "RB"):
            self.setCursor(Qt.SizeFDiagCursor)
        elif edges in ("RT", "LB"):
            self.setCursor(Qt.SizeBDiagCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def fit_to_screen_center(self) -> None:
        if self.pixmap.isNull():
            return
        available = self.available_rect()
        if self.mode == self.MODE_SCROLL:
            # 通常ウィンドウ表示では、画像ではなくウィンドウ外枠を作業領域へ合わせる。
            # 通常ウィンドウはタイトルバー／枠があるため、クライアント領域をその分だけ内側に置く。
            self.setGeometry(self.client_geometry_for_frame_rect(available))
        else:
            desired = QSize(self.pixmap.width(), self.pixmap.height())
            desired.scale(available.size(), Qt.KeepAspectRatio)
            desired.setWidth(max(80, desired.width()))
            desired.setHeight(max(60, desired.height()))
            zoom_from_width = desired.width() * 100.0 / max(1, self.pixmap.width())
            zoom_from_height = desired.height() * 100.0 / max(1, self.pixmap.height())
            self.zoom_percent = max(10, min(2000, int(round(min(zoom_from_width, zoom_from_height)))))
            rect = QRect(0, 0, desired.width(), desired.height())
            rect.moveCenter(available.center())
            self.setGeometry(keep_rect_on_available_screens(rect, 80, 60))
            self.offset = QPoint(0, 0)
        self.center_image_if_needed()
        self.update_cursor(QPoint(self.width() // 2, self.height() // 2))
        self.update()

    def contextMenuEvent(self, event):  # noqa: N802 - Qt naming
        menu = QMenu(self)
        frameless_action = QAction(self.MODE_LABELS[self.MODE_FRAMELESS], self)
        frameless_action.setCheckable(True)
        frameless_action.setChecked(self.mode == self.MODE_FRAMELESS)
        scroll_action = QAction(self.MODE_LABELS[self.MODE_SCROLL], self)
        scroll_action.setCheckable(True)
        scroll_action.setChecked(self.mode == self.MODE_SCROLL)
        close_action = QAction("閉じる", self)
        frameless_action.triggered.connect(lambda: self.switch_mode(self.MODE_FRAMELESS))
        scroll_action.triggered.connect(lambda: self.switch_mode(self.MODE_SCROLL))
        close_action.triggered.connect(self.close)
        menu.addAction(frameless_action)
        menu.addAction(scroll_action)
        add_menu = menu.addMenu("メディアへ追加")
        add_current_action = QAction("現在のカードへ追加", self)
        add_current_action.setEnabled(self.main_window.current_prompt_id is not None)
        add_new_action = QAction("新規カードを作って追加", self)
        add_current_action.triggered.connect(lambda: self.main_window.add_external_image_to_current_prompt(self.image_path))
        add_new_action.triggered.connect(lambda: self.main_window.add_external_image_to_new_prompt(self.image_path))
        add_menu.addAction(add_current_action)
        add_menu.addAction(add_new_action)
        menu.addSeparator()
        menu.addAction(self.front_image_viewers_action)
        menu.addAction(self.tile_image_viewers_action)
        menu.addAction(self.close_all_image_viewers_action)
        menu.addSeparator()
        menu.addAction(close_action)
        global_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
        menu.exec(global_pos)

    def keyPressEvent(self, event):  # noqa: N802 - Qt naming
        if self.handle_image_viewer_shortcut_event(event):
            return
        if self.handle_viewer_navigation_event(event):
            return
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event):  # noqa: N802 - Qt naming
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        steps = delta / 120.0
        factor = 1.1 ** steps
        new_zoom = int(round(self.zoom_percent * factor))
        if new_zoom == self.zoom_percent:
            new_zoom += 1 if delta > 0 else -1
        self.set_zoom_percent(new_zoom)
        event.accept()

    def mouseDoubleClickEvent(self, event):  # noqa: N802 - Qt naming
        if event.button() == Qt.LeftButton:
            self._dragging_window = False
            self._dragging_image = False
            self._resizing = False
            self._resize_edges = ""
            self.fit_to_screen_center()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):  # noqa: N802 - Qt naming
        if event.button() == Qt.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._press_pos = event.position().toPoint()
            self._press_window_pos = self.pos()
            self._press_geom = self.geometry()
            self._press_offset = QPoint(self.offset)
            if self.mode == self.MODE_FRAMELESS:
                edges = self.edge_at(self._press_pos)
                if edges:
                    self._resizing = True
                    self._resize_edges = edges
                else:
                    self._dragging_window = True
            else:
                self._dragging_image = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt naming
        pos = event.position().toPoint()
        global_pos = event.globalPosition().toPoint()
        if self._dragging_window:
            self.move(self._press_window_pos + (global_pos - self._press_global))
            event.accept()
            return
        if self._dragging_image:
            self.offset = self._press_offset + (pos - self._press_pos)
            self.center_image_if_needed()
            self.update()
            event.accept()
            return
        if self._resizing:
            self.resize_frameless(global_pos)
            event.accept()
            return
        self.update_cursor(pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt naming
        self._dragging_window = False
        self._dragging_image = False
        self._resizing = False
        self._resize_edges = ""
        super().mouseReleaseEvent(event)

    def resize_frameless(self, global_pos: QPoint) -> None:
        if self.pixmap.isNull():
            return
        geom = QRect(self._press_geom)
        dx = global_pos.x() - self._press_global.x()
        dy = global_pos.y() - self._press_global.y()
        ratio = self.pixmap.width() / max(1, self.pixmap.height())
        if "L" in self._resize_edges:
            new_w = geom.width() - dx
        elif "R" in self._resize_edges:
            new_w = geom.width() + dx
        else:
            if "T" in self._resize_edges:
                new_w = int(round((geom.height() - dy) * ratio))
            else:
                new_w = int(round((geom.height() + dy) * ratio))
        new_w = max(80, new_w)
        new_h = max(60, int(round(new_w / ratio)))
        avail = self.available_size()
        if new_w > avail.width() or new_h > avail.height():
            size = QSize(new_w, new_h)
            size.scale(avail, Qt.KeepAspectRatio)
            new_w, new_h = size.width(), size.height()
        new_x = geom.x()
        new_y = geom.y()
        if "L" in self._resize_edges:
            new_x = geom.right() - new_w + 1
        if "T" in self._resize_edges:
            new_y = geom.bottom() - new_h + 1
        new_rect = keep_rect_on_available_screens(QRect(new_x, new_y, new_w, new_h), 80, 60)
        self.setGeometry(new_rect)
        self.update()

    def resizeEvent(self, event):  # noqa: N802 - Qt naming
        if self.mode == self.MODE_FRAMELESS and not self.pixmap.isNull():
            ratio = self.pixmap.width() / max(1, self.pixmap.height())
            expected_h = max(1, int(round(self.width() / ratio)))
            if abs(expected_h - self.height()) > 1 and not self._resizing:
                self.resize(self.width(), expected_h)
        self.center_image_if_needed()
        super().resizeEvent(event)

    def scaled_pixmap_for_target(self, target_size: QSize, method: str) -> QPixmap:
        width = max(1, target_size.width())
        height = max(1, target_size.height())
        cache_key = (method, int(self.pixmap.cacheKey()), width, height)
        cached = self._scaled_pixmap_cache.get(cache_key)
        if cached is not None and not cached.isNull():
            return cached
        pixmap = QPixmap()
        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore

            qimage = self.pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)
            source_width = qimage.width()
            source_height = qimage.height()
            source = np.frombuffer(qimage.bits(), dtype=np.uint8).reshape((source_height, source_width, 4))
            interpolation = cv2.INTER_LANCZOS4 if method == "lanczos" else cv2.INTER_CUBIC
            resized = cv2.resize(source, (width, height), interpolation=interpolation)
            resized = np.ascontiguousarray(resized)
            out_image = QImage(resized.data, width, height, width * 4, QImage.Format_RGBA8888).copy()
            pixmap = QPixmap.fromImage(out_image)
        except Exception:
            pixmap = self.pixmap.scaled(target_size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        if pixmap.isNull():
            pixmap = self.pixmap.scaled(target_size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self._scaled_pixmap_cache[cache_key] = pixmap
        self._scaled_pixmap_cache_order.append(cache_key)
        while len(self._scaled_pixmap_cache_order) > 8:
            old_key = self._scaled_pixmap_cache_order.pop(0)
            self._scaled_pixmap_cache.pop(old_key, None)
        return pixmap

    def draw_scaled_pixmap(self, painter: QPainter, target: QRect) -> None:
        if target.width() <= 0 or target.height() <= 0:
            return
        method = normalize_image_viewer_resize_method(self.main_window.image_viewer_resize_method)
        if method == "nearest":
            painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
            painter.drawPixmap(target, self.pixmap)
        elif method == "smooth":
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(target, self.pixmap)
        else:
            painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
            painter.drawPixmap(target.topLeft(), self.scaled_pixmap_for_target(target.size(), method))

    def paintEvent(self, event):  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(20, 20, 20))
        if self.pixmap.isNull():
            painter.setPen(QColor(240, 240, 240))
            painter.drawText(self.rect(), Qt.AlignCenter, "画像を表示できません")
            return
        if self.mode == self.MODE_FRAMELESS:
            self.draw_scaled_pixmap(painter, self.rect())
        else:
            img_size = self.image_size_at_zoom()
            target = QRect(self.offset, img_size)
            self.draw_scaled_pixmap(painter, target)

    def closeEvent(self, event):  # noqa: N802 - Qt naming
        self.main_window.save_image_viewer_position(self.pos())
        self.main_window.unregister_image_viewer(self)
        super().closeEvent(event)


@dataclass(frozen=True)
class ViewerTileRect:
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class ViewerTileItem:
    viewer: ImageViewerWindow
    src_w: int
    src_h: int
    frame_extra_w: int
    frame_extra_h: int
    client_w: float
    client_h: float
    w: float
    h: float


@dataclass(frozen=True)
class PlacedViewerTile:
    item: ViewerTileItem
    rect: ViewerTileRect


def viewer_tile_area(rect: ViewerTileRect) -> float:
    return max(0.0, rect.w) * max(0.0, rect.h)


def viewer_tile_contains(a: ViewerTileRect, b: ViewerTileRect) -> bool:
    return (
        b.x >= a.x
        and b.y >= a.y
        and b.x + b.w <= a.x + a.w
        and b.y + b.h <= a.y + a.h
    )


def viewer_tile_intersects(a: ViewerTileRect, b: ViewerTileRect) -> bool:
    return not (
        b.x >= a.x + a.w
        or b.x + b.w <= a.x
        or b.y >= a.y + a.h
        or b.y + b.h <= a.y
    )


def split_viewer_free_rect(free: ViewerTileRect, used: ViewerTileRect) -> list[ViewerTileRect]:
    if not viewer_tile_intersects(free, used):
        return [free]

    result: list[ViewerTileRect] = []
    if used.x > free.x:
        result.append(ViewerTileRect(free.x, free.y, used.x - free.x, free.h))
    if used.x + used.w < free.x + free.w:
        result.append(
            ViewerTileRect(
                used.x + used.w,
                free.y,
                free.x + free.w - (used.x + used.w),
                free.h,
            )
        )
    if used.y > free.y:
        result.append(ViewerTileRect(free.x, free.y, free.w, used.y - free.y))
    if used.y + used.h < free.y + free.h:
        result.append(
            ViewerTileRect(
                free.x,
                used.y + used.h,
                free.w,
                free.y + free.h - (used.y + used.h),
            )
        )
    return [rect for rect in result if rect.w > 0 and rect.h > 0]


def prune_viewer_free_rects(free_rects: list[ViewerTileRect]) -> list[ViewerTileRect]:
    pruned: list[ViewerTileRect] = []
    for i, rect in enumerate(free_rects):
        if any(i != j and viewer_tile_contains(other, rect) for j, other in enumerate(free_rects)):
            continue
        pruned.append(rect)
    return pruned


def score_viewer_bssf(free: ViewerTileRect, w: float, h: float) -> tuple[float, float, float]:
    leftover_w = free.w - w
    leftover_h = free.h - h
    return (min(leftover_w, leftover_h), max(leftover_w, leftover_h), free.y)


def score_viewer_baf(free: ViewerTileRect, w: float, h: float) -> tuple[float, float, float]:
    return (viewer_tile_area(free) - w * h, min(free.w - w, free.h - h), free.y)


def score_viewer_bl(free: ViewerTileRect, w: float, h: float) -> tuple[float, float, float]:
    return (free.y + h, free.x, viewer_tile_area(free) - w * h)


def pack_viewers_maxrects(
    items: Sequence[ViewerTileItem],
    area_w: int,
    area_h: int,
    score_func: Callable[[ViewerTileRect, float, float], tuple[float, float, float]],
) -> Optional[list[PlacedViewerTile]]:
    free_rects: list[ViewerTileRect] = [ViewerTileRect(0, 0, float(area_w), float(area_h))]
    placed: list[PlacedViewerTile] = []

    for item in items:
        need_w = item.w + IMAGE_VIEWER_TILE_GAP
        need_h = item.h + IMAGE_VIEWER_TILE_GAP
        best: Optional[tuple[tuple[float, float, float], ViewerTileRect]] = None
        for free in free_rects:
            if need_w <= free.w and need_h <= free.h:
                score = score_func(free, need_w, need_h)
                if best is None or score < best[0]:
                    best = (score, ViewerTileRect(free.x, free.y, need_w, need_h))
        if best is None:
            return None

        used = best[1]
        placed.append(PlacedViewerTile(item, ViewerTileRect(used.x, used.y, item.w, item.h)))
        next_free: list[ViewerTileRect] = []
        for free in free_rects:
            next_free.extend(split_viewer_free_rect(free, used))
        free_rects = prune_viewer_free_rects(next_free)

    return placed


def pack_viewers_shelf(items: Sequence[ViewerTileItem], area_w: int, area_h: int) -> Optional[list[PlacedViewerTile]]:
    shelves: list[dict[str, float]] = []
    placed: list[PlacedViewerTile] = []

    for item in items:
        need_w = item.w + IMAGE_VIEWER_TILE_GAP
        need_h = item.h + IMAGE_VIEWER_TILE_GAP
        if need_w > area_w or need_h > area_h:
            return None

        best_shelf: Optional[dict[str, float]] = None
        best_waste: Optional[float] = None
        for shelf in shelves:
            if shelf["used_w"] + need_w <= area_w and need_h <= shelf["h"]:
                waste = shelf["h"] - need_h
                if best_waste is None or waste < best_waste:
                    best_waste = waste
                    best_shelf = shelf

        if best_shelf is None:
            y = 0.0 if not shelves else max(shelf["y"] + shelf["h"] for shelf in shelves)
            if y + need_h > area_h:
                return None
            best_shelf = {"y": y, "h": need_h, "used_w": 0.0}
            shelves.append(best_shelf)

        x = best_shelf["used_w"]
        y = best_shelf["y"]
        placed.append(PlacedViewerTile(item, ViewerTileRect(x, y, item.w, item.h)))
        best_shelf["used_w"] += need_w

    return placed


def viewer_layout_bounds(layout: Sequence[PlacedViewerTile]) -> tuple[float, float, float, float]:
    min_x = min(placed.rect.x for placed in layout)
    min_y = min(placed.rect.y for placed in layout)
    max_x = max(placed.rect.x + placed.rect.w for placed in layout)
    max_y = max(placed.rect.y + placed.rect.h for placed in layout)
    return min_x, min_y, max_x, max_y


def make_scaled_viewer_items(viewers: Sequence[ImageViewerWindow], scale: float) -> list[ViewerTileItem]:
    items: list[ViewerTileItem] = []
    for viewer in viewers:
        if viewer.pixmap.isNull():
            continue
        src_w = max(1, viewer.pixmap.width())
        src_h = max(1, viewer.pixmap.height())
        left, top, right, bottom = viewer.frame_margins()
        extra_w = max(0, int(left + right))
        extra_h = max(0, int(top + bottom))
        effective_scale = max(
            float(scale),
            IMAGE_VIEWER_TILE_MIN_CLIENT_WIDTH / src_w,
            IMAGE_VIEWER_TILE_MIN_CLIENT_HEIGHT / src_h,
        )
        client_w = src_w * effective_scale
        client_h = src_h * effective_scale
        items.append(
            ViewerTileItem(
                viewer=viewer,
                src_w=src_w,
                src_h=src_h,
                frame_extra_w=extra_w,
                frame_extra_h=extra_h,
                client_w=client_w,
                client_h=client_h,
                w=client_w + extra_w,
                h=client_h + extra_h,
            )
        )
    return items


def ordered_viewer_tile_items(items: Sequence[ViewerTileItem]) -> Iterable[list[ViewerTileItem]]:
    key_funcs = [
        lambda item: item.w * item.h,
        lambda item: max(item.w, item.h),
        lambda item: item.h,
        lambda item: item.w,
        lambda item: abs(item.w - item.h),
        lambda item: item.w / max(item.h, 1.0),
        lambda item: item.h / max(item.w, 1.0),
    ]
    seen: set[tuple[int, ...]] = set()
    for key_func in key_funcs:
        ordered = sorted(items, key=key_func, reverse=True)
        signature = tuple(id(item.viewer) for item in ordered)
        if signature in seen:
            continue
        seen.add(signature)
        yield ordered


def try_pack_viewer_tiles(viewers: Sequence[ImageViewerWindow], area_w: int, area_h: int, scale: float) -> Optional[list[PlacedViewerTile]]:
    items = make_scaled_viewer_items(viewers, scale)
    if not items:
        return []
    if any(item.w + IMAGE_VIEWER_TILE_GAP > area_w or item.h + IMAGE_VIEWER_TILE_GAP > area_h for item in items):
        return None

    packers = [
        lambda ordered: pack_viewers_maxrects(ordered, area_w, area_h, score_viewer_bssf),
        lambda ordered: pack_viewers_maxrects(ordered, area_w, area_h, score_viewer_baf),
        lambda ordered: pack_viewers_maxrects(ordered, area_w, area_h, score_viewer_bl),
        lambda ordered: pack_viewers_shelf(ordered, area_w, area_h),
    ]

    best_layout: Optional[list[PlacedViewerTile]] = None
    best_score: Optional[tuple[float, float, float]] = None
    for ordered in ordered_viewer_tile_items(items):
        for packer in packers:
            layout = packer(ordered)
            if layout is None:
                continue
            _min_x, _min_y, max_x, max_y = viewer_layout_bounds(layout)
            score = (max_x * max_y, max_y, max_x)
            if best_score is None or score < best_score:
                best_score = score
                best_layout = layout
    return best_layout


def calculate_best_viewer_tile_layout(viewers: Sequence[ImageViewerWindow], available: QRect) -> list[tuple[ImageViewerWindow, QRect]]:
    visible_viewers = [viewer for viewer in viewers if viewer.isVisible() and not viewer.pixmap.isNull()]
    if not visible_viewers or available.width() <= 0 or available.height() <= 0:
        return []

    area_w = max(1, available.width())
    area_h = max(1, available.height())
    total_image_area = sum(max(1, viewer.pixmap.width()) * max(1, viewer.pixmap.height()) for viewer in visible_viewers)
    if total_image_area <= 0:
        return []

    single_high_values: list[float] = []
    for viewer in visible_viewers:
        left, top, right, bottom = viewer.frame_margins()
        extra_w = max(0, int(left + right))
        extra_h = max(0, int(top + bottom))
        src_w = max(1, viewer.pixmap.width())
        src_h = max(1, viewer.pixmap.height())
        if area_w <= extra_w or area_h <= extra_h:
            return []
        single_high_values.append(min((area_w - extra_w) / src_w, (area_h - extra_h) / src_h))

    single_high = min(single_high_values)
    area_high = (area_w * area_h / total_image_area) ** 0.5
    high = max(0.01, min(single_high, area_high) * 1.05)
    low = 0.01
    best_layout: Optional[list[PlacedViewerTile]] = None

    for _ in range(45):
        mid = (low + high) / 2.0
        layout = try_pack_viewer_tiles(visible_viewers, area_w, area_h, mid)
        if layout is not None:
            best_layout = layout
            low = mid
        else:
            high = mid

    if not best_layout:
        return []

    min_x, min_y, max_x, max_y = viewer_layout_bounds(best_layout)
    used_w = max_x - min_x
    used_h = max_y - min_y
    offset_x = available.x() + (area_w - used_w) / 2.0 - min_x
    offset_y = available.y() + (area_h - used_h) / 2.0 - min_y

    result: list[tuple[ImageViewerWindow, QRect]] = []
    for placed in best_layout:
        rect = placed.rect
        frame_rect = QRect(
            int(round(rect.x + offset_x)),
            int(round(rect.y + offset_y)),
            max(1, int(round(rect.w))),
            max(1, int(round(rect.h))),
        )
        result.append((placed.item.viewer, frame_rect))
    return result


class CollapsibleGroupBox(QGroupBox):
    collapsedChanged = Signal(str, bool)

    def __init__(self, title: str, state_key: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.plain_title = title
        self.state_key = state_key
        self._collapsed = False
        self._saved_maximum_height = self.maximumHeight()
        self.setTitle(f"▼ {self.plain_title}")

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool, emit_signal: bool = True) -> None:
        collapsed = bool(collapsed)
        if self._collapsed == collapsed:
            self._apply_collapsed_visual()
            return
        self._collapsed = collapsed
        self._apply_collapsed_visual()
        if emit_signal:
            self.collapsedChanged.emit(self.state_key, self._collapsed)

    def _collapsed_height(self) -> int:
        return max(30, self.fontMetrics().height() + 12)

    def set_plain_title(self, title: str) -> None:
        self.plain_title = str(title)
        self._apply_collapsed_visual()

    def _apply_collapsed_visual(self) -> None:
        self.setTitle(("▶ " if self._collapsed else "▼ ") + self.plain_title)
        layout = self.layout()
        if layout is not None:
            self._set_layout_visible(layout, not self._collapsed)
        if self._collapsed:
            self.setMaximumHeight(self._collapsed_height())
        else:
            self.setMaximumHeight(16777215)
        self.updateGeometry()

    def _set_layout_visible(self, layout: QLayout, visible: bool) -> None:
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setVisible(visible)
            child_layout = item.layout()
            if child_layout is not None:
                self._set_layout_visible(child_layout, visible)

    def mousePressEvent(self, event):  # noqa: N802 - Qt naming
        pos = event.position() if hasattr(event, "position") else event.pos()
        x = pos.x()
        y = pos.y()
        title_click_width = self.fontMetrics().horizontalAdvance(self.title()) + 28
        if y <= self._collapsed_height() and x <= title_click_width:
            self.set_collapsed(not self._collapsed)
            event.accept()
            return
        super().mousePressEvent(event)

class TagManagerDialog(QDialog):
    def __init__(self, db: Database, color_provider: Callable[[str], str], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.db = db
        self.color_provider = color_provider
        self.current_tag_id: Optional[int] = None
        self.current_preset_id: Optional[int] = None
        self.current_meta_field: str = ""
        self.current_meta_value: str = ""
        self.setWindowTitle("タグ管理")
        self.resize(900, 620)
        self.build_ui()
        self.refresh_categories()
        self.refresh_tag_list()
        self.refresh_preset_list()
        self.refresh_meta_option_list()

    def build_ui(self) -> None:
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        tag_tab = QWidget()
        tag_root = QHBoxLayout(tag_tab)
        self.tag_list = QListWidget()
        self.tag_list.setMinimumWidth(290)
        tag_root.addWidget(self.tag_list, 1)

        tag_form_box = QGroupBox("タグ編集")
        tag_form = QGridLayout(tag_form_box)
        self.tag_name_edit = QLineEdit()
        self.tag_category_combo = QComboBox()
        self.tag_category_combo.setEditable(True)
        self.tag_color_edit = QLineEdit()
        self.tag_color_edit.setPlaceholderText("空ならカテゴリ色")
        self.tag_color_button = QPushButton("タグ色")
        self.tag_visible_check = QCheckBox("表示する")
        self.tag_visible_check.setChecked(True)
        self.category_color_edit = QLineEdit()
        self.category_color_button = QPushButton("カテゴリ色")
        self.new_tag_button = QPushButton("新規")
        self.save_tag_button = QPushButton("保存")
        self.delete_tag_button = QPushButton("削除")

        tag_form.addWidget(QLabel("タグ名"), 0, 0)
        tag_form.addWidget(self.tag_name_edit, 0, 1, 1, 3)
        tag_form.addWidget(QLabel("カテゴリ"), 1, 0)
        tag_form.addWidget(self.tag_category_combo, 1, 1, 1, 3)
        tag_form.addWidget(QLabel("タグ色"), 2, 0)
        tag_form.addWidget(self.tag_color_edit, 2, 1)
        tag_form.addWidget(self.tag_color_button, 2, 2)
        tag_form.addWidget(QLabel("カテゴリ色"), 3, 0)
        tag_form.addWidget(self.category_color_edit, 3, 1)
        tag_form.addWidget(self.category_color_button, 3, 2)
        tag_form.addWidget(self.tag_visible_check, 4, 1, 1, 3)
        tag_btn_row = QHBoxLayout()
        tag_btn_row.addWidget(self.new_tag_button)
        tag_btn_row.addWidget(self.save_tag_button)
        tag_btn_row.addWidget(self.delete_tag_button)
        tag_btn_row.addStretch(1)
        tag_form.addLayout(tag_btn_row, 5, 0, 1, 4)
        tag_form.setRowStretch(6, 1)
        tag_root.addWidget(tag_form_box, 2)
        tabs.addTab(tag_tab, "タグ")

        preset_tab = QWidget()
        preset_root = QHBoxLayout(preset_tab)
        self.preset_list = QListWidget()
        self.preset_list.setMinimumWidth(290)
        preset_root.addWidget(self.preset_list, 1)

        preset_form_box = QGroupBox("タグプリセット編集")
        preset_form = QVBoxLayout(preset_form_box)
        preset_form.addWidget(QLabel("プリセット名"))
        self.preset_name_edit = QLineEdit()
        preset_form.addWidget(self.preset_name_edit)
        preset_form.addWidget(QLabel("含めるタグ"))
        self.preset_tags_editor = TagChipEditor(color_provider=self.color_provider, tag_resolver=self.db.canonical_tag_name)
        preset_form.addWidget(self.preset_tags_editor)
        preset_btn_row = QHBoxLayout()
        self.new_preset_button = QPushButton("新規")
        self.save_preset_button = QPushButton("保存")
        self.delete_preset_button = QPushButton("削除")
        preset_btn_row.addWidget(self.new_preset_button)
        preset_btn_row.addWidget(self.save_preset_button)
        preset_btn_row.addWidget(self.delete_preset_button)
        preset_btn_row.addStretch(1)
        preset_form.addLayout(preset_btn_row)
        preset_form.addStretch(1)
        preset_root.addWidget(preset_form_box, 2)
        tabs.addTab(preset_tab, "タグプリセット")

        meta_tab = QWidget()
        meta_root = QHBoxLayout(meta_tab)
        self.meta_option_list = QListWidget()
        self.meta_option_list.setMinimumWidth(290)
        meta_root.addWidget(self.meta_option_list, 1)

        meta_form_box = QGroupBox("入力候補編集")
        meta_form = QGridLayout(meta_form_box)
        self.meta_field_combo = QComboBox()
        self.meta_field_combo.addItems([META_OPTION_LABELS[field] for field in META_OPTION_FIELDS])
        self.meta_value_edit = QLineEdit()
        self.new_meta_option_button = QPushButton("新規")
        self.save_meta_option_button = QPushButton("保存")
        self.delete_meta_option_button = QPushButton("削除")
        meta_form.addWidget(QLabel("種類"), 0, 0)
        meta_form.addWidget(self.meta_field_combo, 0, 1, 1, 3)
        meta_form.addWidget(QLabel("値"), 1, 0)
        meta_form.addWidget(self.meta_value_edit, 1, 1, 1, 3)
        meta_btn_row = QHBoxLayout()
        meta_btn_row.addWidget(self.new_meta_option_button)
        meta_btn_row.addWidget(self.save_meta_option_button)
        meta_btn_row.addWidget(self.delete_meta_option_button)
        meta_btn_row.addStretch(1)
        meta_form.addLayout(meta_btn_row, 2, 0, 1, 4)
        meta_form.setRowStretch(3, 1)
        meta_root.addWidget(meta_form_box, 2)
        tabs.addTab(meta_tab, "入力候補")

        close_button = QPushButton("閉じる")
        close_button.clicked.connect(self.accept)
        root.addWidget(close_button, alignment=Qt.AlignRight)

        self.tag_list.currentItemChanged.connect(self.on_tag_selected)
        self.tag_category_combo.currentTextChanged.connect(self.on_category_text_changed)
        self.tag_color_button.clicked.connect(lambda: self.pick_color(self.tag_color_edit))
        self.category_color_button.clicked.connect(lambda: self.pick_color(self.category_color_edit))
        self.new_tag_button.clicked.connect(self.new_tag)
        self.save_tag_button.clicked.connect(self.save_tag)
        self.delete_tag_button.clicked.connect(self.delete_tag)

        self.preset_list.currentItemChanged.connect(self.on_preset_selected)
        self.new_preset_button.clicked.connect(self.new_preset)
        self.save_preset_button.clicked.connect(self.save_preset)
        self.delete_preset_button.clicked.connect(self.delete_preset)

        self.meta_option_list.currentItemChanged.connect(self.on_meta_option_selected)
        self.new_meta_option_button.clicked.connect(self.new_meta_option)
        self.save_meta_option_button.clicked.connect(self.save_meta_option)
        self.delete_meta_option_button.clicked.connect(self.delete_meta_option)

    def refresh_categories(self) -> None:
        current = self.tag_category_combo.currentText().strip()
        self.tag_category_combo.blockSignals(True)
        self.tag_category_combo.clear()
        for row in self.db.list_categories():
            self.tag_category_combo.addItem(str(row["name"]))
        if current:
            index = self.tag_category_combo.findText(current)
            if index >= 0:
                self.tag_category_combo.setCurrentIndex(index)
            else:
                self.tag_category_combo.setEditText(current)
        self.tag_category_combo.blockSignals(False)

    def refresh_tag_list(self) -> None:
        selected_id = self.current_tag_id
        self.tag_list.blockSignals(True)
        self.tag_list.clear()
        for row in self.db.list_tags_with_counts():
            name = str(row["name"])
            category = str(row["category"])
            count = int(row["count"])
            visible = int(row["visible"] if "visible" in row.keys() else 1)
            hidden = "" if visible else "   [非表示]"
            label = f"{name}   [{category}]   ({count}){hidden}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, int(row["id"]))
            item.setIcon(colored_square_icon(effective_color_from_row(row), QSize(16, 16)))
            self.tag_list.addItem(item)
            if selected_id == int(row["id"]):
                self.tag_list.setCurrentItem(item)
        self.tag_list.blockSignals(False)

    def refresh_preset_list(self) -> None:
        selected_id = self.current_preset_id
        self.preset_list.blockSignals(True)
        self.preset_list.clear()
        for row in self.db.list_tag_presets():
            tags = tags_from_json(str(row["tags_json"]))
            item = QListWidgetItem(f"{row['name']}   ({len(tags)})")
            item.setData(Qt.UserRole, int(row["id"]))
            self.preset_list.addItem(item)
            if selected_id == int(row["id"]):
                self.preset_list.setCurrentItem(item)
        self.preset_list.blockSignals(False)

    def on_tag_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        tag_id = int(current.data(Qt.UserRole))
        row = self.db.get_tag(tag_id)
        if not row:
            return
        self.current_tag_id = tag_id
        category = str(row["category"] or "custom")
        self.tag_name_edit.setText(str(row["name"]))
        index = self.tag_category_combo.findText(category)
        if index >= 0:
            self.tag_category_combo.setCurrentIndex(index)
        else:
            self.tag_category_combo.setEditText(category)
        self.tag_color_edit.setText(str(row["color"] or ""))
        self.tag_visible_check.setChecked(int(row["visible"] if "visible" in row.keys() else 1) != 0)
        self.category_color_edit.setText(self.db.get_category_color(category))

    def on_category_text_changed(self, text: str) -> None:
        category = normalize_category(text) or "custom"
        self.category_color_edit.setText(self.db.get_category_color(category))

    def new_tag(self) -> None:
        self.current_tag_id = None
        self.tag_list.clearSelection()
        self.tag_name_edit.clear()
        self.tag_category_combo.setEditText("custom")
        self.tag_color_edit.clear()
        self.tag_visible_check.setChecked(True)
        self.category_color_edit.setText(self.db.get_category_color("custom"))
        self.tag_name_edit.setFocus()

    def save_tag(self) -> None:
        try:
            category = normalize_category(self.tag_category_combo.currentText()) or "custom"
            self.db.set_category_color(category, self.category_color_edit.text())
            self.current_tag_id = self.db.update_tag(
                self.current_tag_id,
                self.tag_name_edit.text(),
                category,
                self.tag_color_edit.text(),
                self.tag_visible_check.isChecked(),
            )
            self.refresh_categories()
            self.refresh_tag_list()
            self.refresh_preset_list()
        except sqlite3.IntegrityError as exc:
            QMessageBox.warning(self, "保存エラー", f"タグ名が重複している可能性があります。\n\n{exc}")
        except Exception as exc:
            QMessageBox.warning(self, "保存エラー", str(exc))

    def delete_tag(self) -> None:
        if self.current_tag_id is None:
            return
        result = QMessageBox.question(
            self,
            "タグ削除確認",
            "このタグを削除しますか？\nプロンプトとの紐づけと、タグプリセット内の同名タグも削除されます。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return
        self.db.delete_tag(self.current_tag_id)
        self.current_tag_id = None
        self.new_tag()
        self.refresh_tag_list()
        self.refresh_preset_list()

    def on_preset_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        preset_id = int(current.data(Qt.UserRole))
        row = self.db.conn.execute("SELECT * FROM tag_presets WHERE id = ?", (preset_id,)).fetchone()
        if not row:
            return
        self.current_preset_id = preset_id
        self.preset_name_edit.setText(str(row["name"]))
        self.preset_tags_editor.set_tags(tags_from_json(str(row["tags_json"])))

    def new_preset(self) -> None:
        self.current_preset_id = None
        self.preset_list.clearSelection()
        self.preset_name_edit.clear()
        self.preset_tags_editor.set_tags([])
        self.preset_name_edit.setFocus()

    def save_preset(self) -> None:
        try:
            self.current_preset_id = self.db.save_tag_preset(
                self.current_preset_id,
                self.preset_name_edit.text(),
                self.preset_tags_editor.get_tags(),
            )
            self.refresh_categories()
            self.refresh_tag_list()
            self.refresh_preset_list()
        except sqlite3.IntegrityError as exc:
            QMessageBox.warning(self, "保存エラー", f"プリセット名が重複している可能性があります。\n\n{exc}")
        except Exception as exc:
            QMessageBox.warning(self, "保存エラー", str(exc))

    def delete_preset(self) -> None:
        if self.current_preset_id is None:
            return
        result = QMessageBox.question(
            self,
            "プリセット削除確認",
            "このタグプリセットを削除しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return
        self.db.delete_tag_preset(self.current_preset_id)
        self.current_preset_id = None
        self.new_preset()
        self.refresh_preset_list()

    def refresh_meta_option_list(self) -> None:
        selected = (self.current_meta_field, self.current_meta_value)
        self.meta_option_list.blockSignals(True)
        self.meta_option_list.clear()
        for row in self.db.list_meta_options():
            field = str(row["field"])
            value = str(row["value"])
            item = QListWidgetItem(f"{meta_field_label(field)}: {value}")
            item.setData(Qt.UserRole, (field, value))
            self.meta_option_list.addItem(item)
            if selected == (field, value):
                self.meta_option_list.setCurrentItem(item)
        self.meta_option_list.blockSignals(False)

    def on_meta_option_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        field, value = current.data(Qt.UserRole)
        self.current_meta_field = normalize_meta_field(field)
        self.current_meta_value = normalize_meta_value(value)
        label = meta_field_label(self.current_meta_field)
        index = self.meta_field_combo.findText(label)
        if index >= 0:
            self.meta_field_combo.setCurrentIndex(index)
        self.meta_value_edit.setText(self.current_meta_value)

    def new_meta_option(self) -> None:
        self.current_meta_field = ""
        self.current_meta_value = ""
        self.meta_option_list.clearSelection()
        if self.meta_field_combo.count() > 0:
            self.meta_field_combo.setCurrentIndex(0)
        self.meta_value_edit.clear()
        self.meta_value_edit.setFocus()

    def save_meta_option(self) -> None:
        try:
            field = normalize_meta_field(self.meta_field_combo.currentText())
            value = self.meta_value_edit.text()
            self.db.save_meta_option(self.current_meta_field, self.current_meta_value, field, value)
            self.current_meta_field = field
            self.current_meta_value = normalize_meta_value(value)
            self.refresh_meta_option_list()
        except sqlite3.IntegrityError as exc:
            QMessageBox.warning(self, "保存エラー", f"入力候補が重複している可能性があります。\n\n{exc}")
        except Exception as exc:
            QMessageBox.warning(self, "保存エラー", str(exc))

    def delete_meta_option(self) -> None:
        if not self.current_meta_field or not self.current_meta_value:
            return
        result = QMessageBox.question(
            self,
            "入力候補削除確認",
            "この入力候補を削除しますか？\n既存プロンプトの入力済みテキストは変更しません。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return
        self.db.delete_meta_option(self.current_meta_field, self.current_meta_value)
        self.current_meta_field = ""
        self.current_meta_value = ""
        self.new_meta_option()
        self.refresh_meta_option_list()

    def pick_color(self, line_edit: QLineEdit) -> None:
        current = normalize_hex_color(line_edit.text()) or "#777777"
        color = QColorDialog.getColor(QColor(current), self, "色を選択")
        if color.isValid():
            line_edit.setText(color.name())



class MaterialLabelManagerDialog(QDialog):
    def __init__(self, db: Database, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.db = db
        self.fg_edits: dict[int, QLineEdit] = {}
        self.bg_edits: dict[int, QLineEdit] = {}
        self.preview_labels: dict[int, QLabel] = {}
        self.setWindowTitle("ラベル管理")
        self.resize(620, 360)
        self.build_ui()
        self.load_values()

    def build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(QLabel("メディアラベル 1〜9 の文字色と背景色を設定します。"))

        grid = QGridLayout()
        grid.addWidget(QLabel("ラベル"), 0, 0)
        grid.addWidget(QLabel("文字色"), 0, 1)
        grid.addWidget(QLabel("背景色"), 0, 3)
        grid.addWidget(QLabel("プレビュー"), 0, 5)

        for label_id in range(1, 10):
            fg_edit = QLineEdit()
            bg_edit = QLineEdit()
            fg_button = QPushButton("選択")
            bg_button = QPushButton("選択")
            preview = QLabel(f"ラベル {label_id}")
            preview.setAlignment(Qt.AlignCenter)
            preview.setMinimumWidth(120)

            self.fg_edits[label_id] = fg_edit
            self.bg_edits[label_id] = bg_edit
            self.preview_labels[label_id] = preview

            grid.addWidget(QLabel(str(label_id)), label_id, 0)
            grid.addWidget(fg_edit, label_id, 1)
            grid.addWidget(fg_button, label_id, 2)
            grid.addWidget(bg_edit, label_id, 3)
            grid.addWidget(bg_button, label_id, 4)
            grid.addWidget(preview, label_id, 5)

            fg_button.clicked.connect(lambda checked=False, i=label_id: self.pick_color(self.fg_edits[i]))
            bg_button.clicked.connect(lambda checked=False, i=label_id: self.pick_color(self.bg_edits[i]))
            fg_edit.textChanged.connect(lambda _text="", i=label_id: self.update_preview(i))
            bg_edit.textChanged.connect(lambda _text="", i=label_id: self.update_preview(i))

        root.addLayout(grid)

        button_row = QHBoxLayout()
        reset_button = QPushButton("初期値に戻す")
        save_button = QPushButton("保存して閉じる")
        close_button = QPushButton("閉じる")
        reset_button.clicked.connect(self.reset_defaults)
        save_button.clicked.connect(self.save_and_accept)
        close_button.clicked.connect(self.reject)
        button_row.addWidget(reset_button)
        button_row.addStretch(1)
        button_row.addWidget(save_button)
        button_row.addWidget(close_button)
        root.addLayout(button_row)

    def setting_key(self, label_id: int, kind: str) -> str:
        return f"material_label_{label_id}_{kind}"

    def default_colors(self, label_id: int) -> tuple[str, str]:
        return DEFAULT_MATERIAL_LABEL_COLORS.get(label_id, ("#ffffff", "#555555"))

    def load_values(self) -> None:
        for label_id in range(1, 10):
            default_fg, default_bg = self.default_colors(label_id)
            fg = normalize_hex_color(self.db.get_setting(self.setting_key(label_id, "fg"), default_fg)) or default_fg
            bg = normalize_hex_color(self.db.get_setting(self.setting_key(label_id, "bg"), default_bg)) or default_bg
            self.fg_edits[label_id].setText(fg)
            self.bg_edits[label_id].setText(bg)
            self.update_preview(label_id)

    def reset_defaults(self) -> None:
        for label_id in range(1, 10):
            fg, bg = self.default_colors(label_id)
            self.fg_edits[label_id].setText(fg)
            self.bg_edits[label_id].setText(bg)
            self.update_preview(label_id)

    def pick_color(self, edit: QLineEdit) -> None:
        initial = QColor(normalize_hex_color(edit.text()) or "#ffffff")
        color = QColorDialog.getColor(initial, self, "色を選択")
        if color.isValid():
            edit.setText(color.name())

    def update_preview(self, label_id: int) -> None:
        fg = normalize_hex_color(self.fg_edits[label_id].text()) or self.default_colors(label_id)[0]
        bg = normalize_hex_color(self.bg_edits[label_id].text()) or self.default_colors(label_id)[1]
        self.preview_labels[label_id].setStyleSheet(f"color: {fg}; background-color: {bg}; padding: 4px; border-radius: 3px;")

    def save_and_accept(self) -> None:
        for label_id in range(1, 10):
            default_fg, default_bg = self.default_colors(label_id)
            fg = normalize_hex_color(self.fg_edits[label_id].text()) or default_fg
            bg = normalize_hex_color(self.bg_edits[label_id].text()) or default_bg
            self.db.set_setting(self.setting_key(label_id, "fg"), fg)
            self.db.set_setting(self.setting_key(label_id, "bg"), bg)
        self.accept()



class WorkspaceDeleteWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(bool, str, object)

    def __init__(
        self,
        db_path: str,
        backup_path: str,
        workspace_id: int,
        fallback_workspace_id: int,
        active_workspace_id: int,
        asset_target_paths: list[str],
    ):
        super().__init__()
        self.db_path = db_path
        self.backup_path = backup_path
        self.workspace_id = int(workspace_id)
        self.fallback_workspace_id = int(fallback_workspace_id)
        self.active_workspace_id = int(active_workspace_id)
        self.asset_target_paths = [Path(path) for path in asset_target_paths]

    def run(self) -> None:
        result = {
            "backup_path": self.backup_path,
            "moved_assets": 0,
            "asset_errors": [],
            "integrity": "",
            "db_deleted": False,
        }
        conn: sqlite3.Connection | None = None
        try:
            self.progress.emit(3, "DBバックアップを作成中...")
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.commit()

            backup_conn = sqlite3.connect(self.backup_path)
            try:
                conn.backup(backup_conn)
            finally:
                backup_conn.close()

            self.progress.emit(25, "DBからワークスペースを削除中...")
            conn.execute("BEGIN IMMEDIATE")
            workspace_row = conn.execute("SELECT id FROM workspaces WHERE id = ?", (self.workspace_id,)).fetchone()
            if workspace_row is None:
                raise RuntimeError("削除対象ワークスペースが見つかりません。")
            workspace_count = int(conn.execute("SELECT COUNT(*) AS c FROM workspaces").fetchone()["c"])
            if workspace_count <= 1:
                raise RuntimeError("最後のワークスペースは削除できません。")
            fallback_row = conn.execute("SELECT id FROM workspaces WHERE id = ?", (self.fallback_workspace_id,)).fetchone()
            if fallback_row is None or self.fallback_workspace_id == self.workspace_id:
                fallback_row = conn.execute("SELECT id FROM workspaces WHERE id != ? ORDER BY sort_order ASC, id ASC LIMIT 1", (self.workspace_id,)).fetchone()
                if fallback_row is None:
                    raise RuntimeError("切り替え先ワークスペースが見つかりません。")
                self.fallback_workspace_id = int(fallback_row["id"])

            conn.execute(
                "DELETE FROM prompt_tags WHERE prompt_id IN (SELECT id FROM prompts WHERE workspace_id = ?)",
                (self.workspace_id,),
            )
            conn.execute(
                "DELETE FROM images WHERE prompt_id IN (SELECT id FROM prompts WHERE workspace_id = ?)",
                (self.workspace_id,),
            )
            conn.execute("DELETE FROM prompts WHERE workspace_id = ?", (self.workspace_id,))
            conn.execute("DELETE FROM tag_presets WHERE workspace_id = ?", (self.workspace_id,))
            conn.execute("DELETE FROM tags WHERE workspace_id = ?", (self.workspace_id,))
            conn.execute("DELETE FROM workspaces WHERE id = ?", (self.workspace_id,))
            if self.active_workspace_id == self.workspace_id:
                conn.execute(
                    "INSERT INTO settings(key, value) VALUES('current_workspace_id', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (str(self.fallback_workspace_id),),
                )

            remaining = {
                "workspaces": int(conn.execute("SELECT COUNT(*) AS c FROM workspaces WHERE id = ?", (self.workspace_id,)).fetchone()["c"]),
                "prompts": int(conn.execute("SELECT COUNT(*) AS c FROM prompts WHERE workspace_id = ?", (self.workspace_id,)).fetchone()["c"]),
                "tags": int(conn.execute("SELECT COUNT(*) AS c FROM tags WHERE workspace_id = ?", (self.workspace_id,)).fetchone()["c"]),
                "tag_presets": int(conn.execute("SELECT COUNT(*) AS c FROM tag_presets WHERE workspace_id = ?", (self.workspace_id,)).fetchone()["c"]),
            }
            if any(value != 0 for value in remaining.values()):
                raise RuntimeError(f"DB削除後の件数が0になっていません: {remaining}")
            integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
            result["integrity"] = integrity
            if integrity.lower() != "ok":
                raise RuntimeError(f"DB整合性チェックに失敗しました: {integrity}")
            conn.commit()
            result["db_deleted"] = True

            total_targets = len(self.asset_target_paths)
            if total_targets == 0:
                self.progress.emit(95, "削除後の確認中...")
            else:
                for index, path in enumerate(self.asset_target_paths, start=1):
                    progress = 35 + int((index / max(1, total_targets)) * 55)
                    self.progress.emit(progress, f"メディアをゴミ箱へ移動中... [{index}/{total_targets}] {path.name}")
                    try:
                        if path.exists() and move_path_to_recycle_bin(path):
                            result["moved_assets"] += 1
                    except Exception as exc:
                        result["asset_errors"].append(f"{path}: {exc}")

            self.progress.emit(100, "完了")
            if result["asset_errors"]:
                self.finished.emit(False, "DBから削除しましたが、一部メディアをゴミ箱へ移動できませんでした。", result)
            else:
                self.finished.emit(True, "ワークスペースを削除しました。", result)
        except Exception as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self.finished.emit(False, str(exc), result)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass


class WorkspaceManagerDialog(QDialog):
    def __init__(self, db: Database, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.db = db
        self.current_workspace_id: Optional[int] = None
        self.loading = False
        self.setWindowTitle("ワークスペース管理")
        self.resize(560, 420)

        root = QVBoxLayout(self)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("ワークスペース"))
        self.workspace_combo = QComboBox()
        top_row.addWidget(self.workspace_combo, 1)
        self.new_button = QPushButton("新規")
        top_row.addWidget(self.new_button)
        root.addLayout(top_row)

        form = QGridLayout()
        self.name_edit = QLineEdit()
        self.thumb_check = QCheckBox("カードリストにサムネ表示")
        self.select1_edit = QLineEdit()
        self.select2_edit = QLineEdit()
        self.select3_edit = QLineEdit()
        self.text1_edit = QLineEdit()
        self.text2_edit = QLineEdit()
        self.text3_edit = QLineEdit()

        row = 0
        form.addWidget(QLabel("ワークスペース名"), row, 0)
        form.addWidget(self.name_edit, row, 1)
        row += 1
        form.addWidget(QLabel(""), row, 0)
        form.addWidget(self.thumb_check, row, 1)
        row += 1
        form.addWidget(QLabel("選択項目1"), row, 0)
        form.addWidget(self.select1_edit, row, 1)
        row += 1
        form.addWidget(QLabel("選択項目2"), row, 0)
        form.addWidget(self.select2_edit, row, 1)
        row += 1
        form.addWidget(QLabel("選択項目3"), row, 0)
        form.addWidget(self.select3_edit, row, 1)
        row += 1
        form.addWidget(QLabel("本文項目1"), row, 0)
        form.addWidget(self.text1_edit, row, 1)
        row += 1
        form.addWidget(QLabel("本文項目2"), row, 0)
        form.addWidget(self.text2_edit, row, 1)
        row += 1
        form.addWidget(QLabel("本文項目3"), row, 0)
        form.addWidget(self.text3_edit, row, 1)
        form.setColumnStretch(1, 1)
        root.addLayout(form)

        button_row = QHBoxLayout()
        self.delete_button = QPushButton("削除")
        self.save_button = QPushButton("保存")
        self.close_button = QPushButton("閉じる")
        button_row.addWidget(self.delete_button)
        button_row.addStretch(1)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.close_button)
        root.addLayout(button_row)

        self.workspace_combo.currentIndexChanged.connect(self.on_workspace_changed)
        self.new_button.clicked.connect(self.create_workspace)
        self.delete_button.clicked.connect(self.delete_current_workspace)
        self.save_button.clicked.connect(self.save_current_workspace)
        self.close_button.clicked.connect(self.accept)
        self.reload_workspaces()

    def reload_workspaces(self, select_id: int | None = None) -> None:
        self.loading = True
        try:
            self.workspace_combo.clear()
            rows = self.db.list_workspaces()
            if select_id is None:
                select_id = self.current_workspace_id or self.db.current_workspace_id()
            selected_index = 0
            for index, row in enumerate(rows):
                workspace_id = int(row["id"])
                self.workspace_combo.addItem(str(row["name"]), workspace_id)
                if workspace_id == int(select_id):
                    selected_index = index
            if self.workspace_combo.count() > 0:
                self.workspace_combo.setCurrentIndex(selected_index)
        finally:
            self.loading = False
        self.on_workspace_changed()

    def on_workspace_changed(self) -> None:
        if self.loading:
            return
        workspace_id = self.workspace_combo.currentData()
        if workspace_id is None:
            return
        self.current_workspace_id = int(workspace_id)
        row = self.db.get_workspace(self.current_workspace_id)
        if row is None:
            return
        self.name_edit.setText(str(row["name"]))
        self.thumb_check.setChecked(bool(int(row["show_card_thumbnail"])))
        self.select1_edit.setText(str(row["select_field_1_label"]))
        self.select2_edit.setText(str(row["select_field_2_label"]))
        self.select3_edit.setText(str(row["select_field_3_label"]))
        self.text1_edit.setText(str(row["text_field_1_label"]))
        self.text2_edit.setText(str(row["text_field_2_label"]))
        self.text3_edit.setText(str(row["text_field_3_label"]))
        self.delete_button.setEnabled(self.workspace_combo.count() > 1)

    def create_workspace(self) -> None:
        new_id = self.db.create_workspace()
        self.reload_workspaces(new_id)

    def save_current_workspace(self) -> None:
        if self.current_workspace_id is None:
            return
        try:
            self.db.update_workspace(
                self.current_workspace_id,
                {
                    "name": self.name_edit.text(),
                    "show_card_thumbnail": self.thumb_check.isChecked(),
                    "select_field_1_label": self.select1_edit.text(),
                    "select_field_2_label": self.select2_edit.text(),
                    "select_field_3_label": self.select3_edit.text(),
                    "text_field_1_label": self.text1_edit.text(),
                    "text_field_2_label": self.text2_edit.text(),
                    "text_field_3_label": self.text3_edit.text(),
                },
            )
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "ワークスペース管理", "同じ名前のワークスペースが既にあります。")
            return
        except Exception as exc:
            QMessageBox.warning(self, "ワークスペース管理", f"保存できませんでした。\n{exc}")
            return
        self.reload_workspaces(self.current_workspace_id)

    def delete_current_workspace(self) -> None:
        if self.current_workspace_id is None:
            return
        parent = self.parent()
        if parent is None or not hasattr(parent, "delete_workspace_with_confirmation"):
            QMessageBox.warning(self, "ワークスペース削除", "削除処理を開始できませんでした。")
            return
        parent.delete_workspace_with_confirmation(int(self.current_workspace_id), self)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.base_dir = get_base_dir()
        self.db_path = resolve_database_path(self.base_dir)
        self.assets_dir = self.base_dir / "assets"
        self.legacy_images_dir = self.assets_dir / "images"
        self.legacy_files_dir = self.assets_dir / "files"
        self.legacy_thumbs_dir = self.assets_dir / "thumbnails"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir = self.base_dir / BACKUP_DIR_NAME

        self.db = Database(self.db_path)
        self.current_workspace_id = self.db.current_workspace_id()
        self._workspace_combo_loading = False
        self.run_daily_backup_if_needed()
        self.migrate_legacy_asset_layout()
        self.migrate_material_paths_to_relative()
        self.current_prompt_id: Optional[int] = None
        self._prompt_selection_syncing = False
        self.loading = False
        self.tag_list_loading = False
        self.dirty = False
        self.tag_filter_buttons: list[QToolButton] = []
        self.tag_color_map: dict[str, str] = {}
        self.tag_presets: dict[str, list[str]] = {}
        self.collapsible_sections: list[CollapsibleGroupBox] = []
        self.warned_invalid_image_folder_files: set[str] = set()
        self._pending_pinned_area_update = False
        self.current_font_size = max(9, min(25, safe_int(self.db.get_setting("font_size", "10"), 10)))
        self.font_size_actions: dict[int, QAction] = {}
        self.image_viewer_resize_method = normalize_image_viewer_resize_method(
            self.db.get_setting("image_viewer_resize_method", DEFAULT_IMAGE_VIEWER_RESIZE_METHOD)
        )
        self.image_viewer_resize_method_actions: dict[str, QAction] = {}
        self.prompt_sort_mode = normalize_prompt_sort_mode(self.db.get_setting("prompt_sort_mode", DEFAULT_PROMPT_SORT_MODE))
        self.prompt_sort_actions: dict[str, QAction] = {}
        self.resident_mode = self.db.get_setting("resident_mode", "0") == "1"
        self.resident_mode_action: Optional[QAction] = None
        self.global_hotkey_enabled = self.db.get_setting(GLOBAL_HOTKEY_SETTING_KEY, "0") == "1"
        self.global_hotkey_action: Optional[QAction] = None
        self._global_hotkey_registered = False
        self._global_hotkey_backend = ""
        self._global_hotkey_hook_handle = None
        self._global_hotkey_hook_proc = None
        self._global_hotkey_down = False
        self.startup_action: Optional[QAction] = None
        self._force_quit = False
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self.tray_menu: Optional[QMenu] = None
        self._tray_click_timer: Optional[QTimer] = None
        self.ipc_server: Optional[QLocalServer] = None
        self._ipc_sockets: list[QLocalSocket] = []
        self.image_viewers: list[ImageViewerWindow] = []
        self._viewer_open_offset = 0
        self.material_label_styles = self.load_material_label_styles()

        self.material_load_chunk_size = 60
        self._material_load_timer = QTimer(self)
        self._material_load_timer.setInterval(0)
        self._material_load_timer.timeout.connect(self.process_material_load_chunk)
        self._material_load_rows: list[sqlite3.Row] = []
        self._material_load_index = 0
        self._material_load_prompt_id: Optional[int] = None

        self.thumbnail_rebuild_chunk_size = 3
        self._thumb_rebuild_timer = QTimer(self)
        self._thumb_rebuild_timer.setInterval(0)
        self._thumb_rebuild_timer.timeout.connect(self.process_thumbnail_rebuild_chunk)
        self._thumb_rebuild_rows: list[sqlite3.Row] = []
        self._thumb_rebuild_index = 0
        self._thumb_rebuild_prompt_id: Optional[int] = None
        self._thumb_rebuild_count = 0
        self._thumb_rebuild_errors: list[str] = []
        self._thumb_rebuild_old_thumbs: list[Path] = []

        self.setWindowTitle(APP_NAME)
        self.apply_window_icon()
        self.resize(1320, 900)
        self.setAcceptDrops(True)
        self.build_ui()
        self.refresh_workspace_selector()
        self.apply_workspace_settings()
        self.install_internal_material_drag_guard()
        self.build_menu()
        self.connect_signals()
        self.refresh_tags()
        self.reload_preset_combo()
        self.reload_meta_combos()
        self.apply_font_size(self.current_font_size, save=False)
        self.restore_ui_state()
        self.refresh_prompt_list()
        self.schedule_startup_left_splitter_restore()
        self.setup_tray_icon()
        self.update_quit_on_last_window_closed()
        self.register_global_hotkey_if_needed()
        self.setup_ipc_server()
        self.statusBar().showMessage(f"DB: {self.db_path}")

    def install_internal_material_drag_guard(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def is_text_drop_target(self, obj) -> bool:
        current = obj
        while current is not None:
            if isinstance(current, (QLineEdit, QTextEdit)):
                return True
            parent = current.parent() if hasattr(current, "parent") else None
            if parent is current:
                break
            current = parent
        return False

    def image_viewer_for_event_target(self, obj) -> Optional[ImageViewerWindow]:
        current = obj
        while current is not None:
            if isinstance(current, ImageViewerWindow):
                return current
            parent = current.parent() if hasattr(current, "parent") else None
            if parent is current:
                break
            current = parent
        active = QApplication.activeWindow()
        if isinstance(active, ImageViewerWindow):
            return active
        return None

    def eventFilter(self, obj, event):  # noqa: N802 - Qt naming
        if event.type() == QEvent.ShortcutOverride:
            viewer = self.image_viewer_for_event_target(obj)
            if viewer is not None and viewer.isVisible() and viewer.is_image_viewer_shortcut_event(event):
                # Alt+キーがメニューバー処理へ吸われないようにする。
                # 実行は後続の KeyPress / nativeEvent 側で行う。
                event.accept()
                return False

        if event.type() == QEvent.KeyPress:
            viewer = self.image_viewer_for_event_target(obj)
            if viewer is not None and viewer.isVisible() and viewer.handle_image_viewer_shortcut_event(event):
                return True

        if event.type() in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop):
            mime_data = event.mimeData() if hasattr(event, "mimeData") else None
            if mime_data is not None and mime_data.hasFormat(INTERNAL_MATERIAL_DRAG_MIME) and self.is_text_drop_target(obj):
                event.ignore()
                return True
        return super().eventFilter(obj, event)

    def apply_window_icon(self) -> None:
        icon = load_window_icon()
        if icon.isNull():
            return
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(icon)
        self.setWindowIcon(icon)

    def backup_database(self, manual: bool = False) -> Optional[Path]:
        if not self.db_path.exists():
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = unique_path(self.backup_dir / f"{timestamp}.db")
        self.db.backup_to(dest)
        return dest

    def run_daily_backup_if_needed(self) -> None:
        today = datetime.now().strftime("%Y%m%d")
        if self.db.get_setting("last_auto_backup_date", "") == today:
            return
        try:
            self.backup_database(manual=False)
            self.db.set_setting("last_auto_backup_date", today)
        except Exception:
            pass

    def run_manual_backup(self) -> None:
        try:
            if self.dirty:
                self.save_current_prompt()
            backup_path = self.backup_database(manual=True)
            if backup_path:
                QMessageBox.information(self, "バックアップ完了", f"DBをバックアップしました。\n{backup_path}")
            else:
                QMessageBox.warning(self, "バックアップ失敗", "バックアップ対象のDBが見つかりませんでした。")
        except Exception as exc:
            QMessageBox.warning(self, "バックアップ失敗", f"DBをバックアップできませんでした。\n\n{exc}")


    def build_workspace_delete_plan(self, workspace_id: int) -> WorkspaceDeletePlan:
        workspace_id = int(workspace_id)
        workspace = self.db.get_workspace(workspace_id)
        if workspace is None:
            raise ValueError("削除対象ワークスペースが見つかりません。")
        workspace_rows = self.db.list_workspaces()
        if len(workspace_rows) <= 1:
            raise ValueError("最後のワークスペースは削除できません。")
        fallback_workspace_id = next((int(row["id"]) for row in workspace_rows if int(row["id"]) != workspace_id), 0)
        if fallback_workspace_id <= 0:
            raise ValueError("切り替え先ワークスペースが見つかりません。")

        prompt_rows = self.db.conn.execute(
            "SELECT id FROM prompts WHERE workspace_id = ? ORDER BY id ASC",
            (workspace_id,),
        ).fetchall()
        prompt_ids = [int(row["id"]) for row in prompt_rows]
        media_rows = self.db.conn.execute(
            """
            SELECT i.*
            FROM images i
            INNER JOIN prompts p ON p.id = i.prompt_id
            WHERE p.workspace_id = ?
            ORDER BY i.id ASC
            """,
            (workspace_id,),
        ).fetchall()
        tag_count = int(self.db.conn.execute("SELECT COUNT(*) AS c FROM tags WHERE workspace_id = ?", (workspace_id,)).fetchone()["c"])
        preset_count = int(self.db.conn.execute("SELECT COUNT(*) AS c FROM tag_presets WHERE workspace_id = ?", (workspace_id,)).fetchone()["c"])

        other_ref_keys: set[str] = set()
        other_rows = self.db.conn.execute(
            """
            SELECT i.file_path, i.thumbnail_path
            FROM images i
            INNER JOIN prompts p ON p.id = i.prompt_id
            WHERE p.workspace_id != ?
            """,
            (workspace_id,),
        ).fetchall()
        for row in other_rows:
            for column in ("file_path", "thumbnail_path"):
                raw = str(row[column] or "")
                if not raw:
                    continue
                path = self.stored_path_to_absolute(raw)
                if path:
                    other_ref_keys.add(material_path_key(path))

        target_paths: list[Path] = []
        target_folder_keys: set[str] = set()
        for prompt_id in prompt_ids:
            prompt_dir = self.prompt_asset_dir(prompt_id)
            if prompt_dir.exists() and is_relative_to_path(prompt_dir, self.assets_dir):
                target_paths.append(prompt_dir)
                target_folder_keys.add(material_path_key(prompt_dir))

        def is_inside_target_folder(path: Path) -> bool:
            try:
                resolved = path.resolve()
            except Exception:
                resolved = Path(path)
            for parent in (resolved, *resolved.parents):
                if material_path_key(parent) in target_folder_keys:
                    return True
            return False

        for row in media_rows:
            for column in ("file_path", "thumbnail_path"):
                raw = str(row[column] if column in row.keys() else "")
                if not raw:
                    continue
                path = self.stored_path_to_absolute(raw)
                if not path.exists() or not is_relative_to_path(path, self.assets_dir):
                    continue
                if is_inside_target_folder(path):
                    continue
                if material_path_key(path) in other_ref_keys:
                    continue
                target_paths.append(path)

        unique_targets: list[Path] = []
        seen_targets: set[str] = set()
        for path in target_paths:
            key = material_path_key(path)
            if key in seen_targets:
                continue
            seen_targets.add(key)
            unique_targets.append(path)

        # Keep delete-plan creation lightweight. Recursively scanning media folders here can
        # freeze the GUI before the background worker even starts, especially when a
        # workspace contains many or large files. The actual delete worker reports
        # progress per target path instead.
        file_count = -1
        total_bytes = -1

        return WorkspaceDeletePlan(
            workspace_id=workspace_id,
            workspace_name=str(workspace["name"]),
            fallback_workspace_id=fallback_workspace_id,
            prompt_count=len(prompt_ids),
            tag_count=tag_count,
            tag_preset_count=preset_count,
            media_count=len(media_rows),
            asset_target_paths=unique_targets,
            asset_file_count=file_count,
            asset_total_bytes=total_bytes,
        )

    def confirm_workspace_delete(self, plan: WorkspaceDeletePlan) -> bool:
        summary = (
            f"ワークスペース「{plan.workspace_name}」を削除します。\n\n"
            f"カード: {plan.prompt_count} 件\n"
            f"タグ: {plan.tag_count} 件\n"
            f"タグプリセット: {plan.tag_preset_count} 件\n"
            f"メディア登録: {plan.media_count} 件\n"
            f"ゴミ箱へ移動する対象: {len(plan.asset_target_paths)} 件\n\n"
            "DBバックアップを作成してから削除します。"
        )
        first = QMessageBox.question(
            self,
            "ワークスペース削除確認",
            summary + "\n\n続行しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if first != QMessageBox.Yes:
            return False

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("ワークスペース削除 最終確認")
        box.setText(f"「{plan.workspace_name}」を削除します。")
        box.setInformativeText(
            "この操作はカード、タグ、タグプリセットをDBから削除し、関連メディアをゴミ箱へ移動します。\n"
            "実行前にDBバックアップを作成します。"
        )
        check = QCheckBox("内容を理解して削除する")
        box.setCheckBox(check)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        yes_button = box.button(QMessageBox.Yes)
        if yes_button is not None:
            yes_button.setText("削除")
            yes_button.setEnabled(False)
        no_button = box.button(QMessageBox.No)
        if no_button is not None:
            no_button.setText("キャンセル")
        check.toggled.connect(lambda checked: yes_button.setEnabled(bool(checked)) if yes_button is not None else None)
        result = box.exec()
        return result == QMessageBox.Yes and check.isChecked()

    def delete_workspace_with_confirmation(self, workspace_id: int, manager_dialog: Optional[QDialog] = None) -> None:
        try:
            if self.dirty:
                if not self.maybe_save_dirty():
                    return
            plan = self.build_workspace_delete_plan(workspace_id)
        except Exception as exc:
            QMessageBox.warning(self, "ワークスペース削除", f"削除準備に失敗しました。\n\n{exc}")
            return
        if not self.confirm_workspace_delete(plan):
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = safe_filename(plan.workspace_name).strip(" .") or f"workspace_{plan.workspace_id}"
        backup_path = unique_path(self.backup_dir / f"{timestamp}_before_delete_workspace_{plan.workspace_id}_{safe_name}.db")
        backup_path.parent.mkdir(parents=True, exist_ok=True)

        progress_parent = manager_dialog if manager_dialog is not None else self
        progress = QProgressDialog("ワークスペースを削除中...", "", 0, 100, progress_parent)
        progress.setWindowTitle("ワークスペース削除")
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.setLabelText("準備中...")
        progress.show()
        QApplication.processEvents()

        try:
            self.db.conn.commit()
        except Exception:
            pass

        thread = QThread(self)
        worker = WorkspaceDeleteWorker(
            str(self.db_path),
            str(backup_path),
            plan.workspace_id,
            plan.fallback_workspace_id,
            self.current_workspace_id,
            [str(path) for path in plan.asset_target_paths],
        )
        worker.moveToThread(thread)
        self._workspace_delete_thread = thread
        self._workspace_delete_worker = worker
        self._workspace_delete_progress = progress
        self._workspace_delete_context = {
            "plan": plan,
            "backup_path": backup_path,
            "manager_dialog": manager_dialog,
            "thread": thread,
        }

        thread.started.connect(worker.run)
        # GUI widgets must only be updated on the main thread. Connecting to bound
        # MainWindow methods with QueuedConnection avoids calling Python closures
        # from the worker thread, which could make the progress dialog freeze on Windows.
        worker.progress.connect(self.on_workspace_delete_progress, Qt.QueuedConnection)
        worker.finished.connect(self.on_workspace_delete_finished, Qt.QueuedConnection)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: setattr(self, "_workspace_delete_thread", None))
        QTimer.singleShot(0, thread.start)

    def on_workspace_delete_progress(self, value: int, message: str) -> None:
        progress = getattr(self, "_workspace_delete_progress", None)
        if progress is None:
            return
        try:
            progress.setValue(max(0, min(100, int(value))))
            progress.setLabelText(str(message))
        except RuntimeError:
            pass

    def on_workspace_delete_finished(self, success: bool, message: str, result: object) -> None:
        context = getattr(self, "_workspace_delete_context", {}) or {}
        plan = context.get("plan")
        backup_path = context.get("backup_path")
        manager_dialog = context.get("manager_dialog")
        thread = context.get("thread")
        progress = getattr(self, "_workspace_delete_progress", None)
        if progress is not None:
            try:
                progress.close()
            except RuntimeError:
                pass
        info = result if isinstance(result, dict) else {}
        db_deleted = bool(info.get("db_deleted"))
        if db_deleted:
            try:
                self.db.close()
            except Exception:
                pass
            self.db = Database(self.db_path)
            self.current_workspace_id = self.db.current_workspace_id()
            self.clear_detail()
            self.refresh_workspace_selector()
            self.apply_workspace_settings()
            self.refresh_tags()
            self.refresh_prompt_list()
            if manager_dialog is not None and hasattr(manager_dialog, "reload_workspaces"):
                try:
                    if hasattr(manager_dialog, "db"):
                        manager_dialog.db = self.db
                    manager_dialog.reload_workspaces(self.current_workspace_id)
                except Exception:
                    pass
        backup_text = str(info.get("backup_path", backup_path or ""))
        asset_errors = info.get("asset_errors", []) if isinstance(info, dict) else []
        moved_assets = int(info.get("moved_assets", 0)) if isinstance(info, dict) else 0
        workspace_name = getattr(plan, "workspace_name", "") if plan is not None else ""
        if success:
            QMessageBox.information(
                self,
                "ワークスペース削除",
                f"{message}\n\nDBバックアップ:\n{backup_text}\n\nゴミ箱へ移動した対象: {moved_assets} 件",
            )
            self.statusBar().showMessage(f"ワークスペースを削除しました: {workspace_name}")
        else:
            extra = ""
            if asset_errors:
                extra = "\n\n移動できなかったメディア:\n" + "\n".join(str(err) for err in asset_errors[:8])
                if len(asset_errors) > 8:
                    extra += f"\n...ほか {len(asset_errors) - 8} 件"
            QMessageBox.warning(
                self,
                "ワークスペース削除",
                f"{message}\n\nDBバックアップ:\n{backup_text}{extra}",
            )
            self.statusBar().showMessage("ワークスペース削除で警告/エラーがありました")
        self._workspace_delete_worker = None
        self._workspace_delete_progress = None
        self._workspace_delete_context = None
        if thread is not None:
            try:
                thread.quit()
            except RuntimeError:
                pass

    def prompt_asset_dir(self, prompt_id: int) -> Path:
        return self.assets_dir / f"prompt_{prompt_id:06d}"

    def prompt_images_dir(self, prompt_id: int) -> Path:
        return self.prompt_asset_dir(prompt_id) / "images"

    def prompt_files_dir(self, prompt_id: int) -> Path:
        return self.prompt_asset_dir(prompt_id) / "files"

    def prompt_thumbs_dir(self, prompt_id: int) -> Path:
        return self.prompt_asset_dir(prompt_id) / "thumbnails"

    def ensure_prompt_asset_dirs(self, prompt_id: int) -> tuple[Path, Path, Path]:
        image_dir = self.prompt_images_dir(prompt_id)
        file_dir = self.prompt_files_dir(prompt_id)
        thumb_dir = self.prompt_thumbs_dir(prompt_id)
        image_dir.mkdir(parents=True, exist_ok=True)
        file_dir.mkdir(parents=True, exist_ok=True)
        thumb_dir.mkdir(parents=True, exist_ok=True)
        return image_dir, file_dir, thumb_dir

    def stored_path_to_absolute(self, value: object) -> Path:
        raw = str(value or "").strip()
        if not raw:
            return Path()
        path = Path(raw)
        if path.is_absolute():
            return path
        try:
            win_path = PureWindowsPath(raw)
            if win_path.is_absolute():
                return Path(raw)
            if "\\" in raw:
                return self.base_dir.joinpath(*win_path.parts)
        except Exception:
            pass
        return self.base_dir / path

    def legacy_asset_relative_candidate(self, value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        candidates: list[tuple[str, ...]] = []
        try:
            candidates.append(tuple(Path(raw).parts))
        except Exception:
            pass
        try:
            candidates.append(tuple(PureWindowsPath(raw).parts))
        except Exception:
            pass
        for parts in candidates:
            lower_parts = [str(part).strip("\\/").lower() for part in parts]
            for index, part in enumerate(lower_parts):
                if part != "assets":
                    continue
                rel_parts = [str(part).strip("\\/") for part in parts[index:] if str(part).strip("\\/")]
                if not rel_parts:
                    continue
                rel = Path(*rel_parts)
                candidate = self.base_dir / rel
                if candidate.exists():
                    return rel.as_posix()
        return ""

    def absolute_path_to_stored(self, value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        path = Path(raw)
        try:
            if not path.is_absolute():
                win_path = PureWindowsPath(raw)
                if not win_path.is_absolute():
                    return Path(*win_path.parts).as_posix() if "\\" in raw else path.as_posix()
        except Exception:
            if not path.is_absolute():
                return raw.replace("\\", "/")
        try:
            resolved = path.resolve()
            base = self.base_dir.resolve()
            return resolved.relative_to(base).as_posix()
        except Exception:
            pass
        legacy_candidate = self.legacy_asset_relative_candidate(raw)
        if legacy_candidate:
            return legacy_candidate
        return raw

    def migrate_material_paths_to_relative(self) -> None:
        rows = self.db.conn.execute("SELECT id, file_path, thumbnail_path FROM images ORDER BY id ASC").fetchall()
        changed = False
        for row in rows:
            image_id = int(row["id"])
            file_path = str(row["file_path"] or "")
            thumb_path = str(row["thumbnail_path"] or "")
            new_file_path = self.absolute_path_to_stored(file_path)
            new_thumb_path = self.absolute_path_to_stored(thumb_path)
            if new_file_path != file_path or new_thumb_path != thumb_path:
                self.db.conn.execute(
                    "UPDATE images SET file_path = ?, thumbnail_path = ? WHERE id = ?",
                    (new_file_path, new_thumb_path, image_id),
                )
                changed = True
        if changed:
            self.db.conn.commit()

    def prompt_row_for_display(self, row: PromptRow) -> PromptRow:
        if row.cover_thumb:
            row.cover_thumb = str(self.stored_path_to_absolute(row.cover_thumb))
        return row

    def material_file_path_from_row(self, row: sqlite3.Row) -> Path:
        return self.stored_path_to_absolute(row["file_path"] if "file_path" in row.keys() else "")

    def material_thumb_path_from_row(self, row: sqlite3.Row) -> Optional[Path]:
        raw = str(row["thumbnail_path"] if "thumbnail_path" in row.keys() else "")
        return self.stored_path_to_absolute(raw) if raw else None

    def migrate_legacy_asset_layout(self) -> None:
        legacy_roots = [self.legacy_images_dir, self.legacy_files_dir, self.legacy_thumbs_dir]
        if not any(path.exists() for path in legacy_roots):
            return

        rows = self.db.conn.execute("SELECT * FROM images ORDER BY id ASC").fetchall()
        for row in rows:
            image_id = int(row["id"])
            prompt_id = int(row["prompt_id"])
            media_type = str(row["media_type"] if "media_type" in row.keys() else "image")
            image_dir, file_dir, thumb_dir = self.ensure_prompt_asset_dirs(prompt_id)

            file_path = self.material_file_path_from_row(row)
            if file_path.exists():
                target_dir = image_dir if media_type == "image" else file_dir
                if not is_relative_to_path(file_path, target_dir):
                    try:
                        dest = unique_path(target_dir / file_path.name)
                        shutil.move(str(file_path), str(dest))
                        self.db.update_image_file_path(image_id, self.absolute_path_to_stored(dest), touch=False)
                    except Exception:
                        pass

            thumb_path = self.material_thumb_path_from_row(row)
            if thumb_path and thumb_path.exists() and not is_relative_to_path(thumb_path, thumb_dir):
                try:
                    dest = unique_path(thumb_dir / thumb_path.name)
                    shutil.move(str(thumb_path), str(dest))
                    self.db.update_image_thumbnail(image_id, self.absolute_path_to_stored(dest))
                except Exception:
                    pass

        self.migrate_remaining_legacy_prompt_folders(self.legacy_images_dir, "images")
        self.migrate_remaining_legacy_prompt_folders(self.legacy_files_dir, "files")
        for root in legacy_roots:
            remove_empty_dirs(root)

    def migrate_remaining_legacy_prompt_folders(self, legacy_root: Path, subfolder: str) -> None:
        if not legacy_root.exists():
            return
        for prompt_dir in legacy_root.glob("prompt_*"):
            if not prompt_dir.is_dir():
                continue
            match = re.fullmatch(r"prompt_(\d+)", prompt_dir.name)
            if not match:
                continue
            prompt_id = int(match.group(1))
            target_dir = self.prompt_asset_dir(prompt_id) / subfolder
            target_dir.mkdir(parents=True, exist_ok=True)
            for child in list(prompt_dir.iterdir()):
                try:
                    shutil.move(str(child), str(unique_path(target_dir / child.name)))
                except Exception:
                    pass

    def current_workspace_row(self) -> sqlite3.Row | None:
        return self.db.get_workspace(self.current_workspace_id)

    def current_workspace_show_thumbnail(self) -> bool:
        row = self.current_workspace_row()
        if row is None:
            return True
        return bool(int(row["show_card_thumbnail"]))

    def refresh_workspace_selector(self) -> None:
        if not hasattr(self, "workspace_combo"):
            return
        self._workspace_combo_loading = True
        try:
            self.workspace_combo.clear()
            rows = self.db.list_workspaces()
            selected_index = 0
            for index, row in enumerate(rows):
                workspace_id = int(row["id"])
                self.workspace_combo.addItem(str(row["name"]), workspace_id)
                if workspace_id == int(self.current_workspace_id):
                    selected_index = index
            if self.workspace_combo.count() > 0:
                self.workspace_combo.setCurrentIndex(selected_index)
                selected_workspace_id = self.workspace_combo.currentData()
                if selected_workspace_id is not None:
                    self.current_workspace_id = int(selected_workspace_id)
        finally:
            self._workspace_combo_loading = False

    def apply_workspace_settings(self) -> None:
        required_attrs = (
            "select1_label",
            "select2_label",
            "select3_label",
            "prompt_group",
            "negative_group",
            "description_group",
            "search_edit",
        )
        if not all(hasattr(self, attr_name) for attr_name in required_attrs):
            return
        row = self.current_workspace_row()
        if row is None:
            return
        self.select1_label.setText(str(row["select_field_1_label"]))
        self.select2_label.setText(str(row["select_field_2_label"]))
        self.select3_label.setText(str(row["select_field_3_label"]))
        self.prompt_group.set_plain_title(str(row["text_field_1_label"]))
        self.negative_group.set_plain_title(str(row["text_field_2_label"]))
        self.description_group.set_plain_title(str(row["text_field_3_label"]))
        self.search_edit.setPlaceholderText(
            f"検索: タイトル / {row['text_field_1_label']} / {row['text_field_3_label']} / タグ"
        )

    def on_workspace_selected(self) -> None:
        if self._workspace_combo_loading:
            return
        workspace_id = self.workspace_combo.currentData()
        if workspace_id is None or int(workspace_id) == int(self.current_workspace_id):
            return
        old_workspace_id = self.current_workspace_id
        if not self.maybe_save_dirty():
            self.refresh_workspace_selector()
            return
        try:
            self.db.set_current_workspace_id(int(workspace_id))
            self.current_workspace_id = int(workspace_id)
        except Exception:
            self.current_workspace_id = old_workspace_id
            self.refresh_workspace_selector()
            return
        self.current_prompt_id = None
        self.loading = True
        try:
            self.clear_detail()
        finally:
            self.loading = False
        self.apply_workspace_settings()
        self.refresh_tags()
        self.reload_preset_combo()
        self.refresh_prompt_list()
        self.statusBar().showMessage(f"ワークスペース: {self.workspace_combo.currentText()}")

    def open_workspace_manager(self) -> None:
        dialog = WorkspaceManagerDialog(self.db, self)
        dialog.exec()
        self.current_workspace_id = self.db.current_workspace_id()
        self.refresh_workspace_selector()
        self.apply_workspace_settings()
        self.refresh_tags()
        self.reload_preset_combo()
        self.refresh_prompt_list()

    def create_editable_combo(self, placeholder: str = "") -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        line_edit = combo.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText(placeholder)
        return combo

    def reload_meta_combos(self) -> None:
        for field, combo in [("engine", self.engine_edit), ("model", self.model_edit), ("project", self.project_edit)]:
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("")
            for row in self.db.list_meta_options(field):
                combo.addItem(str(row["value"]))
            combo.setCurrentText(current)
            combo.blockSignals(False)

    def build_ui(self) -> None:
        central = QWidget()
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)
        self.main_splitter = splitter
        root_layout.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)

        self.workspace_combo = QComboBox()
        self.workspace_combo.setToolTip("ワークスペース切り替え")
        left_layout.addWidget(self.workspace_combo)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("検索: タイトル / 本文 / 説明 / タグ")
        self.search_edit.setClearButtonEnabled(True)
        left_layout.addWidget(self.search_edit)

        tag_box = QGroupBox("タグ絞り込み")
        tag_box.setMinimumHeight(LEFT_TAG_FILTER_MIN_HEIGHT)
        tag_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Ignored)
        tag_layout = QVBoxLayout(tag_box)
        tag_layout.setContentsMargins(8, 8, 8, 8)
        self.tag_filter_content = QWidget()
        self.tag_filter_layout = FlowLayout(self.tag_filter_content, margin=0, spacing=6)
        self.tag_filter_content.setLayout(self.tag_filter_layout)
        self.tag_filter_scroll = QScrollArea()
        self.tag_filter_scroll.setWidgetResizable(True)
        self.tag_filter_scroll.setWidget(self.tag_filter_content)
        self.tag_filter_scroll.setMinimumHeight(0)
        self.tag_filter_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        tag_layout.addWidget(self.tag_filter_scroll, 1)
        tag_btn_row = QHBoxLayout()
        self.clear_tags_button = QPushButton("解除/再読み込み")
        self.only_favorite_checkbox = QCheckBox("お気に入りのみ")
        tag_btn_row.addWidget(self.clear_tags_button)
        tag_btn_row.addWidget(self.only_favorite_checkbox)
        tag_layout.addLayout(tag_btn_row)
        self.pinned_prompt_group = QGroupBox("ピン留め")
        self.pinned_prompt_group.setStyleSheet(
            "QGroupBox { background: #fff7df; border: 1px solid #e0c46a; border-radius: 4px; margin-top: 8px; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #6b5200; }"
        )
        pinned_layout = QVBoxLayout(self.pinned_prompt_group)
        pinned_layout.setContentsMargins(6, 10, 6, 6)
        self.pinned_prompt_list = PromptListWidget(self)
        self.pinned_prompt_list.setIconSize(QSize(96, 72))
        self.pinned_prompt_list.setUniformItemSizes(False)
        self.pinned_prompt_list.setSpacing(4)
        self.pinned_prompt_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.pinned_prompt_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.pinned_prompt_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.pinned_prompt_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.pinned_prompt_list.setStyleSheet("QListWidget { background: #fffaf0; border: 1px solid #eadb9f; }")
        pinned_layout.addWidget(self.pinned_prompt_list)
        self.pinned_prompt_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.pinned_prompt_group.setVisible(False)

        self.prompt_list = PromptListWidget(self)
        self.prompt_list.setIconSize(QSize(96, 72))
        self.prompt_list.setUniformItemSizes(False)
        self.prompt_list.setSpacing(4)
        self.prompt_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.prompt_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.prompt_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        self.left_bottom_widget = QWidget()
        left_bottom_layout = QVBoxLayout(self.left_bottom_widget)
        left_bottom_layout.setContentsMargins(0, 0, 0, 0)
        left_bottom_layout.setSpacing(6)
        left_bottom_layout.addWidget(self.pinned_prompt_group)
        left_bottom_layout.addWidget(self.prompt_list, 1)

        self.left_splitter = QSplitter(Qt.Vertical)
        self.left_splitter.addWidget(tag_box)
        self.left_splitter.addWidget(self.left_bottom_widget)
        self.left_splitter.setSizes([LEFT_TAG_FILTER_DEFAULT_HEIGHT, 540])
        left_layout.addWidget(self.left_splitter, 1)

        splitter.addWidget(left)

        right = QWidget()
        self.right_widget = right
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)

        content = QWidget()
        form_root = QVBoxLayout(content)
        form_root.setContentsMargins(0, 0, 0, 0)

        meta_group = QGroupBox("基本情報")
        meta_layout = QGridLayout(meta_group)
        self.title_edit = QLineEdit()
        self.favorite_check = QCheckBox("お気に入り")
        self.rating_combo = QComboBox()
        self.rating_combo.addItems(["評価なし", "★", "★★", "★★★", "★★★★", "★★★★★"])
        self.engine_edit = self.create_editable_combo()
        self.model_edit = self.create_editable_combo()
        self.project_edit = self.create_editable_combo()
        self.tags_editor = TagChipEditor(color_provider=self.tag_color_for_name, standalone_layout=False, tag_resolver=self.db.canonical_tag_name)
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("タグプリセットを追加...")
        self.add_preset_button = QPushButton("追加")

        meta_layout.setColumnStretch(1, 1)

        meta_layout.addWidget(QLabel("タイトル"), 0, 0)
        title_row = QWidget()
        title_row_layout = QHBoxLayout(title_row)
        title_row_layout.setContentsMargins(0, 0, 0, 0)
        title_row_layout.setSpacing(0)
        title_row_layout.addWidget(self.title_edit, 1)
        title_row_layout.addSpacing(6)
        title_row_layout.addWidget(self.favorite_check)
        title_row_layout.addSpacing(6)
        title_row_layout.addWidget(QLabel("評価"))
        title_row_layout.addWidget(self.rating_combo)
        meta_layout.addWidget(title_row, 0, 1, 1, 7)

        self.select1_label = QLabel("使用AI")
        meta_layout.addWidget(self.select1_label, 1, 0)
        ai_row = QWidget()
        ai_row_layout = QHBoxLayout(ai_row)
        ai_row_layout.setContentsMargins(0, 0, 0, 0)
        ai_row_layout.setSpacing(0)
        for combo in (self.engine_edit, self.model_edit, self.project_edit):
            combo.setMinimumWidth(150)
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        field_gap = 10
        ai_row_layout.addWidget(self.engine_edit, 1)
        ai_row_layout.addSpacing(field_gap)
        self.select2_label = QLabel("モデル")
        ai_row_layout.addWidget(self.select2_label)
        ai_row_layout.addWidget(self.model_edit, 1)
        ai_row_layout.addSpacing(field_gap)
        self.select3_label = QLabel("プロジェクト")
        ai_row_layout.addWidget(self.select3_label)
        ai_row_layout.addWidget(self.project_edit, 1)
        meta_layout.addWidget(ai_row, 1, 1, 1, 7)
        tag_label = QLabel("タグ")
        tag_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        tag_control = QWidget()
        tag_control_layout = QVBoxLayout(tag_control)
        tag_control_layout.setContentsMargins(0, 0, 0, 0)
        tag_control_layout.setSpacing(5)
        tag_top_row = QHBoxLayout()
        tag_top_row.setContentsMargins(0, 0, 0, 0)
        tag_top_row.addWidget(self.tags_editor.input_edit, 1)
        tag_top_row.addWidget(self.tags_editor.add_button)
        tag_top_row.addWidget(self.preset_combo)
        tag_top_row.addWidget(self.add_preset_button)
        tag_control_layout.addLayout(tag_top_row)
        tag_control_layout.addWidget(self.tags_editor.chip_container)
        meta_layout.addWidget(tag_label, 2, 0)
        meta_layout.addWidget(tag_control, 2, 1, 1, 7)
        form_root.addWidget(meta_group)

        compact_text_min_height = max(48, self.fontMetrics().height() * 2 + 18)
        self.text_splitter = QSplitter(Qt.Vertical)
        self.text_splitter.setChildrenCollapsible(False)
        self.text_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.prompt_group = CollapsibleGroupBox("プロンプト", "section_prompt_collapsed")
        self.collapsible_sections.append(self.prompt_group)
        prompt_layout = QVBoxLayout(self.prompt_group)
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setAcceptRichText(False)
        self.prompt_edit.setMinimumHeight(compact_text_min_height)
        prompt_layout.addWidget(self.prompt_edit)
        self.text_splitter.addWidget(self.prompt_group)

        self.negative_group = CollapsibleGroupBox("ネガティブ / 補助プロンプト", "section_negative_collapsed")
        self.collapsible_sections.append(self.negative_group)
        negative_layout = QVBoxLayout(self.negative_group)
        self.negative_edit = QTextEdit()
        self.negative_edit.setAcceptRichText(False)
        self.negative_edit.setMinimumHeight(compact_text_min_height)
        negative_layout.addWidget(self.negative_edit)
        self.text_splitter.addWidget(self.negative_group)

        self.description_group = CollapsibleGroupBox("説明 / メモ", "section_description_collapsed")
        self.collapsible_sections.append(self.description_group)
        desc_layout = QVBoxLayout(self.description_group)
        self.description_edit = QTextEdit()
        self.description_edit.setAcceptRichText(False)
        self.description_edit.setMinimumHeight(compact_text_min_height)
        desc_layout.addWidget(self.description_edit)
        self.text_splitter.addWidget(self.description_group)

        image_group = CollapsibleGroupBox("メディア", "section_images_collapsed")
        image_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.collapsible_sections.append(image_group)
        image_layout = QVBoxLayout(image_group)
        img_btn_row = QHBoxLayout()
        self.add_images_button = QPushButton("メディアを追加")
        self.rename_image_button = QPushButton("ファイル名変更")
        self.remove_image_button = QPushButton("選択メディアを削除")
        self.cover_image_button = QPushButton("カバーにする")
        self.open_image_button = QPushButton("開く")
        self.open_prompt_assets_button = QPushButton("メディアフォルダを開く")
        self.reload_materials_button = QPushButton("再読み込み")
        self.rebuild_thumbnails_button = QPushButton("サムネ再作成")
        img_btn_row.addWidget(self.add_images_button)
        img_btn_row.addWidget(self.open_prompt_assets_button)
        img_btn_row.addWidget(self.reload_materials_button)
        img_btn_row.addWidget(self.rebuild_thumbnails_button)
        img_btn_row.addStretch(1)
        image_layout.addLayout(img_btn_row)
        self.image_list = ImageListWidget(self)
        self.image_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        image_layout.addWidget(self.image_list, 1)
        self.drop_hint_label = QLabel("メディアファイルをここへドラッグ＆ドロップで追加できます。")
        self.drop_hint_label.setStyleSheet("color: #777;")
        image_layout.addWidget(self.drop_hint_label)
        self.text_splitter.addWidget(image_group)
        self.text_splitter.setSizes([260, 130, 160, 340])
        form_root.addWidget(self.text_splitter, 1)

        right_layout.addWidget(content, 1)

        splitter.addWidget(right)
        splitter.setSizes([410, 910])

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

    def build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("ファイル")
        open_assets_action = QAction("メディアフォルダを開く", self)
        backup_action = QAction("バックアップ実行", self)
        open_backup_action = QAction("バックアップフォルダを開く", self)
        quit_action = QAction("終了", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        open_assets_action.triggered.connect(self.open_assets_folder)
        backup_action.triggered.connect(self.run_manual_backup)
        open_backup_action.triggered.connect(self.open_backup_folder)
        quit_action.triggered.connect(self.request_quit_app)
        file_menu.addAction(open_assets_action)
        file_menu.addAction(open_backup_action)
        file_menu.addSeparator()
        file_menu.addAction(backup_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        edit_menu = self.menuBar().addMenu("編集")
        save_action = QAction("保存", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.save_current_prompt)
        new_action = QAction("新規", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self.new_prompt)
        duplicate_action = QAction("複製", self)
        duplicate_action.triggered.connect(self.duplicate_prompt)
        delete_action = QAction("削除", self)
        delete_action.triggered.connect(self.delete_current_prompt)
        search_action = QAction("検索", self)
        search_action.setShortcut(QKeySequence.Find)
        search_action.setShortcutContext(Qt.ApplicationShortcut)
        search_action.triggered.connect(self.focus_search_box)
        reload_action = QAction("再読み込み", self)
        reload_action.setShortcut(QKeySequence("F5"))
        reload_action.setShortcutContext(Qt.ApplicationShortcut)
        reload_action.triggered.connect(self.reload_current_materials)
        self.addAction(reload_action)
        paste_material_action = QAction("クリップボードからメディアへ貼り付け", self)
        paste_material_action.setShortcut(QKeySequence("Alt+V"))
        paste_material_action.setShortcutContext(Qt.ApplicationShortcut)
        paste_material_action.triggered.connect(self.paste_material_from_clipboard)
        copy_prompt_action = QAction("プロンプトをコピー", self)
        copy_prompt_action.setShortcut(QKeySequence("Alt+C"))
        copy_prompt_action.setShortcutContext(Qt.ApplicationShortcut)
        copy_prompt_action.triggered.connect(self.copy_prompt)
        copy_full_action = QAction("タイトル+プロンプトをコピー", self)
        copy_full_action.triggered.connect(self.copy_full_prompt)
        edit_menu.addAction(save_action)
        edit_menu.addSeparator()
        edit_menu.addAction(new_action)
        edit_menu.addAction(duplicate_action)
        edit_menu.addAction(delete_action)
        edit_menu.addSeparator()
        edit_menu.addAction(search_action)
        edit_menu.addSeparator()
        edit_menu.addAction(paste_material_action)
        edit_menu.addSeparator()
        edit_menu.addAction(copy_prompt_action)
        edit_menu.addAction(copy_full_action)

        view_menu = self.menuBar().addMenu("表示")
        sort_menu = view_menu.addMenu("並び替え")
        sort_group = QActionGroup(self)
        sort_group.setExclusive(True)
        self.prompt_sort_actions = {}
        for mode, label in [
            (PROMPT_SORT_UPDATED, "更新日時"),
            (PROMPT_SORT_TITLE, "タイトル"),
        ]:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(self.prompt_sort_mode == mode)
            action.triggered.connect(lambda checked=False, m=mode: self.set_prompt_sort_mode(m, save=True))
            sort_group.addAction(action)
            sort_menu.addAction(action)
            self.prompt_sort_actions[mode] = action
        image_viewer_menu = view_menu.addMenu("画像ビュアー")

        bring_image_viewers_front_action = QAction("前面表示", self)
        bring_image_viewers_front_action.setShortcut(QKeySequence("Alt+Z"))
        bring_image_viewers_front_action.setShortcutContext(Qt.ApplicationShortcut)
        bring_image_viewers_front_action.triggered.connect(lambda _checked=False: self.bring_visible_image_viewers_to_front())

        tile_image_viewers_action = QAction("並べて表示", self)
        tile_image_viewers_action.setShortcut(QKeySequence("Alt+A"))
        tile_image_viewers_action.setShortcutContext(Qt.ApplicationShortcut)
        tile_image_viewers_action.triggered.connect(lambda _checked=False: self.tile_visible_image_viewers())

        close_image_viewers_action = QAction("全て閉じる", self)
        close_image_viewers_action.setShortcut(QKeySequence("Alt+X"))
        close_image_viewers_action.setShortcutContext(Qt.ApplicationShortcut)
        close_image_viewers_action.triggered.connect(self.close_all_image_viewers)

        image_viewer_menu.addAction(bring_image_viewers_front_action)
        image_viewer_menu.addAction(tile_image_viewers_action)
        image_viewer_menu.addSeparator()
        image_viewer_menu.addAction(close_image_viewers_action)

        settings_menu = self.menuBar().addMenu("設定")
        self.resident_mode_action = QAction("常駐モード", self)
        self.resident_mode_action.setCheckable(True)
        self.resident_mode_action.setChecked(self.resident_mode)
        self.resident_mode_action.triggered.connect(self.set_resident_mode)
        settings_menu.addAction(self.resident_mode_action)
        self.startup_action = QAction("Windowsスタートアップに登録", self)
        self.startup_action.setCheckable(True)
        self.startup_action.setChecked(is_windows_startup_registered())
        self.startup_action.triggered.connect(self.set_windows_startup_enabled)
        settings_menu.addAction(self.startup_action)

        hotkey_menu = settings_menu.addMenu("グローバルホットキー")
        self.global_hotkey_action = QAction("Shift + Alt + A で表示", self)
        self.global_hotkey_action.setCheckable(True)
        self.global_hotkey_action.setChecked(self.global_hotkey_enabled)
        self.global_hotkey_action.triggered.connect(self.set_global_hotkey_enabled)
        hotkey_menu.addAction(self.global_hotkey_action)
        settings_menu.addSeparator()

        workspace_manage_action = QAction("ワークスペース管理", self)
        workspace_manage_action.triggered.connect(self.open_workspace_manager)
        tag_manage_action = QAction("タグ管理", self)
        tag_manage_action.triggered.connect(self.open_tag_manager)
        label_manage_action = QAction("ラベル管理", self)
        label_manage_action.triggered.connect(self.open_material_label_manager)
        settings_menu.addAction(workspace_manage_action)
        settings_menu.addAction(tag_manage_action)
        settings_menu.addAction(label_manage_action)
        settings_menu.addSeparator()

        font_menu = settings_menu.addMenu("文字サイズ")
        font_group = QActionGroup(self)
        font_group.setExclusive(True)
        self.font_size_actions = {}
        for size in range(9, 26):
            action = QAction(f"{size}pt", self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, s=size: self.apply_font_size(s, save=True))
            font_group.addAction(action)
            font_menu.addAction(action)
            self.font_size_actions[size] = action

        viewer_menu = settings_menu.addMenu("画像ビュアー")
        resize_menu = viewer_menu.addMenu("リサイズ方法")
        resize_group = QActionGroup(self)
        resize_group.setExclusive(True)
        self.image_viewer_resize_method_actions = {}
        for method, label in IMAGE_VIEWER_RESIZE_METHODS:
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, m=method: self.set_image_viewer_resize_method(m, save=True))
            resize_group.addAction(action)
            resize_menu.addAction(action)
            self.image_viewer_resize_method_actions[method] = action
        self.set_image_viewer_resize_method(self.image_viewer_resize_method, save=False)

        help_menu = self.menuBar().addMenu("ヘルプ")
        readme_action = QAction("readme.txt", self)
        readme_action.triggered.connect(self.open_readme_file)
        key_help_action = QAction("キー操作", self)
        key_help_action.triggered.connect(self.show_key_operations_dialog)
        supported_formats_action = QAction("対応ファイル形式", self)
        supported_formats_action.triggered.connect(self.show_supported_formats_dialog)
        about_action = QAction("バージョン情報", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(readme_action)
        help_menu.addAction(key_help_action)
        help_menu.addAction(supported_formats_action)
        help_menu.addSeparator()
        help_menu.addAction(about_action)

    def setup_tray_icon(self) -> None:
        if self.tray_icon is not None:
            return
        icon = load_window_icon()
        self.tray_menu = QMenu(self)

        show_action = QAction("表示", self)
        new_action = QAction("新規", self)
        quit_action = QAction("終了", self)
        show_action.triggered.connect(self.show_main_window)
        new_action.triggered.connect(self.show_main_and_new_prompt)
        quit_action.triggered.connect(self.request_quit_app)

        self.tray_menu.addAction(show_action)
        self.tray_menu.addAction(new_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(quit_action)

        self._tray_click_timer = QTimer(self)
        self._tray_click_timer.setSingleShot(True)
        self._tray_click_timer.timeout.connect(self.popup_tray_menu)

        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip(APP_NAME)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.update_tray_visibility()

    def update_tray_visibility(self) -> None:
        if self.tray_icon is None:
            return
        if self.resident_mode and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon.show()
        else:
            self.tray_icon.hide()

    def update_quit_on_last_window_closed(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setQuitOnLastWindowClosed(not self.resident_mode)

    def set_resident_mode(self, checked: bool) -> None:
        self.resident_mode = bool(checked)
        if self.resident_mode_action is not None and self.resident_mode_action.isChecked() != self.resident_mode:
            self.resident_mode_action.setChecked(self.resident_mode)
        self.db.set_setting("resident_mode", "1" if self.resident_mode else "0")
        self.update_tray_visibility()
        self.update_quit_on_last_window_closed()
        message = "常駐モード: ON" if self.resident_mode else "常駐モード: OFF"
        self.statusBar().showMessage(message)

    def set_windows_startup_enabled(self, checked: bool) -> None:
        if checked:
            if register_windows_startup():
                if self.startup_action is not None:
                    self.startup_action.setChecked(True)
                self.statusBar().showMessage("Windowsスタートアップに登録しました")
            else:
                if self.startup_action is not None:
                    self.startup_action.setChecked(False)
                QMessageBox.warning(self, "Windowsスタートアップ", "Windowsスタートアップに登録できませんでした。")
        else:
            if unregister_windows_startup():
                if self.startup_action is not None:
                    self.startup_action.setChecked(False)
                self.statusBar().showMessage("Windowsスタートアップ登録を解除しました")
            else:
                if self.startup_action is not None:
                    self.startup_action.setChecked(is_windows_startup_registered())
                QMessageBox.warning(self, "Windowsスタートアップ", "Windowsスタートアップ登録を解除できませんでした。")

    def set_global_hotkey_enabled(self, checked: bool) -> None:
        enabled = bool(checked)
        if enabled:
            if self.register_global_hotkey():
                self.global_hotkey_enabled = True
                self.db.set_setting(GLOBAL_HOTKEY_SETTING_KEY, "1")
                self.statusBar().showMessage("グローバルホットキー: Shift + Alt + A")
            else:
                self.global_hotkey_enabled = False
                self.db.set_setting(GLOBAL_HOTKEY_SETTING_KEY, "0")
                if self.global_hotkey_action is not None:
                    self.global_hotkey_action.setChecked(False)
                QMessageBox.warning(
                    self,
                    "グローバルホットキー",
                    "Shift + Alt + A を登録できませんでした。\n他のアプリが使用している可能性があります。",
                )
        else:
            self.unregister_global_hotkey()
            self.global_hotkey_enabled = False
            self.db.set_setting(GLOBAL_HOTKEY_SETTING_KEY, "0")
            self.statusBar().showMessage("グローバルホットキー: OFF")

    def register_global_hotkey_if_needed(self) -> None:
        if self.global_hotkey_enabled:
            if not self.register_global_hotkey():
                self.global_hotkey_enabled = False
                self.db.set_setting(GLOBAL_HOTKEY_SETTING_KEY, "0")
                if self.global_hotkey_action is not None:
                    self.global_hotkey_action.setChecked(False)

    def register_global_hotkey(self) -> bool:
        self.unregister_global_hotkey()
        if not sys.platform.startswith("win"):
            return False
        if self.register_global_hotkey_by_winapi():
            self._global_hotkey_registered = True
            self._global_hotkey_backend = "registerhotkey"
            return True
        if self.register_global_hotkey_by_keyboard_hook():
            self._global_hotkey_registered = True
            self._global_hotkey_backend = "keyboardhook"
            return True
        self._global_hotkey_registered = False
        self._global_hotkey_backend = ""
        return False

    def register_global_hotkey_by_winapi(self) -> bool:
        try:
            import ctypes

            MOD_ALT = 0x0001
            MOD_SHIFT = 0x0004
            MOD_NOREPEAT = 0x4000
            modifiers = MOD_ALT | MOD_SHIFT | MOD_NOREPEAT
            hwnd = int(self.winId())
            return bool(ctypes.windll.user32.RegisterHotKey(hwnd, GLOBAL_HOTKEY_ID, modifiers, ord("A")))
        except Exception:
            return False

    def register_global_hotkey_by_keyboard_hook(self) -> bool:
        try:
            import ctypes
            from ctypes import wintypes

            WH_KEYBOARD_LL = 13
            WM_KEYDOWN = 0x0100
            WM_KEYUP = 0x0101
            WM_SYSKEYDOWN = 0x0104
            WM_SYSKEYUP = 0x0105
            VK_A = 0x41
            VK_SHIFT = 0x10
            VK_MENU = 0x12

            class KBDLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("vkCode", wintypes.DWORD),
                    ("scanCode", wintypes.DWORD),
                    ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t),
                ]

            HOOKPROC = ctypes.WINFUNCTYPE(wintypes.LPARAM, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            def is_down(vk: int) -> bool:
                return bool(user32.GetAsyncKeyState(vk) & 0x8000)

            def callback(n_code, w_param, l_param):
                try:
                    if n_code == 0:
                        info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                        if int(info.vkCode) == VK_A:
                            if int(w_param) in (WM_KEYDOWN, WM_SYSKEYDOWN):
                                if is_down(VK_SHIFT) and is_down(VK_MENU):
                                    if not self._global_hotkey_down:
                                        self._global_hotkey_down = True
                                        QTimer.singleShot(0, self.toggle_main_window_from_hotkey)
                            elif int(w_param) in (WM_KEYUP, WM_SYSKEYUP):
                                self._global_hotkey_down = False
                except Exception:
                    pass
                return user32.CallNextHookEx(self._global_hotkey_hook_handle, n_code, w_param, l_param)

            self._global_hotkey_hook_proc = HOOKPROC(callback)
            handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._global_hotkey_hook_proc, kernel32.GetModuleHandleW(None), 0)
            self._global_hotkey_hook_handle = handle
            return bool(handle)
        except Exception:
            self._global_hotkey_hook_handle = None
            self._global_hotkey_hook_proc = None
            return False

    def unregister_global_hotkey(self) -> None:
        if sys.platform.startswith("win"):
            try:
                import ctypes

                if self._global_hotkey_backend == "registerhotkey":
                    ctypes.windll.user32.UnregisterHotKey(int(self.winId()), GLOBAL_HOTKEY_ID)
                if self._global_hotkey_hook_handle:
                    ctypes.windll.user32.UnhookWindowsHookEx(self._global_hotkey_hook_handle)
            except Exception:
                pass
        self._global_hotkey_registered = False
        self._global_hotkey_backend = ""
        self._global_hotkey_hook_handle = None
        self._global_hotkey_hook_proc = None
        self._global_hotkey_down = False

    def nativeEvent(self, eventType, message):  # noqa: N802 - Qt naming
        if sys.platform.startswith("win"):
            try:
                from ctypes import wintypes

                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0312 and int(msg.wParam) == GLOBAL_HOTKEY_ID:
                    self.toggle_main_window_from_hotkey()
                    return True, 0
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def popup_tray_menu(self) -> None:
        if self.tray_menu is not None:
            self.tray_menu.popup(QCursor.pos())

    def on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            if self._tray_click_timer is not None and self._tray_click_timer.isActive():
                self._tray_click_timer.stop()
            self.show_main_window()
            return
        if reason == QSystemTrayIcon.Trigger:
            if self._tray_click_timer is not None and self._tray_click_timer.isActive():
                self._tray_click_timer.stop()
                self.show_main_window()
                return
            delay = QApplication.doubleClickInterval() if QApplication.instance() is not None else 500
            if self._tray_click_timer is not None:
                self._tray_click_timer.start(max(500, int(delay)))
            else:
                self.popup_tray_menu()

    def show_main_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def toggle_main_window_from_hotkey(self) -> None:
        if self.isVisible() and not self.isMinimized():
            if self.resident_mode:
                self.update_tray_visibility()
                self.hide()
            else:
                self.showMinimized()
            return
        self.show_main_window()

    def show_main_and_new_prompt(self) -> None:
        self.show_main_window()
        self.new_prompt()

    def request_quit_app(self) -> None:
        self._force_quit = True
        app = QApplication.instance()
        if app is not None:
            app.setQuitOnLastWindowClosed(True)
        self.close()

    def setup_ipc_server(self) -> None:
        if self.ipc_server is not None:
            return
        QLocalServer.removeServer(APP_IPC_SERVER_NAME)
        self.ipc_server = QLocalServer(self)
        self.ipc_server.newConnection.connect(self.handle_ipc_connection)
        if not self.ipc_server.listen(APP_IPC_SERVER_NAME):
            self.ipc_server = None

    def handle_ipc_connection(self) -> None:
        if self.ipc_server is None:
            return
        while self.ipc_server.hasPendingConnections():
            socket = self.ipc_server.nextPendingConnection()
            if socket is None:
                continue
            socket.setParent(self)
            self._ipc_sockets.append(socket)
            socket.readyRead.connect(lambda s=socket: self.read_ipc_socket(s))
            socket.disconnected.connect(lambda s=socket: self.cleanup_ipc_socket(s))
            QTimer.singleShot(0, lambda s=socket: self.read_ipc_socket(s))

    def cleanup_ipc_socket(self, socket: QLocalSocket) -> None:
        if socket in self._ipc_sockets:
            self._ipc_sockets.remove(socket)
        socket.deleteLater()

    def read_ipc_socket(self, socket: QLocalSocket) -> None:
        if socket.bytesAvailable() <= 0:
            return
        data = bytes(socket.readAll()).decode("utf-8", errors="replace")
        for line in data.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except Exception:
                continue
            self.handle_ipc_message(message)

    def handle_ipc_message(self, message: dict) -> None:
        command = str(message.get("command", ""))
        if command == "show":
            self.show_main_window()
            return
        if command == "open_images":
            paths = [Path(str(p)) for p in message.get("paths", [])]
            self.open_external_image_files(paths)

    def open_external_image_files(self, paths: Iterable[Path]) -> None:
        for path in paths:
            self.open_external_image_file(path)

    def open_external_image_file(self, path: Path) -> None:
        path = Path(path)
        if not path.exists() or not path.is_file():
            return
        if path.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
            return
        self.open_image_viewer(path, external_image=True)


    def connect_signals(self) -> None:
        self.workspace_combo.currentIndexChanged.connect(self.on_workspace_selected)
        self.search_edit.textChanged.connect(self.refresh_prompt_list)
        self.prompt_list.currentItemChanged.connect(self.on_prompt_selected)
        self.prompt_list.itemDoubleClicked.connect(lambda _item: self.copy_prompt())
        self.prompt_list.customContextMenuRequested.connect(lambda pos: self.show_prompt_list_context_menu(pos, self.prompt_list))
        self.pinned_prompt_list.currentItemChanged.connect(self.on_prompt_selected)
        self.pinned_prompt_list.itemDoubleClicked.connect(lambda _item: self.copy_prompt())
        self.pinned_prompt_list.customContextMenuRequested.connect(lambda pos: self.show_prompt_list_context_menu(pos, self.pinned_prompt_list))
        self.clear_tags_button.clicked.connect(self.clear_tag_filters)
        self.only_favorite_checkbox.stateChanged.connect(self.refresh_prompt_list)
        for section in self.collapsible_sections:
            section.collapsedChanged.connect(self.on_section_collapsed_changed)

        self.add_preset_button.clicked.connect(self.add_selected_preset)

        self.add_images_button.clicked.connect(self.choose_images)
        self.rename_image_button.clicked.connect(self.rename_selected_image)
        self.remove_image_button.clicked.connect(self.remove_selected_image)
        self.cover_image_button.clicked.connect(self.set_selected_image_as_cover)
        self.open_image_button.clicked.connect(self.open_selected_image)
        self.open_prompt_assets_button.clicked.connect(self.open_current_prompt_asset_folder)
        self.reload_materials_button.clicked.connect(self.reload_current_materials)
        self.rebuild_thumbnails_button.clicked.connect(self.rebuild_current_material_thumbnails)
        self.image_list.customContextMenuRequested.connect(self.show_material_context_menu)
        self.image_list.itemDoubleClicked.connect(lambda _item: self.open_selected_image())
        self.image_list.currentItemChanged.connect(self.on_material_selected)

        self.title_edit.textChanged.connect(self.mark_dirty)
        for combo in [
            self.engine_edit,
            self.model_edit,
            self.project_edit,
        ]:
            combo.currentTextChanged.connect(self.mark_dirty)
        self.tags_editor.tagsChanged.connect(self.mark_dirty)
        self.favorite_check.stateChanged.connect(self.mark_dirty)
        self.rating_combo.currentIndexChanged.connect(self.mark_dirty)
        self.prompt_edit.textChanged.connect(self.mark_dirty)
        self.negative_edit.textChanged.connect(self.mark_dirty)
        self.description_edit.textChanged.connect(self.mark_dirty)

    def set_prompt_sort_mode(self, mode: str, save: bool = True) -> None:
        mode = normalize_prompt_sort_mode(mode)
        self.prompt_sort_mode = mode
        for key, action in self.prompt_sort_actions.items():
            action.setChecked(key == mode)
        if save:
            self.db.set_setting("prompt_sort_mode", mode)
            self.statusBar().showMessage(f"並び替え: {PROMPT_SORT_LABELS.get(mode, mode)}")
        self.refresh_prompt_list()

    def apply_font_size(self, size: int, save: bool = True) -> None:
        size = max(9, min(25, int(size)))
        self.current_font_size = size
        action = self.font_size_actions.get(size)
        if action is not None and not action.isChecked():
            action.setChecked(True)
        app = QApplication.instance()
        if app is not None:
            font = app.font()
            font.setPointSize(size)
            app.setFont(font)
        self.setStyleSheet(
            f"""
            * {{ font-size: {size}pt; }}
            QGroupBox {{ font-weight: bold; }}
            QTextEdit, QLineEdit, QListWidget {{ font-weight: normal; }}
            QListWidget::item {{ padding: 4px; }}
            QPushButton {{ padding: 5px 10px; }}
            QToolButton {{ padding: 3px 8px; }}
            """
        )
        if save:
            self.db.set_setting("font_size", str(size))
            self.statusBar().showMessage(f"文字サイズ: {size}pt")

    def on_font_size_changed(self, value: int) -> None:
        self.apply_font_size(value, save=True)

    def set_image_viewer_resize_method(self, method: str, save: bool = True) -> None:
        method = normalize_image_viewer_resize_method(method)
        self.image_viewer_resize_method = method
        for key, action in self.image_viewer_resize_method_actions.items():
            action.setChecked(key == method)
        if save:
            self.db.set_setting("image_viewer_resize_method", method)
            self.statusBar().showMessage(f"画像ビュアーのリサイズ方法: {image_viewer_resize_method_label(method)}")
        for viewer in list(self.image_viewers):
            viewer.clear_scaled_cache()
            viewer.update()

    def restore_ui_state(self) -> None:
        geometry_json = self.db.get_setting("window_geometry", "")
        if geometry_json:
            try:
                data = json.loads(geometry_json)
                x = safe_int(data.get("x", ""), self.x())
                y = safe_int(data.get("y", ""), self.y())
                w = max(800, safe_int(data.get("w", ""), self.width()))
                h = max(600, safe_int(data.get("h", ""), self.height()))
                rect = keep_rect_on_available_screens(QRect(x, y, w, h), 800, 600)
                self.setGeometry(rect)
                if bool(data.get("maximized", False)):
                    self.setWindowState(self.windowState() | Qt.WindowMaximized)
            except Exception:
                pass
        self.restore_splitter_sizes()
        for section in self.collapsible_sections:
            collapsed = self.db.get_setting(section.state_key, "0") == "1"
            section.set_collapsed(collapsed, emit_signal=False)

    def default_left_splitter_sizes(self) -> list[int]:
        total = self.left_splitter.height() if hasattr(self, "left_splitter") else 0
        if total <= 0:
            total = max(700, self.height() - 120)
        tag_height = LEFT_TAG_FILTER_DEFAULT_HEIGHT
        bottom_height = max(LEFT_PROMPT_LIST_MIN_HEIGHT, total - tag_height)
        return [tag_height, bottom_height]

    def load_left_splitter_sizes_setting(self) -> list[int] | None:
        # v90以降は、ピン留めをsplitterの一要素にせず、
        # 「タグ絞り込み」と「ピン留め+カード一覧」の2分割だけを保存する。
        raw = self.db.get_setting("left_splitter_sizes_v3", "")
        if raw:
            try:
                sizes = json.loads(raw)
                if isinstance(sizes, list) and len(sizes) >= 2:
                    values = [max(0, int(v)) for v in sizes[:2]]
                    if sum(values) > 0:
                        return values
            except Exception:
                pass

        # v88〜v90で壊れた高さが left_splitter_sizes / left_splitter_sizes_v2 に
        # 保存されていることがあるため、自動復元には使わない。
        # v91以降の終了時サイズだけを left_splitter_sizes_v3 として保存・復元する。
        return None

    def normalize_left_splitter_sizes(self, sizes: list[int]) -> list[int]:
        values = [max(0, int(v)) for v in list(sizes[:2])]
        while len(values) < 2:
            values.append(0)

        total = self.left_splitter.height()
        if total <= 0:
            total = sum(values) or max(700, self.height() - 120)

        if values[0] < LEFT_TAG_FILTER_MIN_HEIGHT:
            values[0] = LEFT_TAG_FILTER_MIN_HEIGHT
        if values[1] < LEFT_PROMPT_LIST_MIN_HEIGHT:
            values[1] = LEFT_PROMPT_LIST_MIN_HEIGHT

        used = sum(values)
        if total > 0 and used != total:
            diff = total - used
            values[1] = max(LEFT_PROMPT_LIST_MIN_HEIGHT, values[1] + diff)
            if values[1] == LEFT_PROMPT_LIST_MIN_HEIGHT and diff < 0:
                overflow = sum(values) - total
                if overflow > 0 and values[0] > LEFT_TAG_FILTER_MIN_HEIGHT:
                    values[0] -= min(overflow, values[0] - LEFT_TAG_FILTER_MIN_HEIGHT)
        return values

    def restore_splitter_sizes(self) -> None:
        for key, splitter in [
            ("main_splitter_sizes", self.main_splitter),
            ("text_splitter_sizes", self.text_splitter),
        ]:
            raw = self.db.get_setting(key, "")
            if not raw:
                continue
            try:
                sizes = json.loads(raw)
                if isinstance(sizes, list) and all(isinstance(v, int) for v in sizes):
                    if key == "text_splitter_sizes":
                        pane_count = splitter.count()
                        if len(sizes) == 3 and pane_count == 4:
                            sizes = list(sizes) + [340]
                        elif len(sizes) != pane_count:
                            sizes = list(sizes[:pane_count])
                            while len(sizes) < pane_count:
                                sizes.append(160)
                    splitter.setSizes(sizes)
            except Exception:
                pass
        self.restore_left_splitter_sizes()

    def restore_left_splitter_sizes(self) -> None:
        if not hasattr(self, "left_splitter"):
            return
        sizes = self.load_left_splitter_sizes_setting() or self.default_left_splitter_sizes()
        self.left_splitter.setSizes(self.normalize_left_splitter_sizes(sizes))

    def schedule_startup_left_splitter_restore(self) -> None:
        QTimer.singleShot(0, self.restore_left_splitter_sizes)
        QTimer.singleShot(150, self.restore_left_splitter_sizes)

    def save_splitter_sizes(self) -> None:
        self.db.set_setting("main_splitter_sizes", json.dumps(self.main_splitter.sizes()))
        self.db.set_setting("left_splitter_sizes_v3", json.dumps(self.left_splitter.sizes()))
        self.db.set_setting("text_splitter_sizes", json.dumps(self.text_splitter.sizes()))

    def save_ui_state(self) -> None:
        geom = self.normalGeometry() if self.isMaximized() else self.geometry()
        data = {
            "x": geom.x(),
            "y": geom.y(),
            "w": geom.width(),
            "h": geom.height(),
            "maximized": self.isMaximized(),
        }
        self.db.set_setting("window_geometry", json.dumps(data, ensure_ascii=False))
        self.save_splitter_sizes()
        self.db.set_setting("prompt_sort_mode", normalize_prompt_sort_mode(getattr(self, "prompt_sort_mode", DEFAULT_PROMPT_SORT_MODE)))
        for section in self.collapsible_sections:
            self.db.set_setting(section.state_key, "1" if section.is_collapsed() else "0")

    def on_section_collapsed_changed(self, state_key: str, collapsed: bool) -> None:
        self.db.set_setting(state_key, "1" if collapsed else "0")

    def tag_color_for_name(self, tag_name: str) -> str:
        return self.tag_color_map.get(tag_name, self.db.get_effective_tag_color(tag_name))

    def reload_preset_combo(self) -> None:
        current = self.preset_combo.currentText() if hasattr(self, "preset_combo") else ""
        self.tag_presets = {}
        for row in self.db.list_tag_presets():
            self.tag_presets[str(row["name"])] = tags_from_json(str(row["tags_json"]))
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("タグプリセットを追加...")
        for name in self.tag_presets:
            self.preset_combo.addItem(name)
        if current:
            index = self.preset_combo.findText(current)
            if index >= 0:
                self.preset_combo.setCurrentIndex(index)
        self.preset_combo.blockSignals(False)

    def mark_dirty(self) -> None:
        if not self.loading:
            self.dirty = True

    def selected_filter_tags(self) -> list[str]:
        tags: list[str] = []
        for button in self.tag_filter_buttons:
            if button.isChecked():
                tag_name = str(button.property("tag_name") or "")
                if tag_name:
                    tags.append(tag_name)
        return tags

    def refresh_tags(self) -> None:
        checked = set(self.selected_filter_tags())
        self.tag_list_loading = True
        self.tag_color_map = {}
        while self.tag_filter_layout.count():
            item = self.tag_filter_layout.takeAt(0)
            widget = item.widget() if item else None
            if widget:
                widget.deleteLater()
        self.tag_filter_buttons = []

        for row in self.db.list_tags_with_counts():
            name = str(row["name"])
            count = int(row["count"])
            color = effective_color_from_row(row)
            self.tag_color_map[name] = color
            if int(row["visible"] if "visible" in row.keys() else 1) == 0:
                continue
            btn = QToolButton()
            btn.setText(f"{name} ({count})")
            btn.setCheckable(True)
            btn.setChecked(name in checked)
            btn.setProperty("tag_name", name)
            btn.setToolTip(f"カテゴリ: {row['category']}")
            btn.setStyleSheet(chip_style(color, checked=btn.isChecked()))
            btn.toggled.connect(lambda is_checked, b=btn: self.on_tag_filter_toggled(b, is_checked))
            self.tag_filter_layout.addWidget(btn)
            self.tag_filter_buttons.append(btn)
        self.tag_filter_content.updateGeometry()
        self.tags_editor.refresh_chips()
        self.tag_list_loading = False

    def on_tag_filter_toggled(self, button: QToolButton, checked: bool) -> None:
        tag_name = str(button.property("tag_name") or "")
        button.setStyleSheet(chip_style(self.tag_color_for_name(tag_name), checked=checked))
        if not self.tag_list_loading:
            self.refresh_prompt_list()

    def prompt_row_matches_filters(self, row: PromptRow, query: str, selected_tags: set[str], only_fav: bool) -> bool:
        if only_fav and not row.favorite:
            return False
        if selected_tags and not selected_tags.issubset(set(row.tags)):
            return False
        haystack = "\n".join(
            [
                row.title,
                row.prompt,
                row.negative_prompt,
                row.description,
                row.engine,
                row.model,
                row.project,
                " ".join(row.tags),
            ]
        ).lower()
        return not query or query in haystack

    def setup_prompt_list_item(self, item: QListWidgetItem, row: PromptRow) -> None:
        # The visible row is drawn by PromptListItemWidget.
        # Keep the QListWidgetItem display text empty so Qt's default item text
        # does not bleed into the reserved thumbnail area behind the custom widget.
        item.setText("")
        item.setData(Qt.UserRole, row.id)
        item.setData(Qt.UserRole + 1, row.title or "(無題)")
        item.setData(Qt.UserRole + 2, row.pinned)
        item.setToolTip(f"更新: {row.updated_at}\nタグ: {', '.join(row.tags)}")

    def add_prompt_row_to_list(self, target_list: QListWidget, row: PromptRow) -> None:
        item = QListWidgetItem()
        self.setup_prompt_list_item(item, row)
        widget = PromptListItemWidget(row, QSize(72, 72), show_thumbnail=self.current_workspace_show_thumbnail())
        item.setSizeHint(widget.sizeHint())
        target_list.addItem(item)
        target_list.setItemWidget(item, widget)

    def find_prompt_item_in_visible_lists(self, prompt_id: int) -> tuple[QListWidget | None, QListWidgetItem | None]:
        for target_list in (self.pinned_prompt_list, self.prompt_list):
            for index in range(target_list.count()):
                item = target_list.item(index)
                if item is not None and int(item.data(Qt.UserRole)) == int(prompt_id):
                    return target_list, item
        return None, None

    def update_prompt_list_item_in_place(self, target_list: QListWidget, item: QListWidgetItem, row: PromptRow) -> None:
        old_widget = target_list.itemWidget(item)
        if old_widget is not None:
            target_list.removeItemWidget(item)
            old_widget.deleteLater()
        self.setup_prompt_list_item(item, row)
        widget = PromptListItemWidget(row, QSize(72, 72), show_thumbnail=self.current_workspace_show_thumbnail())
        item.setSizeHint(widget.sizeHint())
        target_list.setItemWidget(item, widget)

    def remove_prompt_item_from_list(self, target_list: QListWidget, item: QListWidgetItem) -> None:
        row_index = target_list.row(item)
        if row_index < 0:
            return
        old_widget = target_list.itemWidget(item)
        if old_widget is not None:
            target_list.removeItemWidget(item)
            old_widget.deleteLater()
        removed_item = target_list.takeItem(row_index)
        del removed_item

    def update_saved_prompt_in_visible_list(self, prompt_id: int, add_missing: bool = True) -> bool:
        row = self.db.get_prompt_row(prompt_id)
        if row is None:
            return False
        row = self.prompt_row_for_display(row)

        query = self.search_edit.text().strip().lower()
        selected_tags = set(self.selected_filter_tags())
        only_fav = self.only_favorite_checkbox.isChecked()
        should_show_normal = self.prompt_row_matches_filters(row, query, selected_tags, only_fav)
        target_list, item = self.find_prompt_item_in_visible_lists(prompt_id)

        self._prompt_selection_syncing = True
        self.prompt_list.blockSignals(True)
        self.pinned_prompt_list.blockSignals(True)
        try:
            if row.pinned:
                if target_list is self.pinned_prompt_list and item is not None:
                    self.update_prompt_list_item_in_place(target_list, item, row)
                elif add_missing:
                    if target_list is not None and item is not None:
                        self.remove_prompt_item_from_list(target_list, item)
                    self.add_prompt_row_to_list(self.pinned_prompt_list, row)
                return True

            if should_show_normal:
                if target_list is self.prompt_list and item is not None:
                    self.update_prompt_list_item_in_place(target_list, item, row)
                elif add_missing:
                    if target_list is not None and item is not None:
                        self.remove_prompt_item_from_list(target_list, item)
                    self.add_prompt_row_to_list(self.prompt_list, row)
                return True

            if target_list is not None and item is not None:
                self.remove_prompt_item_from_list(target_list, item)
            return False
        finally:
            self.prompt_list.blockSignals(False)
            self.pinned_prompt_list.blockSignals(False)
            self._prompt_selection_syncing = False
            self.update_pinned_prompt_area_height()
            self.schedule_pinned_prompt_area_update()

    def update_prompt_rows_in_visible_list_in_place(self, *prompt_ids: int | None) -> None:
        seen: set[int] = set()
        for prompt_id in prompt_ids:
            if prompt_id is None:
                continue
            try:
                pid = int(prompt_id)
            except Exception:
                continue
            if pid in seen:
                continue
            seen.add(pid)
            self.update_saved_prompt_in_visible_list(pid, add_missing=False)

    def update_current_prompt_row_in_visible_list_in_place(self) -> None:
        self.update_prompt_rows_in_visible_list_in_place(self.current_prompt_id)

    def schedule_pinned_prompt_area_update(self) -> None:
        if getattr(self, "_pending_pinned_area_update", False):
            return
        self._pending_pinned_area_update = True

        def _run() -> None:
            self._pending_pinned_area_update = False
            self.update_pinned_prompt_area_height()

        QTimer.singleShot(0, _run)

    def update_pinned_prompt_area_height(self) -> None:
        count = self.pinned_prompt_list.count()
        if count <= 0:
            self.pinned_prompt_group.setVisible(False)
            self.pinned_prompt_list.setFixedHeight(0)
            self.pinned_prompt_group.setFixedHeight(0)
            return

        self.pinned_prompt_group.setVisible(True)
        self.pinned_prompt_list.doItemsLayout()
        self.pinned_prompt_list.updateGeometries()
        self.pinned_prompt_list.viewport().updateGeometry()

        row_height = 0
        for index in range(count):
            item = self.pinned_prompt_list.item(index)
            if item is None:
                continue
            item_height = self.pinned_prompt_list.sizeHintForRow(index)
            if item_height <= 0:
                item_height = item.sizeHint().height()
            widget = self.pinned_prompt_list.itemWidget(item)
            if widget is not None:
                widget.ensurePolished()
                item_height = max(item_height, widget.sizeHint().height(), widget.minimumSizeHint().height())
            row_height += max(item_height, self.pinned_prompt_list.iconSize().height() + 8)

        spacing_height = max(0, count - 1) * self.pinned_prompt_list.spacing()
        frame_height = self.pinned_prompt_list.frameWidth() * 2
        list_height = row_height + spacing_height + frame_height + 8
        margins = self.pinned_prompt_group.layout().contentsMargins()
        title_height = max(24, self.pinned_prompt_group.fontMetrics().height() + 10)
        group_height = list_height + margins.top() + margins.bottom() + title_height

        self.pinned_prompt_list.setFixedHeight(list_height)
        self.pinned_prompt_group.setFixedHeight(group_height)
        self.pinned_prompt_list.updateGeometry()
        self.pinned_prompt_group.updateGeometry()

    def refresh_prompt_list(self) -> None:
        if self.loading:
            return
        current_id = self.current_prompt_id
        query = self.search_edit.text().strip().lower()
        selected_tags = set(self.selected_filter_tags())
        only_fav = self.only_favorite_checkbox.isChecked()
        rows = [self.prompt_row_for_display(row) for row in self.db.list_prompts(self.prompt_sort_mode)]

        self.prompt_list.blockSignals(True)
        self.pinned_prompt_list.blockSignals(True)
        self.prompt_list.clear()
        self.pinned_prompt_list.clear()
        matched_count = 0
        pinned_count = 0
        for row in rows:
            if row.pinned:
                self.add_prompt_row_to_list(self.pinned_prompt_list, row)
                pinned_count += 1
                continue
            if not self.prompt_row_matches_filters(row, query, selected_tags, only_fav):
                continue
            self.add_prompt_row_to_list(self.prompt_list, row)
            matched_count += 1

        selected_item: QListWidgetItem | None = None
        selected_list: QListWidget | None = None
        if current_id is not None:
            for target_list in (self.pinned_prompt_list, self.prompt_list):
                for index in range(target_list.count()):
                    item = target_list.item(index)
                    if item is not None and int(item.data(Qt.UserRole)) == int(current_id):
                        selected_item = item
                        selected_list = target_list
                        break
                if selected_item is not None:
                    break
        if selected_item is not None and selected_list is not None:
            selected_list.setCurrentItem(selected_item)

        self.prompt_list.blockSignals(False)
        self.pinned_prompt_list.blockSignals(False)
        self.update_pinned_prompt_area_height()
        self.schedule_pinned_prompt_area_update()
        if pinned_count:
            self.statusBar().showMessage(f"{matched_count} 件表示 / ピン留め {pinned_count} 件 / DB: {self.db_path}")
        else:
            self.statusBar().showMessage(f"{matched_count} 件表示 / DB: {self.db_path}")

    def clear_tag_filters(self) -> None:
        self.tag_list_loading = True
        for button in self.tag_filter_buttons:
            button.setChecked(False)
            tag_name = str(button.property("tag_name") or "")
            button.setStyleSheet(chip_style(self.tag_color_for_name(tag_name), checked=False))
        self.tag_list_loading = False

        self.only_favorite_checkbox.blockSignals(True)
        self.only_favorite_checkbox.setChecked(False)
        self.only_favorite_checkbox.blockSignals(False)

        if self.search_edit.text():
            self.search_edit.clear()
        else:
            self.refresh_prompt_list()

    def focus_search_box(self) -> None:
        self.search_edit.setFocus(Qt.ShortcutFocusReason)
        self.search_edit.selectAll()

    def maybe_save_dirty(self) -> bool:
        if not self.dirty or self.current_prompt_id is None:
            return True
        result = QMessageBox.question(
            self,
            "未保存の変更",
            "現在のカードに未保存の変更があります。保存しますか？",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if result == QMessageBox.Cancel:
            return False
        if result == QMessageBox.Save:
            self.save_current_prompt()
        return True

    def restore_prompt_selection_without_loading(self, prompt_id: int | None) -> None:
        if prompt_id is None:
            return
        target_list, item = self.find_prompt_item_in_visible_lists(int(prompt_id))
        self._prompt_selection_syncing = True
        self.prompt_list.blockSignals(True)
        self.pinned_prompt_list.blockSignals(True)
        try:
            self.prompt_list.setCurrentItem(None)
            self.prompt_list.clearSelection()
            self.pinned_prompt_list.setCurrentItem(None)
            self.pinned_prompt_list.clearSelection()
            if target_list is not None and item is not None:
                target_list.setCurrentItem(item)
                item.setSelected(True)
        finally:
            self.prompt_list.blockSignals(False)
            self.pinned_prompt_list.blockSignals(False)
            self._prompt_selection_syncing = False

    def on_prompt_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if self._prompt_selection_syncing:
            return
        if current is None:
            return
        prompt_id = int(current.data(Qt.UserRole))
        if self.current_prompt_id is not None and prompt_id == int(self.current_prompt_id):
            return
        previous_prompt_id = self.current_prompt_id
        if not self.maybe_save_dirty():
            self.restore_prompt_selection_without_loading(previous_prompt_id)
            return

        sender = self.sender()
        other_list: QListWidget | None = None
        if sender is self.pinned_prompt_list:
            other_list = self.prompt_list
        elif sender is self.prompt_list:
            other_list = self.pinned_prompt_list
        if other_list is not None:
            other_list.blockSignals(True)
            other_list.setCurrentItem(None)
            other_list.clearSelection()
            other_list.blockSignals(False)
        self.load_prompt(prompt_id)

    def clear_detail(self) -> None:
        self.cancel_material_list_loading()
        self.loading = True
        self.current_prompt_id = None
        self.title_edit.clear()
        self.engine_edit.setCurrentText("")
        self.model_edit.setCurrentText("")
        self.project_edit.setCurrentText("")
        self.tags_editor.set_tags([])
        self.favorite_check.setChecked(False)
        self.rating_combo.setCurrentIndex(0)
        self.prompt_edit.clear()
        self.negative_edit.clear()
        self.description_edit.clear()
        self.image_list.clear()
        self.loading = False
        self.dirty = False

    def load_prompt(self, prompt_id: int) -> None:
        row = self.db.get_prompt(prompt_id)
        if not row:
            return
        self.loading = True
        self.current_prompt_id = prompt_id
        self.title_edit.setText(str(row["title"]))
        self.engine_edit.setCurrentText(str(row["engine"]))
        self.model_edit.setCurrentText(str(row["model"]))
        self.project_edit.setCurrentText(str(row["project"]))
        self.tags_editor.set_tags(self.db.list_prompt_tags(prompt_id))
        self.favorite_check.setChecked(bool(row["favorite"]))
        rating = max(0, min(5, int(row["rating"])))
        self.rating_combo.setCurrentIndex(rating)
        self.prompt_edit.setPlainText(str(row["prompt"]))
        self.negative_edit.setPlainText(str(row["negative_prompt"]))
        self.description_edit.setPlainText(str(row["description"]))
        assets_changed = self.sync_current_prompt_assets()
        self.refresh_images(sync_assets=False)
        if assets_changed:
            self.update_prompt_rows_in_visible_list_in_place(prompt_id)
        self.loading = False
        self.dirty = False
        self.statusBar().showMessage(f"読み込み: {row['title']}")

    def gather_current_data(self) -> dict:
        return {
            "title": self.title_edit.text().strip() or "(無題)",
            "prompt": self.prompt_edit.toPlainText(),
            "negative_prompt": self.negative_edit.toPlainText(),
            "description": self.description_edit.toPlainText(),
            "engine": self.engine_edit.currentText().strip(),
            "model": self.model_edit.currentText().strip(),
            "project": self.project_edit.currentText().strip(),
            "rating": self.rating_combo.currentIndex(),
            "favorite": 1 if self.favorite_check.isChecked() else 0,
        }

    def save_current_prompt(self) -> None:
        data = self.gather_current_data()
        created_new = self.current_prompt_id is None
        if created_new:
            self.current_prompt_id = self.db.create_prompt(**data)
        else:
            self.db.update_prompt(self.current_prompt_id, data)
        self.db.set_prompt_tags(self.current_prompt_id, self.tags_editor.get_tags())
        self.db.ensure_meta_options_from_prompt_data(data)
        self.dirty = False
        self.refresh_tags()
        self.reload_preset_combo()
        self.reload_meta_combos()
        if created_new:
            self.refresh_prompt_list()
            self.select_prompt_in_list(self.current_prompt_id)
            self.statusBar().showMessage("保存しました")
            return

        still_visible = self.update_saved_prompt_in_visible_list(self.current_prompt_id)
        if still_visible:
            self.statusBar().showMessage("保存しました")
        else:
            self.statusBar().showMessage("保存しました。現在の絞り込み条件から外れたため一覧から非表示にしました")

    def select_prompt_in_list(self, prompt_id: int) -> None:
        self._prompt_selection_syncing = True
        try:
            for target_list, other_list in ((self.pinned_prompt_list, self.prompt_list), (self.prompt_list, self.pinned_prompt_list)):
                for i in range(target_list.count()):
                    item = target_list.item(i)
                    if int(item.data(Qt.UserRole)) == int(prompt_id):
                        other_list.blockSignals(True)
                        other_list.setCurrentItem(None)
                        other_list.clearSelection()
                        other_list.blockSignals(False)
                        target_list.setCurrentItem(item)
                        target_list.scrollToItem(item)
                        return
        finally:
            self._prompt_selection_syncing = False

    def new_prompt(self) -> None:
        if not self.maybe_save_dirty():
            return
        new_id = self.db.create_prompt("新規カード")
        self.db.set_prompt_tags(new_id, [])
        self.current_prompt_id = new_id
        self.refresh_prompt_list()
        self.select_prompt_in_list(new_id)
        self.load_prompt(new_id)
        self.title_edit.selectAll()
        self.title_edit.setFocus()

    def duplicate_prompt(self) -> None:
        if self.current_prompt_id is None:
            return
        if not self.maybe_save_dirty():
            return
        new_id = self.db.duplicate_prompt(self.current_prompt_id)
        if new_id is None:
            return
        self.current_prompt_id = new_id
        self.refresh_tags()
        self.refresh_prompt_list()
        self.select_prompt_in_list(new_id)
        self.load_prompt(new_id)
        self.statusBar().showMessage("複製しました。メディアはコピーせず、カード情報だけ複製しています。")

    def show_prompt_list_context_menu(self, pos: QPoint, source_list: QListWidget | None = None) -> None:
        source_list = source_list or self.prompt_list
        item = source_list.itemAt(pos)
        if item is None:
            return
        target_id = int(item.data(Qt.UserRole))
        source_list.setCurrentItem(item)
        if self.current_prompt_id != target_id:
            return
        row = self.db.get_prompt(target_id)
        if row is None:
            return
        is_pinned = bool(row["pinned"])
        menu = QMenu(self)
        pin_action = menu.addAction("ピン留め解除" if is_pinned else "ピン留め")
        menu.addSeparator()
        open_assets_action = menu.addAction("メディアフォルダを開く")
        menu.addSeparator()
        copy_action = menu.addAction("プロンプトをコピー")
        copy_full_action = menu.addAction("タイトル+プロンプトをコピー")
        menu.addSeparator()
        duplicate_action = menu.addAction("複製")
        delete_action = menu.addAction("削除")
        selected = menu.exec(source_list.viewport().mapToGlobal(pos))
        if selected == pin_action:
            self.toggle_prompt_pinned(target_id, not is_pinned)
        elif selected == open_assets_action:
            self.open_prompt_asset_folder(target_id)
        elif selected == copy_action:
            self.copy_prompt()
        elif selected == copy_full_action:
            self.copy_full_prompt()
        elif selected == duplicate_action:
            self.duplicate_prompt()
        elif selected == delete_action:
            self.delete_current_prompt()

    def toggle_prompt_pinned(self, prompt_id: int, pinned: bool) -> None:
        self.db.set_prompt_pinned(prompt_id, pinned)
        self.refresh_prompt_list()
        self.select_prompt_in_list(prompt_id)
        self.statusBar().showMessage("ピン留めしました" if pinned else "ピン留めを解除しました")

    def delete_current_prompt(self) -> None:
        if self.current_prompt_id is None:
            return
        title = self.title_edit.text().strip() or "(無題)"
        result = QMessageBox.question(
            self,
            "削除確認",
            f"「{title}」を削除しますか？\nDB上の登録を削除し、関連メディアファイルはWindowsのゴミ箱へ移動します。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return

        deleted_id = self.current_prompt_id
        image_rows = self.db.list_images(deleted_id)
        prompt_asset_dir = self.prompt_asset_dir(deleted_id)
        recycle_targets: list[Path] = []
        if prompt_asset_dir.exists():
            recycle_targets.append(prompt_asset_dir)
        for row in image_rows:
            file_path = self.material_file_path_from_row(row)
            thumb_path = self.material_thumb_path_from_row(row)
            if file_path.exists() and not (prompt_asset_dir.exists() and is_relative_to_path(file_path, prompt_asset_dir)):
                recycle_targets.append(file_path)
            if thumb_path and thumb_path.exists() and not (prompt_asset_dir.exists() and is_relative_to_path(thumb_path, prompt_asset_dir)):
                recycle_targets.append(thumb_path)

        self.db.delete_prompt(deleted_id)
        moved, errors = move_paths_to_recycle_bin(recycle_targets)
        self.clear_detail()
        self.refresh_tags()
        self.refresh_prompt_list()
        if errors:
            QMessageBox.warning(self, "削除警告", "登録は削除しましたが、一部ファイルをゴミ箱へ移動できませんでした。\n\n" + "\n".join(errors[:5]))
            self.statusBar().showMessage(f"削除しました。一部ファイル移動失敗: {len(errors)} 件")
        else:
            self.statusBar().showMessage(f"削除しました。メディアファイルをゴミ箱へ移動: {moved} 件")

    def copy_prompt(self) -> None:
        text = strip_prompt_comment_lines(self.prompt_edit.toPlainText())
        QGuiApplication.clipboard().setText(text)
        self.statusBar().showMessage("プロンプトをコピーしました")

    def copy_full_prompt(self) -> None:
        parts = []
        title = self.title_edit.text().strip()
        if title:
            parts.append(f"# {title}")
        prompt = strip_prompt_comment_lines(self.prompt_edit.toPlainText()).strip()
        if prompt:
            parts.append(prompt)
        negative = strip_prompt_comment_lines(self.negative_edit.toPlainText()).strip()
        if negative:
            parts.append("\n[Negative / Sub Prompt]\n" + negative)
        QGuiApplication.clipboard().setText("\n\n".join(parts))
        self.statusBar().showMessage("タイトル+プロンプトをコピーしました")

    def add_selected_preset(self) -> None:
        name = self.preset_combo.currentText()
        if name not in self.tag_presets:
            return
        self.tags_editor.add_tags(self.tag_presets[name])
        self.mark_dirty()

    def open_tag_manager(self) -> None:
        dialog = TagManagerDialog(self.db, self.tag_color_for_name, self)
        dialog.exec()
        self.refresh_tags()
        self.reload_preset_combo()
        self.reload_meta_combos()
        if self.current_prompt_id is not None and not self.dirty:
            self.loading = True
            self.tags_editor.set_tags(self.db.list_prompt_tags(self.current_prompt_id))
            self.loading = False
        self.refresh_prompt_list()

    def load_material_label_styles(self) -> dict[int, tuple[str, str]]:
        styles: dict[int, tuple[str, str]] = {}
        for label_id in range(1, 10):
            default_fg, default_bg = DEFAULT_MATERIAL_LABEL_COLORS.get(label_id, ("#ffffff", "#555555"))
            fg = normalize_hex_color(self.db.get_setting(f"material_label_{label_id}_fg", default_fg)) or default_fg
            bg = normalize_hex_color(self.db.get_setting(f"material_label_{label_id}_bg", default_bg)) or default_bg
            styles[label_id] = (fg, bg)
        return styles

    def open_material_label_manager(self) -> None:
        dialog = MaterialLabelManagerDialog(self.db, self)
        if dialog.exec():
            self.material_label_styles = self.load_material_label_styles()
            self.refresh_material_label_colors()
            self.statusBar().showMessage("ラベル設定を更新しました")

    def material_label_style(self, label_id: int) -> tuple[str, str] | None:
        label_id = max(0, min(9, int(label_id)))
        if label_id <= 0:
            return None
        return self.material_label_styles.get(label_id)

    def apply_material_label_to_item(self, item: QListWidgetItem, label_id: int) -> None:
        style = self.material_label_style(label_id)
        # 背景色は QListWidgetItem の BackgroundRole だと IconMode + stylesheet で
        # 描画されない/選択色に負けるため、MaterialListItemDelegate 側で描く。
        item.setBackground(QBrush())
        if not style:
            item.setForeground(QBrush())
        else:
            fg, _bg = style
            item.setForeground(QBrush(QColor(fg)))
        if hasattr(self, "image_list"):
            self.image_list.viewport().update()

    def refresh_material_label_colors(self) -> None:
        for index in range(self.image_list.count()):
            item = self.image_list.item(index)
            if item is None:
                continue
            label_id = safe_int(item.data(Qt.UserRole + 2), 0)
            self.apply_material_label_to_item(item, label_id)

    def set_selected_material_label(self, label_id: int) -> None:
        image_id = self.selected_image_id()
        if image_id is None:
            return
        label_id = max(0, min(9, int(label_id)))
        self.db.update_image_label(image_id, label_id)
        item = self.image_list.currentItem()
        if item is not None:
            item.setData(Qt.UserRole + 2, label_id)
            self.apply_material_label_to_item(item, label_id)
        self.update_current_prompt_row_in_visible_list_in_place()
        if label_id:
            self.statusBar().showMessage(f"メディアラベル {label_id} を設定しました")
        else:
            self.statusBar().showMessage("メディアラベルを解除しました")


    def ensure_current_prompt_saved_for_images(self) -> bool:
        if self.current_prompt_id is None:
            self.save_current_prompt()
        elif self.dirty:
            self.save_current_prompt()
        return self.current_prompt_id is not None

    def choose_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "メディアを選択",
            str(Path.home()),
            "All Files (*.*);;Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.ico *.svg *.tif *.tiff *.tga);;Videos (*.mp4 *.mov *.avi *.mkv *.webm)",
        )
        if files:
            self.add_images_from_paths([Path(f) for f in files])

    def add_external_image_to_current_prompt(self, path: Path) -> None:
        if self.current_prompt_id is None:
            QMessageBox.information(self, "メディアへ追加", "追加先のカードがありません。")
            return
        self.add_images_from_paths([path])

    def add_external_image_to_new_prompt(self, path: Path) -> None:
        path = Path(path)
        if not path.exists() or not path.is_file():
            QMessageBox.warning(self, "メディアへ追加エラー", "画像ファイルが見つかりません。")
            return
        if not self.maybe_save_dirty():
            return
        title = path.stem.strip() or "新規カード"
        new_id = self.db.create_prompt(title)
        self.db.set_prompt_tags(new_id, [])
        self.current_prompt_id = new_id
        self.refresh_prompt_list()
        self.select_prompt_in_list(new_id)
        self.load_prompt(new_id)
        self.add_images_from_paths([path])

    def add_selected_material_to_new_prompt(self) -> None:
        image_id = self.selected_image_id()
        if image_id is None:
            return
        row = self.db.get_image(image_id)
        if not row:
            return
        src_path = self.material_file_path_from_row(row)
        if not src_path.exists() or not src_path.is_file():
            QMessageBox.warning(self, "メディア追加エラー", f"メディアファイルが見つかりません。\n{src_path}")
            return
        if not self.maybe_save_dirty():
            return

        original_name = str(row["original_name"] if "original_name" in row.keys() else "")
        title_source = original_name or src_path.name
        title = Path(title_source).stem.strip() or src_path.stem.strip() or "新規カード"
        new_id = self.db.create_prompt(title)
        self.db.set_prompt_tags(new_id, [])

        if not self.transfer_material_to_prompt(image_id, new_id, copy_mode=True):
            self.db.delete_prompt(new_id)
            self.refresh_prompt_list()
            self.select_prompt_in_list(self.current_prompt_id) if self.current_prompt_id is not None else None
            return

        self.current_prompt_id = new_id
        self.refresh_prompt_list()
        self.select_prompt_in_list(new_id)
        self.load_prompt(new_id)
        self.statusBar().showMessage("新規カードを作成してメディアを追加しました")

    def material_destination_dir(self, prompt_id: int, media_type: str, src_path: Path) -> Path:
        image_dir, file_dir, _thumb_dir = self.ensure_prompt_asset_dirs(prompt_id)
        return image_dir if (media_type or media_type_for_path(src_path)) == "image" else file_dir

    def transfer_material_to_prompt(self, image_id: int, target_prompt_id: int, copy_mode: bool = False) -> bool:
        row = self.db.get_image(image_id)
        if not row:
            return False
        source_prompt_id = int(row["prompt_id"])
        target_prompt_id = int(target_prompt_id)
        if source_prompt_id == target_prompt_id and not copy_mode:
            self.statusBar().showMessage("同じカードへのメディア移動は行いませんでした")
            return False

        src_path = self.material_file_path_from_row(row)
        if not src_path.exists() or not src_path.is_file():
            QMessageBox.warning(self, "メディアD&Dエラー", f"メディアファイルが見つかりません。\n{src_path}")
            return False

        media_type = str(row["media_type"] if "media_type" in row.keys() else media_type_for_path(src_path))
        target_dir = self.material_destination_dir(target_prompt_id, media_type, src_path)
        target_dir.mkdir(parents=True, exist_ok=True)
        dest_path = unique_path(target_dir / safe_filename(src_path.name))
        caption = str(row["caption"] if "caption" in row.keys() else "")
        original_name = str(row["original_name"] if "original_name" in row.keys() else src_path.name)
        label_id = safe_int(row["label_id"] if "label_id" in row.keys() else 0, 0)

        try:
            if copy_mode:
                shutil.copy2(src_path, dest_path)
                new_image_id = self.db.add_image(
                    target_prompt_id,
                    self.absolute_path_to_stored(dest_path),
                    "",
                    caption=caption,
                    media_type=media_type,
                    original_name=original_name or src_path.name,
                )
                thumb_path = self.create_material_thumbnail(dest_path, new_image_id, target_prompt_id, media_type)
                if thumb_path:
                    self.db.update_image_thumbnail(new_image_id, self.absolute_path_to_stored(thumb_path))
                if label_id:
                    self.db.update_image_label(new_image_id, label_id)
                message = "メディアをコピーしました"
            else:
                old_thumb_path = self.material_thumb_path_from_row(row)
                if src_path.resolve() != dest_path.resolve():
                    shutil.move(str(src_path), str(dest_path))
                thumb_path = self.create_material_thumbnail(dest_path, image_id, target_prompt_id, media_type)
                new_thumb_path = self.absolute_path_to_stored(thumb_path) if thumb_path else ""
                self.db.move_image_to_prompt(image_id, target_prompt_id, self.absolute_path_to_stored(dest_path), new_thumb_path)
                if old_thumb_path and old_thumb_path.exists() and (not thumb_path or old_thumb_path.resolve() != thumb_path.resolve()):
                    try:
                        old_thumb_path.unlink()
                    except Exception:
                        pass
                remove_empty_dirs(self.prompt_asset_dir(source_prompt_id))
                message = "メディアを移動しました"
        except Exception as exc:
            QMessageBox.warning(self, "メディアD&Dエラー", f"メディアを{'コピー' if copy_mode else '移動'}できませんでした。\n\n{exc}")
            return False

        if self.current_prompt_id in (source_prompt_id, target_prompt_id):
            self.refresh_images()
        self.update_prompt_rows_in_visible_list_in_place(source_prompt_id, target_prompt_id)
        self.statusBar().showMessage(message)
        return True

    def clipboard_image_to_qimage(self) -> QImage:
        clipboard = QGuiApplication.clipboard()
        mime = clipboard.mimeData()
        if mime is not None and mime.hasImage():
            data = mime.imageData()
            if isinstance(data, QImage):
                return QImage(data)
            if isinstance(data, QPixmap):
                return data.toImage()
        image = clipboard.image()
        return QImage(image) if not image.isNull() else QImage()

    def add_clipboard_image_as_material(self, image: QImage) -> bool:
        if image.isNull():
            return False
        if not self.ensure_current_prompt_saved_for_images():
            return False
        assert self.current_prompt_id is not None

        prompt_image_dir, _prompt_file_dir, _prompt_thumb_dir = self.ensure_prompt_asset_dirs(self.current_prompt_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = unique_path(prompt_image_dir / f"clipboard_{timestamp}.png")
        if not image.save(str(dest), "PNG"):
            QMessageBox.warning(self, "メディア貼り付けエラー", "クリップボード画像をPNGとして保存できませんでした。")
            return False

        image_id = self.db.add_image(
            self.current_prompt_id,
            self.absolute_path_to_stored(dest),
            "",
            media_type="image",
            original_name="clipboard.png",
        )
        thumb_path = self.create_material_thumbnail(dest, image_id, self.current_prompt_id, "image")
        if thumb_path:
            self.db.update_image_thumbnail(image_id, self.absolute_path_to_stored(thumb_path))

        self.refresh_images(sync_assets=False)
        self.update_current_prompt_row_in_visible_list_in_place()
        self.statusBar().showMessage(f"クリップボード画像をメディアへ追加しました: {dest.name}")
        return True

    def paste_material_from_clipboard(self) -> None:
        clipboard = QGuiApplication.clipboard()
        mime = clipboard.mimeData()
        if mime is None:
            QMessageBox.information(self, "メディア貼り付け", "クリップボードに貼り付け可能なメディアがありません。")
            return

        if mime.hasUrls():
            paths = [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]
            paths = [path for path in paths if path.exists() and path.is_file()]
            if paths:
                self.add_images_from_paths(paths)
                return

        image = self.clipboard_image_to_qimage()
        if not image.isNull():
            self.add_clipboard_image_as_material(image)
            return

        QMessageBox.information(self, "メディア貼り付け", "クリップボードに貼り付け可能なファイルまたは画像がありません。")

    def add_images_from_paths(self, paths: Iterable[Path]) -> None:
        paths = [Path(p) for p in paths if Path(p).exists() and Path(p).is_file()]
        if not paths:
            return
        if not self.ensure_current_prompt_saved_for_images():
            return
        assert self.current_prompt_id is not None
        added = 0
        prompt_image_dir, prompt_file_dir, _prompt_thumb_dir = self.ensure_prompt_asset_dirs(self.current_prompt_id)
        video_count = sum(1 for p in paths if p.suffix.lower() in SUPPORTED_VIDEO_EXTS)
        video_mode_for_all: Optional[str] = None

        for src in paths:
            try:
                ext = src.suffix.lower()
                if ext in SUPPORTED_IMAGE_EXTS:
                    dest = unique_path(prompt_image_dir / safe_filename(src.name))
                    if src.resolve() != dest.resolve():
                        shutil.copy2(src, dest)
                    image_id = self.db.add_image(self.current_prompt_id, self.absolute_path_to_stored(dest), "", media_type="image", original_name=src.name)
                    thumb_path = self.create_material_thumbnail(dest, image_id, self.current_prompt_id, "image")
                    if thumb_path:
                        self.db.update_image_thumbnail(image_id, self.absolute_path_to_stored(thumb_path))
                    added += 1

                elif ext in SUPPORTED_VIDEO_EXTS:
                    if video_mode_for_all is not None:
                        mode = video_mode_for_all
                    else:
                        mode, apply_all = self.ask_video_import_mode(src, allow_apply_all=video_count > 1)
                        if apply_all and mode is not None:
                            video_mode_for_all = mode
                    if mode is None:
                        continue
                    if mode == "copy":
                        dest = unique_path(prompt_file_dir / safe_filename(src.name))
                        if src.resolve() != dest.resolve():
                            shutil.copy2(src, dest)
                        image_id = self.db.add_image(self.current_prompt_id, self.absolute_path_to_stored(dest), "", media_type="video", original_name=src.name)
                        thumb_path = self.create_material_thumbnail(dest, image_id, self.current_prompt_id, "video")
                        if not thumb_path:
                            thumb_path = self.create_material_thumbnail(dest, image_id, self.current_prompt_id, media_type_for_path(dest))
                        if thumb_path:
                            self.db.update_image_thumbnail(image_id, self.absolute_path_to_stored(thumb_path))
                    else:
                        dest = self.generate_video_snapshot(src, prompt_image_dir)
                        image_id = self.db.add_image(self.current_prompt_id, self.absolute_path_to_stored(dest), "", media_type="image", original_name=src.name)
                        thumb_path = self.create_material_thumbnail(dest, image_id, self.current_prompt_id, "image")
                        if thumb_path:
                            self.db.update_image_thumbnail(image_id, self.absolute_path_to_stored(thumb_path))
                    added += 1

                else:
                    dest = unique_path(prompt_file_dir / safe_filename(src.name))
                    if src.resolve() != dest.resolve():
                        shutil.copy2(src, dest)
                    image_id = self.db.add_image(self.current_prompt_id, self.absolute_path_to_stored(dest), "", media_type=media_type_for_path(src), original_name=src.name)
                    thumb_path = self.create_material_thumbnail(dest, image_id, self.current_prompt_id, media_type_for_path(dest))
                    if thumb_path:
                        self.db.update_image_thumbnail(image_id, self.absolute_path_to_stored(thumb_path))
                    added += 1
            except Exception as exc:
                QMessageBox.warning(self, "メディア追加エラー", f"メディアを追加できませんでした。\n{src}\n\n{exc}")
        if added:
            self.refresh_images(sync_assets=False)
            self.update_current_prompt_row_in_visible_list_in_place()
            self.statusBar().showMessage(f"メディアを {added} 件追加しました")

    def ask_video_import_mode(self, src: Path, allow_apply_all: bool = False) -> tuple[Optional[str], bool]:
        dialog = QDialog(self)
        dialog.setWindowTitle("動画追加")
        layout = QVBoxLayout(dialog)

        label = QLabel(f"動画をどう追加しますか？\n{src.name}")
        label.setWordWrap(True)
        layout.addWidget(label)

        apply_checkbox: Optional[QCheckBox] = None
        if allow_apply_all:
            apply_checkbox = QCheckBox("今後すべてに適用")
            layout.addWidget(apply_checkbox)

        button_row = QHBoxLayout()
        copy_button = QPushButton("動画をコピーして登録")
        thumb_button = QPushButton("サムネ画像のみ作成")
        cancel_button = QPushButton("キャンセル")
        button_row.addWidget(copy_button)
        button_row.addWidget(thumb_button)
        button_row.addStretch(1)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

        selected_mode: dict[str, Optional[str]] = {"mode": None}

        def choose(mode: str) -> None:
            selected_mode["mode"] = mode
            dialog.accept()

        copy_button.clicked.connect(lambda: choose("copy"))
        thumb_button.clicked.connect(lambda: choose("thumb"))
        cancel_button.clicked.connect(dialog.reject)
        dialog.setDefaultButton(copy_button) if hasattr(dialog, "setDefaultButton") else None
        copy_button.setDefault(True)
        copy_button.setFocus()

        if dialog.exec() != QDialog.Accepted:
            return None, False
        apply_all = bool(apply_checkbox and apply_checkbox.isChecked())
        mode = selected_mode.get("mode")
        if mode in {"copy", "thumb"}:
            return mode, apply_all
        return None, False

    def create_material_thumbnail(self, src: Path, image_id: int, prompt_id: int, media_type: str = "") -> Optional[Path]:
        media_type = (media_type or media_type_for_path(src)).strip().lower()
        if media_type == "video" or src.suffix.lower() in SUPPORTED_VIDEO_EXTS:
            thumb_path = self.create_video_thumbnail(src, image_id, prompt_id)
            if thumb_path:
                return thumb_path
            return self.create_extension_thumbnail(src, image_id, prompt_id)
        if media_type == "image" or src.suffix.lower() in SUPPORTED_IMAGE_EXTS:
            return self.create_thumbnail(src, image_id, prompt_id)
        return self.create_extension_thumbnail(src, image_id, prompt_id)

    def create_thumbnail(self, src: Path, image_id: int, prompt_id: int) -> Optional[Path]:
        pix = QPixmap(str(src))
        if pix.isNull():
            return None
        thumb = pix.scaled(320, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        thumb_dir = self.prompt_thumbs_dir(prompt_id)
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f"thumb_{image_id:08d}.jpg"
        canvas = QPixmap(320, 240)
        canvas.fill(QColor("#ffffff"))
        painter = QPainter(canvas)
        try:
            x = max(0, (canvas.width() - thumb.width()) // 2)
            y = max(0, (canvas.height() - thumb.height()) // 2)
            painter.drawPixmap(x, y, thumb)
        finally:
            painter.end()
        if canvas.save(str(thumb_path), "JPEG", 90):
            return thumb_path
        return None

    def generate_video_snapshot(self, src: Path, prompt_asset_dir: Path) -> Path:
        dest = unique_path(prompt_asset_dir / f"{normalize_file_stem(src.name)}.jpg")
        self.write_video_frame_jpeg(src, dest, target_height=1080)
        return dest

    def create_video_thumbnail(self, src: Path, image_id: int, prompt_id: int) -> Optional[Path]:
        thumb_dir = self.prompt_thumbs_dir(prompt_id)
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f"thumb_{image_id:08d}.jpg"
        try:
            self.write_video_thumbnail_jpeg(src, thumb_path)
            return thumb_path
        except Exception:
            return None

    def windows_short_path(self, path: Path) -> Optional[str]:
        if os.name != "nt":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            get_short_path_name = ctypes.windll.kernel32.GetShortPathNameW
            get_short_path_name.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
            get_short_path_name.restype = wintypes.DWORD
            buffer = ctypes.create_unicode_buffer(32768)
            result = get_short_path_name(str(path), buffer, len(buffer))
            if 0 < result < len(buffer):
                return buffer.value
        except Exception:
            pass
        return None

    def capture_video_frame_from_cv2_path(self, cv2, path_text: str):
        cap = cv2.VideoCapture(path_text)
        if not cap.isOpened():
            cap.release()
            raise RuntimeError("動画を開けませんでした。")

        try:
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            candidate_indexes: list[int] = []
            if frame_count > 0:
                candidate_indexes.extend([max(0, int(frame_count * 0.15)), max(0, frame_count // 2), 0])
            else:
                candidate_indexes.extend([0])

            frame = None
            seen: set[int] = set()
            for index in candidate_indexes:
                if index in seen:
                    continue
                seen.add(index)
                if frame_count > 0:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, current = cap.read()
                if ok and current is not None:
                    frame = current
                    break

            if frame is None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                for _ in range(30):
                    ok, current = cap.read()
                    if ok and current is not None:
                        frame = current
                        break

            if frame is None:
                raise RuntimeError("動画からフレームを取得できませんでした。")
            return frame
        finally:
            cap.release()

    def capture_video_frame(self, src: Path):
        try:
            import cv2  # type: ignore
        except Exception as exc:
            raise RuntimeError("動画サムネ生成には opencv-python が必要です。") from exc

        errors: list[str] = []
        candidates: list[str] = []

        def add_candidate(value: Optional[str]) -> None:
            if value and value not in candidates:
                candidates.append(value)

        add_candidate(str(src))
        add_candidate(self.windows_short_path(src))
        for candidate in candidates:
            try:
                return self.capture_video_frame_from_cv2_path(cv2, candidate)
            except Exception as exc:
                errors.append(str(exc))

        # OpenCV can fail on some Windows paths, especially with non-ASCII names.
        # Retry from an ASCII file name in a temporary folder before giving up.
        suffix = src.suffix if src.suffix else ".mp4"
        try:
            with tempfile.TemporaryDirectory(prefix="apo_video_") as tmp_dir:
                temp_path = Path(tmp_dir) / f"source{suffix.lower()}"
                shutil.copy2(src, temp_path)
                temp_candidates: list[str] = []
                for value in (str(temp_path), self.windows_short_path(temp_path)):
                    if value and value not in temp_candidates:
                        temp_candidates.append(value)
                for candidate in temp_candidates:
                    try:
                        return self.capture_video_frame_from_cv2_path(cv2, candidate)
                    except Exception as exc:
                        errors.append(str(exc))
        except Exception as exc:
            errors.append(str(exc))

        detail = errors[-1] if errors else "原因不明"
        raise RuntimeError(f"動画からフレームを取得できませんでした。{detail}")

    def write_cv2_jpeg(self, cv2, dest: Path, frame, quality: int = 90) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        if not ok:
            raise RuntimeError("JPEGをエンコードできませんでした。")
        try:
            dest.write_bytes(encoded.tobytes())
        except Exception as exc:
            raise RuntimeError("JPEGを書き出せませんでした。") from exc

    def write_video_thumbnail_jpeg(self, src: Path, dest: Path) -> None:
        try:
            import cv2  # type: ignore
        except Exception as exc:
            raise RuntimeError("動画サムネ生成には opencv-python が必要です。") from exc

        frame = self.capture_video_frame(src)
        height, width = frame.shape[:2]
        if height <= 0 or width <= 0:
            raise RuntimeError("取得したフレームのサイズが不正です。")

        canvas_w, canvas_h = 320, 240
        scale = min(canvas_w / float(width), canvas_h / float(height))
        target_w = max(1, int(round(width * scale)))
        target_h = max(1, int(round(height * scale)))
        resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC)
        left = max(0, (canvas_w - target_w) // 2)
        right = max(0, canvas_w - target_w - left)
        top = max(0, (canvas_h - target_h) // 2)
        bottom = max(0, canvas_h - target_h - top)
        canvas = cv2.copyMakeBorder(resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        self.write_cv2_jpeg(cv2, dest, canvas, quality=90)

    def write_video_frame_jpeg(self, src: Path, dest: Path, target_height: int = 1080) -> None:
        try:
            import cv2  # type: ignore
        except Exception as exc:
            raise RuntimeError("動画サムネ生成には opencv-python が必要です。") from exc

        frame = self.capture_video_frame(src)
        height, width = frame.shape[:2]
        if height <= 0 or width <= 0:
            raise RuntimeError("取得したフレームのサイズが不正です。")

        target_width = max(1, int(round(width * (target_height / float(height)))))
        if height != target_height:
            frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA if target_height < height else cv2.INTER_CUBIC)

        self.write_cv2_jpeg(cv2, dest, frame, quality=90)

    def create_extension_thumbnail(self, src: Path, image_id: int, prompt_id: int) -> Optional[Path]:
        thumb_dir = self.prompt_thumbs_dir(prompt_id)
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f"thumb_{image_id:08d}.png"
        ext = extension_label(src)
        pix = QPixmap(320, 240)
        bg = QColor(color_for_media_type(media_type_for_path(src)))
        pix.fill(bg)
        painter = QPainter(pix)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QColor("#ffffff"))
            font = QFont()
            font.setBold(True)
            font.setPointSize(44 if len(ext) <= 4 else 34)
            painter.setFont(font)
            painter.drawText(QRect(0, 55, 320, 95), Qt.AlignCenter, ext)
            small_font = QFont()
            small_font.setPointSize(16)
            painter.setFont(small_font)
            painter.drawText(QRect(0, 150, 320, 45), Qt.AlignCenter, "FILE")
        finally:
            painter.end()
        if pix.save(str(thumb_path), "PNG"):
            return thumb_path
        return None

    def sync_current_prompt_assets(self) -> bool:
        if self.current_prompt_id is None:
            return False
        prompt_id = self.current_prompt_id
        image_dir, file_dir, _thumb_dir = self.ensure_prompt_asset_dirs(prompt_id)
        changed = False
        recycle_targets: list[Path] = []
        registered: set[str] = set()

        for row in self.db.list_images(prompt_id):
            image_id = int(row["id"])
            file_path = self.material_file_path_from_row(row)
            if not file_path.exists():
                thumb_path = self.material_thumb_path_from_row(row)
                if thumb_path and thumb_path.exists():
                    recycle_targets.append(thumb_path)
                self.db.delete_image(image_id)
                changed = True
                continue
            registered.add(material_path_key(file_path))
            thumb_path = self.material_thumb_path_from_row(row)
            if not thumb_path or not thumb_path.exists():
                media_type = str(row["media_type"] if "media_type" in row.keys() else media_type_for_path(file_path))
                try:
                    new_thumb = self.create_material_thumbnail(file_path, image_id, prompt_id, media_type)
                    if new_thumb:
                        self.db.update_image_thumbnail(image_id, self.absolute_path_to_stored(new_thumb))
                        changed = True
                except Exception:
                    pass

        if recycle_targets:
            move_paths_to_recycle_bin(recycle_targets)

        invalid_image_files: list[str] = []
        for child in sorted(image_dir.iterdir(), key=lambda p: p.name.lower()) if image_dir.exists() else []:
            if not child.is_file():
                continue
            if material_path_key(child) in registered:
                continue
            if child.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
                key = material_path_key(child)
                if key not in self.warned_invalid_image_folder_files:
                    self.warned_invalid_image_folder_files.add(key)
                    invalid_image_files.append(child.name)
                continue
            try:
                image_id = self.db.add_image(prompt_id, self.absolute_path_to_stored(child), "", media_type="image", original_name=child.name)
                thumb_path = self.create_material_thumbnail(child, image_id, prompt_id, "image")
                if thumb_path:
                    self.db.update_image_thumbnail(image_id, self.absolute_path_to_stored(thumb_path))
                registered.add(material_path_key(child))
                changed = True
            except Exception:
                pass

        for child in sorted(file_dir.iterdir(), key=lambda p: p.name.lower()) if file_dir.exists() else []:
            if not child.is_file():
                continue
            if material_path_key(child) in registered:
                continue
            try:
                if child.suffix.lower() in SUPPORTED_VIDEO_EXTS:
                    image_id = self.db.add_image(prompt_id, self.absolute_path_to_stored(child), "", media_type="video", original_name=child.name)
                    thumb_path = self.create_material_thumbnail(child, image_id, prompt_id, "video")
                    if not thumb_path:
                        thumb_path = self.create_material_thumbnail(child, image_id, prompt_id, media_type_for_path(child))
                else:
                    image_id = self.db.add_image(prompt_id, self.absolute_path_to_stored(child), "", media_type=media_type_for_path(child), original_name=child.name)
                    thumb_path = self.create_material_thumbnail(child, image_id, prompt_id, media_type_for_path(child))
                if thumb_path:
                    self.db.update_image_thumbnail(image_id, self.absolute_path_to_stored(thumb_path))
                registered.add(material_path_key(child))
                changed = True
            except Exception:
                pass

        if invalid_image_files:
            preview = "\n".join(f"- {name}" for name in invalid_image_files[:20])
            if len(invalid_image_files) > 20:
                preview += f"\n...他 {len(invalid_image_files) - 20} 件"
            QMessageBox.warning(
                self,
                "メディア同期警告",
                "imagesフォルダに画像以外のファイルがあります。\n"
                "このフォルダでは画像ファイルだけを登録します。\n\n" + preview,
            )

        return changed

    def cancel_material_list_loading(self) -> None:
        if self._material_load_timer.isActive():
            self._material_load_timer.stop()
        self._material_load_rows = []
        self._material_load_index = 0
        self._material_load_prompt_id = None

    def refresh_images(self, sync_assets: bool = True) -> None:
        self.cancel_material_list_loading()
        self.image_list.clear()
        if self.current_prompt_id is None:
            return
        if sync_assets:
            assets_changed = self.sync_current_prompt_assets()
            if assets_changed:
                self.update_current_prompt_row_in_visible_list_in_place()
        rows = self.db.list_images(self.current_prompt_id)
        self.start_material_list_loading(rows, self.current_prompt_id)

    def start_material_list_loading(self, rows: list[sqlite3.Row], prompt_id: int) -> None:
        self._material_load_rows = list(rows)
        self._material_load_index = 0
        self._material_load_prompt_id = prompt_id
        total = len(self._material_load_rows)
        if total == 0:
            self.statusBar().showMessage("メディア: 0 件")
            return
        self.statusBar().showMessage(f"メディア一覧を読み込み中... 0/{total}")
        self._material_load_timer.start()

    def process_material_load_chunk(self) -> None:
        prompt_id = self._material_load_prompt_id
        if prompt_id is None or prompt_id != self.current_prompt_id:
            self.cancel_material_list_loading()
            return

        total = len(self._material_load_rows)
        if self._material_load_index >= total:
            self._material_load_timer.stop()
            self.statusBar().showMessage(f"メディア: {total} 件")
            return

        end_index = min(total, self._material_load_index + self.material_load_chunk_size)
        self.image_list.setUpdatesEnabled(False)
        try:
            for row in self._material_load_rows[self._material_load_index:end_index]:
                self.add_material_list_item(row)
        finally:
            self.image_list.setUpdatesEnabled(True)
        self._material_load_index = end_index

        if self._material_load_index >= total:
            self._material_load_timer.stop()
            self.statusBar().showMessage(f"メディア: {total} 件")
        else:
            self.statusBar().showMessage(f"メディア一覧を読み込み中... {self._material_load_index}/{total}")

    def add_material_list_item(self, row: sqlite3.Row) -> None:
        image_id = int(row["id"])
        file_path_obj = self.material_file_path_from_row(row)
        thumb_path_obj = self.material_thumb_path_from_row(row)
        file_path = str(file_path_obj)
        thumb_path = str(thumb_path_obj or file_path_obj)
        cover = bool(row["is_cover"])
        label_id = int(row["label_id"] if "label_id" in row.keys() else 0)
        media_type = str(row["media_type"] if "media_type" in row.keys() else "image")
        file_name = Path(file_path).name
        stem = Path(file_path).stem
        prefix = media_label(media_type)
        label_text = f"{prefix} {stem}" if prefix else stem
        label = f"★ {label_text}" if cover else label_text
        display_label = elide_material_label(label)
        item = QListWidgetItem(display_label)
        item.setData(Qt.UserRole, image_id)
        item.setData(Qt.UserRole + 1, file_name)
        item.setData(Qt.UserRole + 2, label_id)
        item.setToolTip(file_name)
        self.apply_material_label_to_item(item, label_id)
        item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
        item.setSizeHint(QSize(170, 150))
        icon = icon_from_path(thumb_path, QSize(140, 105))
        if icon.isNull():
            icon = icon_from_path(file_path, QSize(140, 105))
        if not icon.isNull():
            item.setIcon(icon)
        self.image_list.addItem(item)

    def selected_image_id(self) -> Optional[int]:
        item = self.image_list.currentItem()
        if not item:
            return None
        return int(item.data(Qt.UserRole))

    def visible_material_image_ids(self) -> list[int]:
        ids: list[int] = []
        for index in range(self.image_list.count()):
            item = self.image_list.item(index)
            if item is not None:
                try:
                    ids.append(int(item.data(Qt.UserRole)))
                except Exception:
                    pass
        return ids

    def reorder_material_by_drop(self, image_id: int, insert_index: int) -> None:
        if self.current_prompt_id is None:
            return
        if self._material_load_timer.isActive():
            self.statusBar().showMessage("メディア一覧の読み込み中は並び替えできません")
            return
        ids = self.visible_material_image_ids()
        if image_id not in ids:
            return
        old_index = ids.index(image_id)
        insert_index = max(0, min(len(ids), int(insert_index)))
        if old_index < insert_index:
            insert_index -= 1
        if old_index == insert_index:
            return
        ids.pop(old_index)
        insert_index = max(0, min(len(ids), insert_index))
        ids.insert(insert_index, image_id)
        self.db.reorder_images(self.current_prompt_id, ids)
        self.image_list.setUpdatesEnabled(False)
        try:
            item = self.image_list.takeItem(old_index)
            if item is not None:
                self.image_list.insertItem(insert_index, item)
                self.image_list.setCurrentItem(item)
                self.image_list.scrollToItem(item)
        finally:
            self.image_list.setUpdatesEnabled(True)
        self.update_current_prompt_row_in_visible_list_in_place()
        self.statusBar().showMessage("メディアの並び順を変更しました")

    def select_material_in_list(self, image_id: int) -> None:
        for index in range(self.image_list.count()):
            item = self.image_list.item(index)
            if item is not None and int(item.data(Qt.UserRole)) == int(image_id):
                self.image_list.setCurrentItem(item)
                self.image_list.scrollToItem(item)
                return

    def selected_material_path(self) -> Optional[Path]:
        image_id = self.selected_image_id()
        if image_id is None:
            return None
        row = self.db.get_image(image_id)
        if not row:
            return None
        path = self.material_file_path_from_row(row)
        return path if path.exists() else None

    def material_path_for_image_id(self, image_id) -> Optional[Path]:
        try:
            image_id = int(image_id)
        except Exception:
            return None
        row = self.db.get_image(image_id)
        if not row:
            return None
        path = self.material_file_path_from_row(row)
        return path if path.exists() else None

    def selected_material_drag_pixmap(self) -> Optional[QPixmap]:
        image_id = self.selected_image_id()
        if image_id is None:
            return None
        row = self.db.get_image(image_id)
        if not row:
            return None
        thumb_path = self.material_thumb_path_from_row(row) or self.material_file_path_from_row(row)
        pix = pixmap_from_path(str(thumb_path), QSize(96, 72))
        return pix

    def on_material_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            self.drop_hint_label.setText("メディアファイルをここへドラッグ＆ドロップで追加できます。")
            return
        file_name = str(current.data(Qt.UserRole + 1) or current.text())
        image_id = current.data(Qt.UserRole)
        detail = material_file_detail_text(file_name, self.material_path_for_image_id(image_id))
        self.drop_hint_label.setText(detail)

    def reload_current_materials(self) -> None:
        if self.current_prompt_id is None:
            return
        self.refresh_images(sync_assets=True)
        self.update_current_prompt_row_in_visible_list_in_place()
        self.statusBar().showMessage("メディアリストを再読み込みしました")

    def rebuild_current_material_thumbnails(self) -> None:
        if self.current_prompt_id is None:
            return
        if self._thumb_rebuild_timer.isActive():
            self.statusBar().showMessage("サムネ再作成中です")
            return
        prompt_id = self.current_prompt_id
        self.sync_current_prompt_assets()
        rows = self.db.list_images(prompt_id)
        if not rows:
            self.statusBar().showMessage("再作成するサムネがありません")
            return

        self._thumb_rebuild_rows = list(rows)
        self._thumb_rebuild_index = 0
        self._thumb_rebuild_prompt_id = prompt_id
        self._thumb_rebuild_count = 0
        self._thumb_rebuild_errors = []
        self._thumb_rebuild_old_thumbs = []
        self.rebuild_thumbnails_button.setEnabled(False)
        self.statusBar().showMessage(f"サムネ再作成中... 0/{len(self._thumb_rebuild_rows)}")
        self._thumb_rebuild_timer.start()

    def cancel_thumbnail_rebuild(self) -> None:
        if self._thumb_rebuild_timer.isActive():
            self._thumb_rebuild_timer.stop()
        self._thumb_rebuild_rows = []
        self._thumb_rebuild_index = 0
        self._thumb_rebuild_prompt_id = None
        self._thumb_rebuild_count = 0
        self._thumb_rebuild_errors = []
        self._thumb_rebuild_old_thumbs = []
        if hasattr(self, "rebuild_thumbnails_button"):
            self.rebuild_thumbnails_button.setEnabled(True)

    def process_thumbnail_rebuild_chunk(self) -> None:
        prompt_id = self._thumb_rebuild_prompt_id
        if prompt_id is None or prompt_id != self.current_prompt_id:
            self.cancel_thumbnail_rebuild()
            self.statusBar().showMessage("サムネ再作成をキャンセルしました")
            return

        total = len(self._thumb_rebuild_rows)
        end_index = min(total, self._thumb_rebuild_index + self.thumbnail_rebuild_chunk_size)
        for row in self._thumb_rebuild_rows[self._thumb_rebuild_index:end_index]:
            image_id = int(row["id"])
            file_path = self.material_file_path_from_row(row)
            if not file_path.exists():
                continue
            old_thumb = self.material_thumb_path_from_row(row)
            media_type = str(row["media_type"] if "media_type" in row.keys() else media_type_for_path(file_path))
            try:
                new_thumb = self.create_material_thumbnail(file_path, image_id, prompt_id, media_type)
                if not new_thumb:
                    raise RuntimeError("サムネを作成できませんでした。")
                self.db.update_image_thumbnail(image_id, self.absolute_path_to_stored(new_thumb))
                if old_thumb and old_thumb.exists() and old_thumb.resolve() != new_thumb.resolve():
                    self._thumb_rebuild_old_thumbs.append(old_thumb)
                self._thumb_rebuild_count += 1
            except Exception as exc:
                self._thumb_rebuild_errors.append(f"{file_path.name}: {exc}")

        self._thumb_rebuild_index = end_index
        if self._thumb_rebuild_index < total:
            self.statusBar().showMessage(f"サムネ再作成中... {self._thumb_rebuild_index}/{total}")
            return

        self._thumb_rebuild_timer.stop()
        rebuilt = self._thumb_rebuild_count
        errors = list(self._thumb_rebuild_errors)
        old_thumbs = list(self._thumb_rebuild_old_thumbs)
        self.cancel_thumbnail_rebuild()

        if old_thumbs:
            move_paths_to_recycle_bin(old_thumbs)
        QPixmapCache.clear()
        self.refresh_images(sync_assets=False)
        self.update_prompt_rows_in_visible_list_in_place(prompt_id)
        if errors:
            QMessageBox.warning(
                self,
                "サムネ再作成警告",
                f"サムネを {rebuilt} 件再作成しました。\n一部のメディアで失敗しました。\n\n" + "\n".join(errors[:10]),
            )
        self.statusBar().showMessage(f"サムネを {rebuilt} 件再作成しました")

    def rename_selected_image(self) -> None:
        image_id = self.selected_image_id()
        if image_id is None:
            return
        row = self.db.get_image(image_id)
        if not row:
            return
        old_path = self.material_file_path_from_row(row)
        if not old_path.exists():
            QMessageBox.warning(self, "ファイル名変更エラー", "メディアファイルが見つかりません。")
            return
        current_stem = old_path.stem
        new_name, ok = QInputDialog.getText(
            self,
            "ファイル名変更",
            f"新しいファイル名を入力してください。\n拡張子 {old_path.suffix} は維持されます。",
            text=current_stem,
        )
        if not ok:
            return
        new_stem = normalize_file_stem(new_name)
        if not new_stem:
            return
        if new_stem == current_stem:
            return
        new_path = unique_path(old_path.with_name(f"{new_stem}{old_path.suffix}"))
        try:
            old_path.rename(new_path)
            self.db.update_image_file_path(image_id, self.absolute_path_to_stored(new_path))
            self.refresh_images()
            self.update_current_prompt_row_in_visible_list_in_place()
            self.statusBar().showMessage(f"メディアファイル名を変更しました: {new_path.name}")
        except Exception as exc:
            QMessageBox.warning(self, "ファイル名変更エラー", str(exc))

    def remove_selected_image(self) -> None:
        image_id = self.selected_image_id()
        if image_id is None:
            return
        row = self.db.get_image(image_id)
        if not row:
            return
        result = QMessageBox.question(
            self,
            "メディア削除確認",
            "選択メディアの登録を削除しますか？\nメディアファイルはWindowsのゴミ箱へ移動します。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return

        recycle_targets = [self.material_file_path_from_row(row)]
        thumb_path = self.material_thumb_path_from_row(row)
        if thumb_path and thumb_path.exists():
            recycle_targets.append(thumb_path)

        prompt_id = int(row["prompt_id"])
        prompt_asset_dir = self.prompt_asset_dir(prompt_id)
        self.db.delete_image(image_id)
        if not self.db.list_images(prompt_id):
            if prompt_asset_dir.exists():
                recycle_targets = [prompt_asset_dir]
        moved, errors = move_paths_to_recycle_bin(recycle_targets)
        remove_empty_dirs(prompt_asset_dir)
        self.refresh_images()
        self.update_prompt_rows_in_visible_list_in_place(prompt_id)
        if errors:
            QMessageBox.warning(self, "メディア削除警告", "登録は削除しましたが、一部ファイルをゴミ箱へ移動できませんでした。\n\n" + "\n".join(errors[:5]))
            self.statusBar().showMessage(f"メディア登録を削除しました。一部ファイル移動失敗: {len(errors)} 件")
        else:
            self.statusBar().showMessage(f"メディアを削除しました。ゴミ箱へ移動: {moved} 件")

    def set_selected_image_as_cover(self) -> None:
        if self.current_prompt_id is None:
            return
        image_id = self.selected_image_id()
        if image_id is None:
            return
        self.db.set_cover_image(self.current_prompt_id, image_id)
        self.refresh_images()
        self.update_current_prompt_row_in_visible_list_in_place()
        self.statusBar().showMessage("カバーを変更しました")

    def copy_selected_material_to_clipboard(self) -> None:
        image_id = self.selected_image_id()
        if image_id is None:
            return
        row = self.db.get_image(image_id)
        if not row:
            return
        path = self.material_file_path_from_row(row)
        if not path.exists():
            QMessageBox.warning(self, "コピーエラー", "メディアファイルが見つかりません。")
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path.resolve()))])
        QApplication.clipboard().setMimeData(mime)
        self.statusBar().showMessage(f"メディアをクリップボードにコピーしました: {path.name}")

    def show_selected_material_properties(self) -> None:
        image_id = self.selected_image_id()
        if image_id is None:
            return
        row = self.db.get_image(image_id)
        if not row:
            return
        path = self.material_file_path_from_row(row)
        if not path.exists():
            QMessageBox.warning(self, "プロパティ表示エラー", "メディアファイルが見つかりません。")
            return
        if not show_file_properties(path):
            QMessageBox.warning(self, "プロパティ表示エラー", "プロパティを表示できませんでした。")

    def show_material_context_menu(self, pos: QPoint) -> None:
        item = self.image_list.itemAt(pos)
        if item is None:
            return
        self.image_list.setCurrentItem(item)
        menu = QMenu(self)
        open_action = menu.addAction("開く")
        reveal_action = menu.addAction("エクスプローラーで表示")
        copy_action = menu.addAction("コピー")
        add_new_card_action = menu.addAction("新規カードを作って追加")
        rename_action = menu.addAction("ファイル名の変更")
        cover_action = menu.addAction("カバーにする")
        label_menu = menu.addMenu("ラベル")
        label_actions: dict[QAction, int] = {}
        for label_id in range(1, 10):
            action = label_menu.addAction(str(label_id))
            label_actions[action] = label_id
        clear_label_action = label_menu.addAction("解除")
        label_actions[clear_label_action] = 0
        menu.addSeparator()
        delete_action = menu.addAction("削除")
        menu.addSeparator()
        property_action = menu.addAction("プロパティ")
        selected = menu.exec(self.image_list.viewport().mapToGlobal(pos))
        if selected == open_action:
            self.open_selected_image()
        elif selected == reveal_action:
            self.reveal_selected_material_in_explorer()
        elif selected == copy_action:
            self.copy_selected_material_to_clipboard()
        elif selected == add_new_card_action:
            self.add_selected_material_to_new_prompt()
        elif selected == rename_action:
            self.rename_selected_image()
        elif selected == cover_action:
            self.set_selected_image_as_cover()
        elif selected in label_actions:
            self.set_selected_material_label(label_actions[selected])
        elif selected == delete_action:
            self.remove_selected_image()
        elif selected == property_action:
            self.show_selected_material_properties()

    def reveal_selected_material_in_explorer(self) -> None:
        image_id = self.selected_image_id()
        if image_id is None:
            return
        row = self.db.get_image(image_id)
        if not row:
            return
        path = self.material_file_path_from_row(row)
        if not path.exists():
            QMessageBox.warning(self, "表示エラー", "メディアファイルが見つかりません。")
            return
        reveal_path_in_file_manager(path)

    def card_image_navigation_entries(self, prompt_id: int) -> list[tuple[int, Path]]:
        entries: list[tuple[int, Path]] = []
        for row in self.db.list_images(int(prompt_id)):
            path = self.material_file_path_from_row(row)
            if path.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
                continue
            if not path.exists():
                continue
            entries.append((int(row["id"]), path))
        return entries

    def select_material_in_list_if_current_prompt(self, prompt_id: int, image_id: int) -> None:
        if self.current_prompt_id is None or int(self.current_prompt_id) != int(prompt_id):
            return
        for index in range(self.image_list.count()):
            item = self.image_list.item(index)
            if item is not None and int(item.data(Qt.UserRole)) == int(image_id):
                self.image_list.setCurrentItem(item)
                self.image_list.scrollToItem(item)
                return

    def open_selected_image(self) -> None:
        image_id = self.selected_image_id()
        if image_id is None:
            return
        row = self.db.get_image(image_id)
        if not row:
            return
        path = self.material_file_path_from_row(row)
        if path.suffix.lower() in SUPPORTED_IMAGE_EXTS:
            self.open_image_viewer(path, source_prompt_id=int(row["prompt_id"]), source_image_id=int(image_id))
        else:
            open_path(path)

    def force_activate_widget(self, widget: QWidget) -> None:
        widget.show()
        widget.raise_()
        widget.activateWindow()
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes

            hwnd = int(widget.winId())
            user32 = ctypes.windll.user32
            SW_SHOWNORMAL = 1
            HWND_TOPMOST = -1
            HWND_NOTOPMOST = -2
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_SHOWWINDOW = 0x0040
            user32.ShowWindow(hwnd, SW_SHOWNORMAL)
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def open_image_viewer(
        self,
        path: Path,
        external_image: bool = False,
        source_prompt_id: int | None = None,
        source_image_id: int | None = None,
    ) -> None:
        if not path.exists():
            QMessageBox.warning(self, "画像表示エラー", "画像ファイルが見つかりません。")
            return
        viewer = ImageViewerWindow(
            self,
            path,
            ImageViewerWindow.MODE_FRAMELESS,
            external_image=external_image,
            source_prompt_id=source_prompt_id,
            source_image_id=source_image_id,
        )
        self.image_viewers.append(viewer)
        viewer.show()
        self.force_activate_widget(viewer)
        QTimer.singleShot(0, lambda v=viewer: self.force_activate_widget(v) if v.isVisible() else None)
        QTimer.singleShot(250, lambda v=viewer: self.force_activate_widget(v) if v.isVisible() else None)

    def replace_image_viewer_mode(self, old_viewer: ImageViewerWindow, mode: str) -> None:
        geometry = QRect(old_viewer.geometry())
        zoom_percent = old_viewer.zoom_percent
        offset = QPoint(old_viewer.offset)
        image_path = old_viewer.image_path
        external_image = getattr(old_viewer, "external_image", False)
        source_prompt_id = getattr(old_viewer, "source_prompt_id", None)
        source_image_id = getattr(old_viewer, "source_image_id", None)
        if old_viewer in self.image_viewers:
            self.image_viewers.remove(old_viewer)
        old_viewer.close()

        viewer = ImageViewerWindow(
            self,
            image_path,
            mode,
            external_image=external_image,
            source_prompt_id=source_prompt_id,
            source_image_id=source_image_id,
        )
        viewer.zoom_percent = zoom_percent
        viewer.offset = offset
        if geometry.isValid():
            if mode == ImageViewerWindow.MODE_SCROLL:
                geometry = self.keep_rect_on_screen(geometry)
            viewer.setGeometry(geometry)
        if mode == ImageViewerWindow.MODE_FRAMELESS:
            viewer.resize_to_zoom()
        else:
            viewer.center_image_if_needed()
        self.image_viewers.append(viewer)
        viewer.showNormal()
        if mode == ImageViewerWindow.MODE_SCROLL:
            viewer.keep_window_frame_on_available_screen()
            QTimer.singleShot(0, lambda v=viewer: v.keep_window_frame_on_available_screen() if v.isVisible() else None)
            QTimer.singleShot(120, lambda v=viewer: v.keep_window_frame_on_available_screen() if v.isVisible() else None)
        self.force_activate_widget(viewer)
        QTimer.singleShot(0, viewer.showNormal)
        QTimer.singleShot(0, lambda v=viewer: self.force_activate_widget(v) if v.isVisible() else None)

    def unregister_image_viewer(self, viewer: ImageViewerWindow) -> None:
        if viewer in self.image_viewers:
            self.image_viewers.remove(viewer)

    def close_all_image_viewers(self) -> None:
        for viewer in list(self.image_viewers):
            viewer.close()

    def visible_image_viewers(self) -> list[ImageViewerWindow]:
        viewers = [viewer for viewer in list(self.image_viewers) if viewer.isVisible()]
        if len(viewers) != len(self.image_viewers):
            self.image_viewers = viewers
        return viewers

    def bring_visible_image_viewers_to_front(self) -> None:
        viewers = self.visible_image_viewers()
        if not viewers:
            self.statusBar().showMessage("表示中の画像ウィンドウはありません")
            return
        for viewer in viewers:
            viewer.showNormal()
            self.force_activate_widget(viewer)
        self.statusBar().showMessage(f"表示中の画像ウィンドウを前面に出しました: {len(viewers)}件")

    def tile_visible_image_viewers(self, anchor_rect: Optional[QRect] = None) -> None:
        viewers = self.visible_image_viewers()
        if not viewers:
            self.statusBar().showMessage("表示中の画像ウィンドウはありません")
            return

        if anchor_rect is None:
            if self.isVisible():
                anchor_rect = self.frameGeometry()
            else:
                active_window = QApplication.activeWindow()
                if isinstance(active_window, ImageViewerWindow):
                    anchor_rect = active_window.frameGeometry()
                else:
                    anchor_rect = viewers[0].frameGeometry()
        available = best_available_geometry_for_rect(anchor_rect)
        if len(viewers) == 1:
            viewer = viewers[0]
            viewer.fit_to_screen_center()
            self.force_activate_widget(viewer)
            self.statusBar().showMessage("表示中の画像ウィンドウを画面内へ配置しました")
            return

        layout = calculate_best_viewer_tile_layout(viewers, available)
        if not layout:
            self.statusBar().showMessage("画像ウィンドウの並べ替えに失敗しました")
            return

        for viewer, frame_rect in layout:
            frame_rect = keep_rect_on_available_screens(frame_rect, IMAGE_VIEWER_TILE_MIN_CLIENT_WIDTH, IMAGE_VIEWER_TILE_MIN_CLIENT_HEIGHT)
            if viewer.mode == ImageViewerWindow.MODE_SCROLL:
                viewer.setGeometry(viewer.client_geometry_for_frame_rect(frame_rect))
            else:
                viewer.setGeometry(frame_rect)
            if not viewer.pixmap.isNull():
                zoom_from_width = viewer.width() * 100.0 / max(1, viewer.pixmap.width())
                zoom_from_height = viewer.height() * 100.0 / max(1, viewer.pixmap.height())
                viewer.zoom_percent = max(10, min(2000, int(round(min(zoom_from_width, zoom_from_height)))))
            viewer.offset = QPoint(0, 0)
            viewer.center_image_if_needed()
            viewer.update_cursor(QPoint(viewer.width() // 2, viewer.height() // 2))
            viewer.update()

        for viewer, _frame_rect in layout:
            self.force_activate_widget(viewer)
        self.statusBar().showMessage(f"表示中の画像ウィンドウを並べて表示しました: {len(layout)}件")

    def save_image_viewer_position(self, pos: QPoint) -> None:
        self.db.set_setting("image_viewer_x", str(pos.x()))
        self.db.set_setting("image_viewer_y", str(pos.y()))

    def keep_rect_on_screen(self, rect: QRect) -> QRect:
        return keep_rect_on_available_screens(rect, 80, 60)

    def next_viewer_position(self, size: QSize) -> QPoint:
        screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 720)
        default_x = available.x() + max(0, (available.width() - size.width()) // 2)
        default_y = available.y() + max(0, (available.height() - size.height()) // 2)
        x = safe_int(self.db.get_setting("image_viewer_x", ""), default_x)
        y = safe_int(self.db.get_setting("image_viewer_y", ""), default_y)
        # Restore the saved position exactly for the first viewer.
        # Only additional simultaneous viewers are offset, so repeated open/close
        # does not drift farther from the saved position.
        offset = len(self.image_viewers) * 30
        rect = self.keep_rect_on_screen(QRect(x + offset, y + offset, size.width(), size.height()))
        return rect.topLeft()

    def open_backup_folder(self) -> None:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        open_path(self.backup_dir)

    def open_assets_folder(self) -> None:
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        open_path(self.assets_dir)

    def open_prompt_asset_folder(self, prompt_id: int) -> None:
        prompt_dir = self.prompt_asset_dir(prompt_id)
        prompt_dir.mkdir(parents=True, exist_ok=True)
        open_path(prompt_dir)

    def open_current_prompt_asset_folder(self) -> None:
        if self.current_prompt_id is None:
            self.open_assets_folder()
            return
        self.open_prompt_asset_folder(self.current_prompt_id)

    def open_readme_file(self) -> None:
        readme_path = get_base_dir() / "readme.txt"
        if not readme_path.exists():
            QMessageBox.warning(self, "readme.txt", f"readme.txt が見つかりません。\n{readme_path}")
            return
        open_path(readme_path)

    def show_supported_formats_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("対応ファイル形式")
        dialog.setModal(True)
        dialog.resize(620, 520)

        layout = QVBoxLayout(dialog)

        title = QLabel("対応ファイル形式")
        title.setStyleSheet("font-weight: bold; font-size: 15px;")
        layout.addWidget(title)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(supported_media_formats_text())
        layout.addWidget(text, 1)

        close_button = QPushButton("閉じる")
        close_button.clicked.connect(dialog.accept)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        dialog.exec()


    def key_operation_rows(self) -> list[tuple[str, str]]:
        return [
            ("保存", "Ctrl+S"),
            ("新規", "Ctrl+N"),
            ("検索", "Ctrl+F"),
            ("再読み込み", "F5"),
            ("クリップボードからメディアへ貼り付け", "Alt+V"),
            ("プロンプトをコピー", "Alt+C"),
            ("終了", "Ctrl+Q"),
            ("メインウィンドウ表示", "Shift+Alt+A ※有効時"),
            ("メディア コピー", "Ctrl+C"),
            ("メディア 貼り付け", "Ctrl+V / Alt+V"),
            ("メディア 開く", "Enter / Space"),
            ("メディア 削除", "Del"),
            ("メディア ファイル名変更", "F2"),
            ("メディア ラベル設定", "0-9"),
            ("カード 削除", "Del"),
            ("画像ビュアー 前面表示", "Alt+Z"),
            ("画像ビュアー 並べて表示", "Alt+A"),
            ("画像ビュアー 前の画像", "Left / Up / Alt+Left"),
            ("画像ビュアー 次の画像", "Right / Down / Alt+Right"),
            ("画像ビュアー 全て閉じる", "Alt+X"),
            ("画像ビュアー 閉じる", "Esc"),
        ]

    def show_key_operations_dialog(self) -> None:
        rows = self.key_operation_rows()

        dialog = QDialog(self)
        dialog.setWindowTitle("キー操作")
        dialog.setModal(True)
        dialog.resize(520, 440)
        layout = QVBoxLayout(dialog)

        title = QLabel("キー操作")
        title.setStyleSheet("font-weight: bold; font-size: 15px;")
        layout.addWidget(title)

        table_widget = QWidget()
        table_layout = QGridLayout(table_widget)
        table_layout.setContentsMargins(8, 8, 8, 8)
        table_layout.setHorizontalSpacing(24)
        table_layout.setVerticalSpacing(6)
        table_layout.setColumnStretch(0, 1)

        header_process = QLabel("処理")
        header_key = QLabel("対応キー")
        header_process.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header_key.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header_process.setStyleSheet("font-weight: bold; border-bottom: 1px solid #888; padding-bottom: 4px;")
        header_key.setStyleSheet("font-weight: bold; border-bottom: 1px solid #888; padding-bottom: 4px;")
        table_layout.addWidget(header_process, 0, 0)
        table_layout.addWidget(header_key, 0, 1)

        for row_index, (name, key) in enumerate(rows, start=1):
            process_label = QLabel(name)
            key_label = QLabel(key)
            process_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            key_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            table_layout.addWidget(process_label, row_index, 0)
            table_layout.addWidget(key_label, row_index, 1)

        table_layout.setRowStretch(len(rows) + 1, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(table_widget)
        layout.addWidget(scroll, 1)

        close_button = QPushButton("閉じる")
        close_button.setDefault(True)
        close_button.clicked.connect(dialog.accept)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        dialog.exec()

    def show_about_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("バージョン情報")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        top = QHBoxLayout()

        icon_label = QLabel()
        icon = load_window_icon()
        if not icon.isNull():
            icon_label.setPixmap(icon.pixmap(64, 64))
        icon_label.setFixedSize(72, 72)
        icon_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        top.addWidget(icon_label)

        info = QLabel(
            f"<b>{APP_NAME} {APP_VERSION}</b><br><br>"
            f"{APP_AUTHOR}<br>"
            f"<a href='{APP_CONTACT_X}'>{APP_CONTACT_X}</a><br>"
            f"<a href='{APP_REPOSITORY}'>{APP_REPOSITORY}</a><br><br>"
            "MIT License"
        )
        info.setOpenExternalLinks(True)
        info.setTextInteractionFlags(Qt.TextBrowserInteraction)
        top.addWidget(info, 1)
        layout.addLayout(top)

        ok_button = QPushButton("OK")
        ok_button.setDefault(True)
        ok_button.clicked.connect(dialog.accept)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(ok_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        dialog.exec()

    def dragEnterEvent(self, event):  # noqa: N802 - Qt naming
        if has_media_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802 - Qt naming
        if has_media_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):  # noqa: N802 - Qt naming
        paths = media_paths_from_mime(event.mimeData())
        if paths:
            self.add_images_from_paths(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def closeEvent(self, event):  # noqa: N802 - Qt naming
        if self.resident_mode and not self._force_quit:
            if not self.maybe_save_dirty():
                event.ignore()
                return
            self.save_ui_state()
            self.update_tray_visibility()
            self.hide()
            event.ignore()
            return

        if not self.maybe_save_dirty():
            self._force_quit = False
            event.ignore()
            return
        self.cancel_material_list_loading()
        self.cancel_thumbnail_rebuild()
        self.close_all_image_viewers()
        self.save_ui_state()
        self.unregister_global_hotkey()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        if self.ipc_server is not None:
            self.ipc_server.close()
        self.db.close()
        event.accept()
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app.quit)


def normalize_tag(tag: str) -> str:
    tag = tag.strip().strip("#＃")
    tag = re.sub(r"\s+", " ", tag)
    return tag


def normalize_category(category: str) -> str:
    category = category.strip()
    category = re.sub(r"\s+", " ", category)
    return category


def normalize_workspace_name(name: str) -> str:
    name = str(name or "").strip()
    name = re.sub(r"\s+", " ", name)
    return name


def normalize_meta_field(field: str) -> str:
    field = str(field or "").strip()
    if field in META_OPTION_LABELS:
        return field
    return META_OPTION_FIELDS_BY_LABEL.get(field, "")


def normalize_meta_value(value: str) -> str:
    value = str(value or "").strip()
    value = re.sub(r"\s+", " ", value)
    return value


def available_screen_geometries() -> list[QRect]:
    geometries: list[QRect] = []
    for screen in QGuiApplication.screens():
        if screen is not None:
            geom = screen.availableGeometry()
            if geom.isValid():
                geometries.append(QRect(geom))
    if not geometries:
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            if geom.isValid():
                geometries.append(QRect(geom))
    return geometries or [QRect(0, 0, 1280, 720)]


def best_available_geometry_for_rect(rect: QRect) -> QRect:
    screen = QGuiApplication.screenAt(rect.center())
    if screen is not None:
        geom = screen.availableGeometry()
        if geom.isValid():
            return QRect(geom)
    geometries = available_screen_geometries()
    best = geometries[0]
    best_area = -1
    for geom in geometries:
        inter = geom.intersected(rect)
        area = inter.width() * inter.height() if inter.isValid() else 0
        if area > best_area:
            best = geom
            best_area = area
    return QRect(best)


def keep_rect_on_available_screens(rect: QRect, min_width: int = 80, min_height: int = 60) -> QRect:
    rect = QRect(rect)
    available = best_available_geometry_for_rect(rect)
    intersects_any = any(geom.intersects(rect) for geom in available_screen_geometries())
    if not rect.isValid() or not intersects_any:
        width = min(max(min_width, rect.width() if rect.isValid() else min_width), available.width())
        height = min(max(min_height, rect.height() if rect.isValid() else min_height), available.height())
        fixed = QRect(0, 0, width, height)
        fixed.moveCenter(available.center())
        return fixed
    width = min(max(min_width, rect.width()), available.width())
    height = min(max(min_height, rect.height()), available.height())
    x = min(max(available.x(), rect.x()), available.right() - width + 1)
    y = min(max(available.y(), rect.y()), available.bottom() - height + 1)
    return QRect(x, y, width, height)


def meta_field_label(field: str) -> str:
    return META_OPTION_LABELS.get(normalize_meta_field(field), str(field or ""))


def parse_tags(text: str) -> list[str]:
    parts = re.split(r"[,，、\n]+", text)
    tags: list[str] = []
    seen: set[str] = set()
    for part in parts:
        tag = normalize_tag(part)
        if tag and tag not in seen:
            tags.append(tag)
            seen.add(tag)
    return tags


def strip_prompt_comment_lines(text: str) -> str:
    lines: list[str] = []
    for line in str(text or "").splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith("＃"):
            continue
        lines.append(line)
    return "\n".join(lines)


def tags_from_json(text: str) -> list[str]:
    try:
        data = json.loads(text or "[]")
    except Exception:
        data = []
    if not isinstance(data, list):
        return []
    return [normalize_tag(str(item)) for item in data if normalize_tag(str(item))]


def normalize_hex_color(color: str) -> str:
    color = (color or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        return color.lower()
    if re.fullmatch(r"#[0-9a-fA-F]{3}", color):
        return "#" + "".join(ch * 2 for ch in color[1:]).lower()
    return ""


def text_color_for_bg(color: str) -> str:
    color = normalize_hex_color(color) or "#777777"
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b)
    return "#111111" if luminance > 150 else "#ffffff"


def chip_style(color: str, checked: bool = False) -> str:
    color = normalize_hex_color(color) or "#777777"
    text_color = text_color_for_bg(color)
    # 選択中タグの枠線。白枠だと白背景に溶けるため、濃いスレート色で強調する。
    border = "#1f2937" if checked else color
    width = 3 if checked else 1
    return f"""
        QToolButton {{
            background-color: {color};
            color: {text_color};
            border: {width}px solid {border};
            border-radius: 10px;
            padding: 3px 8px;
            font-weight: bold;
        }}
    """


def effective_color_from_row(row: sqlite3.Row) -> str:
    return normalize_hex_color(str(row["color"] or "")) or normalize_hex_color(str(row["category_color"] or "")) or "#777777"


def colored_square_icon(color: str, size: QSize) -> QIcon:
    pix = QPixmap(size)
    pix.fill(QColor(normalize_hex_color(color) or "#777777"))
    return QIcon(pix)


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resolve_database_path(base_dir: Path) -> Path:
    db_path = base_dir / DB_FILENAME
    if db_path.exists():
        return db_path
    legacy_db_path = base_dir / LEGACY_DB_FILENAME
    if legacy_db_path.exists():
        shutil.copy2(legacy_db_path, db_path)
    return db_path


def get_resource_path(*parts: str) -> Path:
    """Return a resource path for both normal .py runs and PyInstaller onefile builds."""
    candidates: list[Path] = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(Path(sys._MEIPASS).joinpath(*parts))  # type: ignore[attr-defined]
    candidates.append(get_base_dir().joinpath(*parts))
    candidates.append(Path(__file__).resolve().parent.joinpath(*parts))

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else Path(*parts)


def load_window_icon() -> QIcon:
    window_icon_path = get_resource_path(*WINDOW_ICON_RELATIVE)
    if window_icon_path.exists():
        icon = QIcon(str(window_icon_path))
        if not icon.isNull():
            return icon

    exe_icon_path = get_resource_path(*EXE_ICON_RELATIVE)
    if exe_icon_path.exists():
        icon = QIcon(str(exe_icon_path))
        if not icon.isNull():
            return icon

    return QIcon()


def set_windows_app_user_model_id() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass



def format_file_size(size: int) -> str:
    value = float(max(0, int(size)))
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024


def material_path_key(path: Path) -> str:
    try:
        return os.path.normcase(str(Path(path).resolve()))
    except Exception:
        return os.path.normcase(str(Path(path)))


def is_relative_to_path(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def move_path_to_recycle_bin(path: Path) -> bool:
    """Move a file/folder to the Windows Recycle Bin. Returns True when something was moved."""
    path = Path(path)
    if not path.exists():
        return False

    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            FO_DELETE = 3
            FOF_SILENT = 0x0004
            FOF_NOCONFIRMATION = 0x0010
            FOF_ALLOWUNDO = 0x0040
            FOF_NOERRORUI = 0x0400

            class SHFILEOPSTRUCTW(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR),
                    ("fFlags", wintypes.USHORT),
                    ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", wintypes.LPVOID),
                    ("lpszProgressTitle", wintypes.LPCWSTR),
                ]

            # SHFileOperation requires a double-null-terminated path list.
            from_path = str(path.resolve()) + "\0\0"
            op = SHFILEOPSTRUCTW()
            op.hwnd = None
            op.wFunc = FO_DELETE
            op.pFrom = from_path
            op.pTo = None
            op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
            op.fAnyOperationsAborted = False
            op.hNameMappings = None
            op.lpszProgressTitle = None

            result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
            if result != 0 or op.fAnyOperationsAborted:
                raise OSError(f"SHFileOperationW failed: result={result}, aborted={bool(op.fAnyOperationsAborted)}")
            return True
        except Exception:
            raise

    # This tool is primarily for Windows EXE distribution. Non-Windows fallback keeps behavior simple.
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return True


def move_paths_to_recycle_bin(paths: Iterable[Path]) -> tuple[int, list[str]]:
    moved = 0
    errors: list[str] = []
    seen: set[str] = set()
    normalized: list[Path] = []
    for raw_path in paths:
        try:
            path = Path(raw_path)
            key = str(path.resolve())
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        if path.exists():
            normalized.append(path)

    # Move deeper files before parent folders unless the caller intentionally only provides a folder.
    normalized.sort(key=lambda p: len(p.parts), reverse=True)
    for path in normalized:
        if not path.exists():
            continue
        try:
            if move_path_to_recycle_bin(path):
                moved += 1
        except Exception as exc:
            errors.append(f"{path}: {exc}")
    return moved, errors


def remove_empty_dirs(root: Path) -> None:
    if not root.exists() or root.is_file():
        return
    for child in sorted([p for p in root.rglob("*") if p.is_dir()], key=lambda p: len(p.parts), reverse=True):
        try:
            child.rmdir()
        except OSError:
            pass
    try:
        root.rmdir()
    except OSError:
        pass

def safe_filename(name: str) -> str:
    name = name.strip().replace("\x00", "")
    name = re.sub(r"[<>:\"/\\|?*]+", "_", name)
    return name or "image.png"


def normalize_file_stem(name: str) -> str:
    name = name.strip().replace("\x00", "")
    name = Path(name).stem if Path(name).suffix else name
    name = safe_filename(name)
    name = Path(name).stem if Path(name).suffix else name
    return name.strip(" .")


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    idx = 2
    while True:
        candidate = parent / f"{stem}-{idx}{suffix}"
        if not candidate.exists():
            return candidate
        idx += 1


def extension_label(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    return (ext or "FILE").upper()[:8]


def media_type_for_path(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in SUPPORTED_IMAGE_EXTS:
        return "image"
    if ext in SUPPORTED_VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in ARCHIVE_EXTS:
        return "archive"
    if ext in DOCUMENT_EXTS:
        return "document"
    if ext in CODE_EXTS:
        return "code"
    if ext in TEXT_EXTS:
        return "text"
    return "file"


def media_label(media_type: str) -> str:
    return {
        "video": "*",
        "audio": "[AUDIO]",
        "archive": "[ZIP]",
        "document": "[DOC]",
        "code": "[CODE]",
        "text": "[TEXT]",
        "file": "",
    }.get(media_type, "")


def color_for_media_type(media_type: str) -> str:
    return {
        "video": "#334155",
        "audio": "#7c3aed",
        "archive": "#b45309",
        "document": "#2563eb",
        "code": "#047857",
        "text": "#4b5563",
        "file": "#374151",
    }.get(media_type, "#374151")


def icon_from_path(path: str, size: QSize) -> QIcon:
    pix = pixmap_from_path(path, size)
    if pix is None:
        return QIcon()
    return QIcon(pix)


def pixmap_from_path(path: str, size: QSize) -> QPixmap | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    pix = QPixmap(str(p))
    if pix.isNull():
        return None
    return pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def has_media_urls(mime_data) -> bool:
    return bool(media_paths_from_mime(mime_data))


def media_paths_from_mime(mime_data) -> list[Path]:
    paths: list[Path] = []
    if mime_data.hasFormat(INTERNAL_MATERIAL_DRAG_MIME):
        return paths
    if not mime_data.hasUrls():
        return paths
    for url in mime_data.urls():
        if not url.isLocalFile():
            continue
        path = Path(url.toLocalFile())
        if path.is_file():
            paths.append(path)
    return paths


def format_material_file_size(size_bytes: int) -> str:
    size_bytes = max(0, int(size_bytes))
    if size_bytes <= 0:
        return "0 KB"
    return f"{max(1, round(size_bytes / 1024)):,} KB"


def material_file_detail_text(file_name: str, path: Optional[Path]) -> str:
    file_name = str(file_name or "")
    if path is None or not path.exists():
        return file_name
    try:
        stat = path.stat()
    except Exception:
        return file_name
    size_bytes = int(stat.st_size)
    size_text = format_material_file_size(size_bytes)
    modified_text = datetime.fromtimestamp(stat.st_mtime).strftime("%Y/%m/%d %H:%M:%S")
    return f"{file_name} | {size_text} ({size_bytes:,} bytes) | {modified_text}"


def elide_material_label(text: str, max_chars: int = 22) -> str:
    text = str(text or "")
    if len(text) <= max_chars:
        return text
    keep = max(1, max_chars - 1)
    return text[:keep] + "…"


def normalize_image_viewer_resize_method(method: str) -> str:
    method = str(method or "").strip().lower()
    if method in IMAGE_VIEWER_RESIZE_METHOD_KEYS:
        return method
    return DEFAULT_IMAGE_VIEWER_RESIZE_METHOD


def image_viewer_resize_method_label(method: str) -> str:
    method = normalize_image_viewer_resize_method(method)
    for key, label in IMAGE_VIEWER_RESIZE_METHODS:
        if key == method:
            return label
    return method


def show_file_properties(path: Path) -> bool:
    path = path.resolve()
    if not path.exists():
        return False
    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            SEE_MASK_INVOKEIDLIST = 0x0000000C
            SW_SHOW = 5

            class SHELLEXECUTEINFOW(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("fMask", wintypes.ULONG),
                    ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR),
                    ("lpFile", wintypes.LPCWSTR),
                    ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR),
                    ("nShow", ctypes.c_int),
                    ("hInstApp", wintypes.HINSTANCE),
                    ("lpIDList", wintypes.LPVOID),
                    ("lpClass", wintypes.LPCWSTR),
                    ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD),
                    ("hIcon", wintypes.HANDLE),
                    ("hProcess", wintypes.HANDLE),
                ]

            info = SHELLEXECUTEINFOW()
            info.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
            info.fMask = SEE_MASK_INVOKEIDLIST
            info.hwnd = None
            info.lpVerb = "properties"
            info.lpFile = str(path)
            info.lpParameters = None
            info.lpDirectory = str(path.parent)
            info.nShow = SW_SHOW

            return bool(ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)))
        except Exception:
            return False
    open_path(path.parent)
    return True


def reveal_path_in_file_manager(path: Path) -> None:
    path = path.resolve()
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", f"/select,{str(path)}"])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            open_path(path.parent if path.is_file() else path)
    except Exception:
        open_path(path.parent if path.is_file() else path)


def open_path(path: Path) -> None:
    path = path.resolve()
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


def safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def powershell_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def windows_startup_shortcut_path() -> Optional[Path]:
    if not sys.platform.startswith("win"):
        return None
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / STARTUP_SHORTCUT_NAME


def startup_target_and_args() -> tuple[Path, str, Path, str]:
    base_dir = get_base_dir()
    if getattr(sys, "frozen", False):
        target = Path(sys.executable).resolve()
        arguments = STARTUP_ARG
    else:
        target = Path(sys.executable).resolve()
        script = Path(__file__).resolve()
        arguments = f'"{script}" {STARTUP_ARG}'
    icon_path = base_dir / EXE_ICON_RELATIVE[0] / EXE_ICON_RELATIVE[1] / EXE_ICON_RELATIVE[2]
    icon_location = str(icon_path if icon_path.exists() else target)
    return target, arguments, base_dir, icon_location


def is_windows_startup_registered() -> bool:
    path = windows_startup_shortcut_path()
    return bool(path and path.exists())


def register_windows_startup() -> bool:
    shortcut = windows_startup_shortcut_path()
    if shortcut is None:
        return False
    target, arguments, working_dir, icon_location = startup_target_and_args()
    try:
        shortcut.parent.mkdir(parents=True, exist_ok=True)
        command = "; ".join(
            [
                "$w = New-Object -ComObject WScript.Shell",
                f"$s = $w.CreateShortcut({powershell_quote(str(shortcut))})",
                f"$s.TargetPath = {powershell_quote(str(target))}",
                f"$s.Arguments = {powershell_quote(arguments)}",
                f"$s.WorkingDirectory = {powershell_quote(str(working_dir))}",
                f"$s.IconLocation = {powershell_quote(icon_location)}",
                "$s.WindowStyle = 7",
                "$s.Save()",
            ]
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0 and shortcut.exists()
    except Exception:
        return False


def unregister_windows_startup() -> bool:
    shortcut = windows_startup_shortcut_path()
    if shortcut is None:
        return False
    try:
        if shortcut.exists():
            shortcut.unlink()
        return not shortcut.exists()
    except Exception:
        return False


def collect_startup_image_paths(args: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for arg in args:
        raw = str(arg or "").strip()
        if not raw or raw.startswith("--"):
            continue
        path = Path(raw)
        if path.exists() and path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTS:
            paths.append(path.resolve())
    return paths


def send_ipc_message(message: dict) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(APP_IPC_SERVER_NAME)
    if not socket.waitForConnected(1200):
        return False
    payload = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
    socket.write(payload)
    socket.flush()
    ok = socket.waitForBytesWritten(1200)
    socket.disconnectFromServer()
    return bool(ok)


def main() -> int:
    set_windows_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app_icon = load_window_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    startup_image_paths = collect_startup_image_paths(sys.argv[1:])
    startup_launch = STARTUP_ARG in sys.argv[1:]

    lock = QLockFile(str(get_base_dir() / ".cardbox.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        if startup_image_paths:
            send_ipc_message({"command": "open_images", "paths": [str(p) for p in startup_image_paths]})
            return 0
        if startup_launch:
            return 0
        if send_ipc_message({"command": "show"}):
            return 0
        QMessageBox.information(None, APP_NAME, "CardBox は既に起動しています。")
        return 0

    window = MainWindow()
    if startup_launch:
        if window.resident_mode:
            window.update_tray_visibility()
            window.hide()
        else:
            window.showMinimized()
    elif startup_image_paths and window.resident_mode:
        window.update_tray_visibility()
        window.hide()
    else:
        window.show()
    if startup_image_paths:
        QTimer.singleShot(0, lambda paths=startup_image_paths: window.open_external_image_files(paths))
    QTimer.singleShot(0, window.apply_window_icon)
    QTimer.singleShot(1000, window.apply_window_icon)
    result = app.exec()
    lock.unlock()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
