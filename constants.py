# --- Theme Configuration ---
import customtkinter as ctk
import json
import os

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# --- Theme Definitions ---
DEFAULT_THEMES = {
    "Default": {
        "BG": "#121212",
        "CARD": "#1E1E1E",
        "PRIMARY": "#3A7EBF",
        "LIVE_GO": "#1a7f37",
        "FILE_GO": "#106ba3",
        "DANGER": "#c9302c",
        "WARN": "#e0a800",
        "TEXT_MAIN": "#FFFFFF",
        "TEXT_SUB": "#B0B0B0",
        "TEXT_ON_WARN": "#121212",
        "BTN_DISABLED_BG": "#3A3A3A",
        "BTN_DISABLED_TEXT": "#AAAAAA"
    },
    "Pink": {
        "BG": "#181014",
        "CARD": "#24181e",
        "PRIMARY": "#E05297",
        "LIVE_GO": "#1a7f37",
        "FILE_GO": "#C71585",
        "DANGER": "#c9302c",
        "WARN": "#e0a800",
        "TEXT_MAIN": "#FFFFFF",
        "TEXT_SUB": "#dcc5d0",
        "TEXT_ON_WARN": "#121212",
        "BTN_DISABLED_BG": "#3d2933",
        "BTN_DISABLED_TEXT": "#998a90"
    },
    "Purple": {
        "BG": "#100e17",
        "CARD": "#1a1624",
        "PRIMARY": "#8A2BE2",
        "LIVE_GO": "#1a7f37",
        "FILE_GO": "#6A0DAD",
        "DANGER": "#c9302c",
        "WARN": "#e0a800",
        "TEXT_MAIN": "#FFFFFF",
        "TEXT_SUB": "#b8b0c4",
        "TEXT_ON_WARN": "#121212",
        "BTN_DISABLED_BG": "#2d263b",
        "BTN_DISABLED_TEXT": "#8a8095"
    }
}

THEMES = DEFAULT_THEMES.copy()
THEME_FILE = "theme_config.json"
CURRENT_THEME_NAME = "Default"

if os.path.exists(THEME_FILE):
    try:
        with open(THEME_FILE, 'r') as f:
            data = json.load(f)
            CURRENT_THEME_NAME = data.get("theme", "Default")
            custom_themes = data.get("custom_themes", {})
            THEMES.update(custom_themes)
    except:
        pass

if CURRENT_THEME_NAME not in THEMES:
    CURRENT_THEME_NAME = "Default"

active_theme = THEMES[CURRENT_THEME_NAME]

# --- Accessible Color Palette (High Contrast) ---
COLOR_BG = active_theme["BG"]
COLOR_CARD = active_theme["CARD"]

# Action Colors (Darkened for better white-text contrast)
COLOR_PRIMARY = active_theme["PRIMARY"]
COLOR_LIVE_GO = active_theme["LIVE_GO"]
COLOR_FILE_GO = active_theme["FILE_GO"]
COLOR_DANGER = active_theme["DANGER"]
COLOR_WARN = active_theme["WARN"]

# Text Colors
COLOR_TEXT_MAIN = active_theme["TEXT_MAIN"]
COLOR_TEXT_SUB = active_theme["TEXT_SUB"]
COLOR_TEXT_ON_WARN = active_theme["TEXT_ON_WARN"]

# Disabled States
COLOR_BTN_DISABLED_BG = active_theme["BTN_DISABLED_BG"]
COLOR_BTN_DISABLED_TEXT = active_theme["BTN_DISABLED_TEXT"]

DEFAULT_FILENAME = "default_keymap.json"
