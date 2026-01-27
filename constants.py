# --- Theme Configuration ---
import customtkinter as ctk

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# --- Accessible Color Palette (High Contrast) ---
COLOR_BG = "#121212"
COLOR_CARD = "#1E1E1E"

# Action Colors (Darkened for better white-text contrast)
COLOR_PRIMARY = "#3A7EBF"   # Standard UI Blue
COLOR_LIVE_GO = "#1a7f37"   # Deep Green (Success)
COLOR_FILE_GO = "#106ba3"   # Deep Blue (Play File)
COLOR_DANGER = "#c9302c"    # Deep Red (Stop)
COLOR_WARN = "#e0a800"      # Amber/Gold (Pause)

# Text Colors
COLOR_TEXT_MAIN = "#FFFFFF"
COLOR_TEXT_SUB = "#B0B0B0"
COLOR_TEXT_ON_WARN = "#121212" # Black text for yellow buttons

# Disabled States
COLOR_BTN_DISABLED_BG = "#3A3A3A"
COLOR_BTN_DISABLED_TEXT = "#AAAAAA"

DEFAULT_FILENAME = "default_keymap.json"
