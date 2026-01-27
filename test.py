import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import mido
import threading
import time
import mido.backends.rtmidi
import pydirectinput
import copy
import json
import os
import ctypes
import webbrowser
import shutil
import sys
import random
try:
    import rtmidi
except ImportError:
    pass
try:
    import keyboard
except ImportError:
    keyboard = None

# --- Theme Configuration ---
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
user32 = ctypes.windll.user32

# --- Windows API Helpers ---
def get_open_windows():
    titles = []
    def foreach_window(hwnd, lParam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            if user32.IsWindowVisible(hwnd):
                titles.append(buff.value)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(WNDENUMPROC(foreach_window), 0)
    return sorted(list(set(titles)))

def get_active_window_title():
    hWnd = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(hWnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hWnd, buf, length + 1)
    return buf.value

def focus_window_by_title(title):
    if not title: return
    def foreach_window(hwnd, lParam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            if buff.value == title:
                if user32.IsIconic(hwnd):
                    user32.ShowWindow(hwnd, 9) # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
                return False
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(WNDENUMPROC(foreach_window), 0)

# --- Logic Helpers ---
def create_default_88_key_map():
    return {
        24: "right", 25: "up", 26: "down", 27: "left", 28: "shiftright",
        29: "/", 30: ".", 31: ",", 32: "l", 33: ";", 34: "'",
        35: "]", 36: "[", 37: "p", 38: "o", 39: "-", 40: "=",
        41: "0", 42: "9", 43: "ctrlleft", 44: "shiftleft", 45: "`",
        46: "2", 47: "5", 48: "q", 49: "s", 50: "x", 51: "d",
        52: "c", 53: "v", 54: "g", 55: "b", 56: "h", 57: "n",
        58: "j", 59: "m", 60: "w", 61: "3", 62: "e", 63: "4",
        64: "r", 65: "t", 66: "6", 67: "y", 68: "7", 69: "u",
        70: "8", 71: "i", 72: "k", 73: "altleft"
    }

def midi_to_note_name(note_number):
    if not 0 <= note_number <= 127: return "Invalid"
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    octave = (note_number // 12) - 1
    note = note_names[note_number % 12]
    return f"{note}{octave}"

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def load_profile_data(filename):
    # Try local file first, then bundled resource
    target_path = filename if os.path.exists(filename) else resource_path(filename)
    
    # Default name derived from filename
    display_name = os.path.splitext(os.path.basename(filename))[0].replace("_", " ").title()
    default_meta = {"name": display_name, "linked_window": "", "hotkeys": {"play_pause": "f9", "stop": "f10"}}
    
    try:
        with open(target_path, 'r') as f:
            data = json.load(f)
            # Check for new format with metadata
            if "metadata" in data and "mappings" in data:
                meta = data["metadata"]
                if meta.get("name") == "Unnamed Profile":
                    meta["name"] = display_name
                if "hotkeys" not in meta:
                    meta["hotkeys"] = {"play_pause": "f9", "stop": "f10"}
                return {int(k): v for k, v in data["mappings"].items()}, meta
            else:
                # Legacy format (just mappings)
                return {int(k): v for k, v in data.items()}, default_meta
    except (FileNotFoundError, json.JSONDecodeError):
        return create_default_88_key_map(), default_meta

def save_profile_data(filename, key_map, metadata):
    data = {"metadata": metadata, "mappings": key_map}
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4, sort_keys=True)
    except Exception as e:
        messagebox.showerror("Save Error", f"Could not save file:\n{e}")

def press_keys_for_midi(keys, action='down'):
    if not keys: return
    if not isinstance(keys, list): keys = [keys]
    if action == 'down':
        for key in keys: pydirectinput.keyDown(key)
    else:
        for key in keys: pydirectinput.keyUp(key)

def find_fallback_key(note, key_map):
    target_pitch_class = note % 12
    candidates = [k for k in key_map if k % 12 == target_pitch_class]
    if not candidates: return None
    closest_note = min(candidates, key=lambda x: abs(x - note))
    return key_map[closest_note]

# --- Main App ---
class MidiKeyTranslatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.extract_bundled_configs()

        # Set App ID so the taskbar icon displays correctly
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MidiKeybindPro.App.1.0")
        except:
            pass

        self.title("MIDI Keybind Pro")
        try:
            self.iconbitmap(resource_path("icon.ico"))
        except:
            pass
        self.geometry("500x820")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Application State ---
        self.live_running = False
        self.file_playing = False
        self.file_paused = False
        self.file_thread = None
        self.live_thread = None
        self.held_keys = set()
        self.key_lock = threading.Lock()
        self.debug_win = None
        self.debug_text = None
        self.debug_monitor_var = tk.BooleanVar(value=False)

        # Configuration
        self.pin_var = tk.BooleanVar(value=True)
        self.fallback_var = tk.BooleanVar(value=True)
        self.jitter_var = tk.BooleanVar(value=False)
        self.use_target_window = tk.BooleanVar(value=True)
        self.speed_modifier_var = tk.DoubleVar(value=1.0) # New: Speed modifier for file playback
        self.target_window_title = tk.StringVar(value="")

        # Thread-Safe Configuration Mirrors (Updated by UI, Read by Threads)
        self.safe_speed = 1.0
        self.safe_use_target = True
        self.safe_target_title = ""
        self.safe_jitter = False
        self.safe_fallback = True

        self.current_filename = DEFAULT_FILENAME
        self.key_map, self.current_metadata = load_profile_data(self.current_filename)
        
        self.profile_cache = []
        self.scan_profiles()

        # --- UI Construction ---
        self.main_container = ctk.CTkScrollableFrame(self, fg_color=COLOR_BG, corner_radius=0)
        self.main_container.grid(row=0, column=0, sticky="nsew")
        self.main_container.grid_columnconfigure(0, weight=1)

        # 1. Header
        self.build_header()

        # 2. Status Bar
        self.build_status_card()

        # 3. Settings & Target
        self.build_config_card()

        # 4. Live Input Card
        self.build_live_card()

        # 5. File Player Card
        self.build_file_card()

        # 6. Footer
        self.build_footer()

        # Initialization
        self.populate_midi_devices()
        self.populate_window_list()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.setup_hotkeys()
        self.toggle_pin()
        self.after(1000, self.check_initial_profile)
        self.after(200, self.check_disclaimer)

    def extract_bundled_configs(self):
        """Extracts bundled JSON files to the local directory so they are visible in dialogs."""
        # Check if running as PyInstaller bundle
        if hasattr(sys, '_MEIPASS'):
            try:
                for filename in os.listdir(sys._MEIPASS):
                    if filename.lower().endswith('.json'):
                        dest = os.path.join(os.getcwd(), filename)
                        if not os.path.exists(dest):
                            shutil.copy2(os.path.join(sys._MEIPASS, filename), dest)
            except Exception as e:
                print(f"Config extraction failed: {e}")

    def scan_profiles(self):
        """Scans directory for JSON profiles and caches metadata."""
        self.profile_cache = []
        try:
            for f in os.listdir("."):
                if f.lower().endswith(".json"):
                    _, meta = load_profile_data(f)
                    self.profile_cache.append({"filename": f, "metadata": meta})
        except Exception as e:
            print(f"Scan error: {e}")

    def check_initial_profile(self):
        """Checks running programs on startup and loads profile if linked window exists."""
        open_windows = get_open_windows()
        open_windows_lower = [w.lower() for w in open_windows]

        for prof in self.profile_cache:
            link = prof["metadata"].get("linked_window", "")
            if link:
                link_lower = link.lower()
                if any(link_lower in w for w in open_windows_lower) and prof["filename"] != self.current_filename:
                    self.load_profile(prof["filename"])
                    break

    def check_disclaimer(self):
        marker_file = "eula_accepted"
        if os.path.exists(marker_file):
            return

        # Create custom dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Welcome!")
        dialog.geometry("420x340")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.transient(self)
        dialog.grab_set()

        # Center logic
        try:
            x = self.winfo_x() + (self.winfo_width() // 2) - 210
            y = self.winfo_y() + (self.winfo_height() // 2) - 170
            dialog.geometry(f"+{x}+{y}")
        except:
            pass

        # Content
        title_font = ctk.CTkFont(size=18, weight="bold")
        body_font = ctk.CTkFont(size=13)

        ctk.CTkLabel(dialog, text="Welcome to MIDI Keybind Pro! 🎹", font=title_font, text_color=COLOR_PRIMARY).pack(pady=(25, 15))
        
        msg = ("We hope you enjoy turning your instrument into a controller!\n\n"
               "Just a friendly heads-up: This tool works by simulating keyboard presses. "
               "While we've built it to be safe, some online games have strict rules about automation.\n\n"
               "Please use this tool responsibly. We want you to have fun, but we can't take "
               "responsibility for any account actions that might occur in third-party games.\n\n"
               "Play safe and have fun!")
        
        ctk.CTkLabel(dialog, text=msg, font=body_font, wraplength=360, justify="left", text_color="#DDDDDD").pack(pady=10, padx=20)

        def on_accept():
            try:
                with open(marker_file, "w") as f:
                    f.write("accepted")
            except Exception:
                pass
            dialog.destroy()

        ctk.CTkButton(dialog, text="I Understand, Let's Play!", command=on_accept, fg_color=COLOR_LIVE_GO, width=200).pack(pady=20)

    def restart_as_admin(self):
        try:
            if getattr(sys, 'frozen', False):
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv[1:]), None, 1)
            else:
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
            self.destroy()
        except Exception as e:
            print(f"Admin restart failed: {e}")

    def build_header(self):
        header = ctk.CTkFrame(self.main_container, fg_color="transparent")
        header.grid(row=0, column=0, pady=(20, 10), sticky="ew")
        ctk.CTkLabel(header, text="MIDI Keybind Pro", font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold")).pack()
        ctk.CTkLabel(header, text="Universal MIDI Input Translator", font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_SUB).pack()
        ctk.CTkLabel(header, text="Turn your Piano into a Keyboard", font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_SUB).pack()

        if not ctypes.windll.shell32.IsUserAnAdmin():
            admin_frame = ctk.CTkFrame(header, fg_color="transparent")
            admin_frame.pack(pady=(5, 0))
            ctk.CTkButton(admin_frame, text="🛡️ Run as Admin", width=120, height=24, fg_color="#333", hover_color="#444", command=self.restart_as_admin).pack(side="left", padx=5)
            self.create_info_btn(admin_frame, "Administrator Privileges", "Required for some games (e.g., Genshin Impact, Valorant) that block simulated input from non-admin programs.").pack(side="left")

    def create_info_btn(self, parent, title, message):
        return ctk.CTkButton(parent, text="?", width=20, height=20, corner_radius=10,
                            fg_color="transparent", border_width=1, border_color=COLOR_TEXT_SUB,
                            text_color=COLOR_TEXT_SUB, hover_color="#333",
                            command=lambda: self.show_custom_info(title, message))

    def show_custom_info(self, title, message):
        top = ctk.CTkToplevel(self)
        top.title("")
        top.geometry("320x180")
        top.resizable(False, False)
        top.transient(self)
        top.attributes("-topmost", True)
        top.grab_set()
        
        # Center on parent
        x = self.winfo_x() + (self.winfo_width() // 2) - 160
        y = self.winfo_y() + (self.winfo_height() // 2) - 90
        top.geometry(f"+{x}+{y}")
        
        ctk.CTkLabel(top, text=title, font=ctk.CTkFont(size=15, weight="bold"), text_color=COLOR_PRIMARY).pack(pady=(20, 10))
        ctk.CTkLabel(top, text=message, font=ctk.CTkFont(size=12), wraplength=280, text_color="#DDDDDD").pack(pady=5)
        ctk.CTkButton(top, text="Got it", width=80, height=25, command=top.destroy).pack(pady=20)

    def build_status_card(self):
        self.status_card = ctk.CTkFrame(self.main_container, fg_color=COLOR_CARD, corner_radius=15, border_width=1, border_color="#333")
        self.status_card.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.status_card.grid_columnconfigure(1, weight=1)

        self.status_indicator = ctk.CTkButton(self.status_card, text="", width=15, height=15, corner_radius=10, fg_color=COLOR_BTN_DISABLED_BG, hover=False, state="disabled")
        self.status_indicator.grid(row=0, column=0, padx=(20, 15), pady=25)

        text_frame = ctk.CTkFrame(self.status_card, fg_color="transparent")
        text_frame.grid(row=0, column=1, sticky="w", pady=15)

        self.status_main = ctk.CTkLabel(text_frame, text="Standby", font=ctk.CTkFont(size=18, weight="bold"), anchor="w")
        self.status_main.pack(anchor="w")

        self.status_sub = ctk.CTkLabel(text_frame, text="Waiting for input...", font=ctk.CTkFont(size=13), text_color=COLOR_TEXT_SUB, anchor="w")
        self.status_sub.pack(anchor="w")

    def build_config_card(self):
        card = ctk.CTkFrame(self.main_container, fg_color=COLOR_CARD, corner_radius=15)
        card.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card, text="CONFIGURATION", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_SUB).grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")

        prof_frame = ctk.CTkFrame(card, fg_color="transparent")
        prof_frame.grid(row=1, column=0, padx=20, pady=5, sticky="ew")

        self.profile_lbl = ctk.CTkLabel(prof_frame, text=self.current_metadata.get("name", "Unknown"), font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"))
        self.profile_lbl.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(prof_frame, text="Profiles", width=80, height=25, fg_color="#333", hover_color="#444", command=self.open_profile_manager).pack(side="right", padx=2)
        ctk.CTkButton(prof_frame, text="Save Map", width=60, height=25, fg_color="#333", hover_color="#444", command=self.save_current_map).pack(side="right", padx=2)
        ctk.CTkButton(prof_frame, text="Hotkeys", width=60, height=25, fg_color="#333", hover_color="#444", command=self.open_hotkey_editor).pack(side="right", padx=2)
        ctk.CTkButton(prof_frame, text="Edit Map", width=80, height=25, fg_color=COLOR_PRIMARY, command=self.open_editor).pack(side="right", padx=10)

        fb_frame = ctk.CTkFrame(card, fg_color="transparent")
        fb_frame.grid(row=2, column=0, padx=20, pady=10, sticky="w")
        self.fallback_switch = ctk.CTkSwitch(fb_frame, text="Smart Octave Fallback", variable=self.fallback_var, button_color=COLOR_PRIMARY, progress_color=COLOR_PRIMARY)
        self.fallback_switch.pack(side="left")
        self.create_info_btn(fb_frame, "Smart Octave Fallback", "If a note is not mapped, this attempts to find the same note in a different octave that IS mapped.").pack(side="left", padx=10)
        
        jitter_frame = ctk.CTkFrame(card, fg_color="transparent")
        jitter_frame.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="w")
        self.jitter_switch = ctk.CTkSwitch(jitter_frame, text="Gaussian Jitter", variable=self.jitter_var, button_color=COLOR_PRIMARY, progress_color=COLOR_PRIMARY)
        self.jitter_switch.pack(side="left")
        self.create_info_btn(jitter_frame, "Gaussian Jitter", "Adds a small random delay to key presses to simulate human imperfection.").pack(side="left", padx=10)

        target_frame = ctk.CTkFrame(card, fg_color="transparent")
        target_frame.grid(row=4, column=0, padx=20, pady=(5, 15), sticky="ew")

        self.target_switch = ctk.CTkSwitch(target_frame, text="Focus Protection", variable=self.use_target_window, button_color=COLOR_PRIMARY, progress_color=COLOR_PRIMARY)
        self.target_switch.pack(side="left")
        self.create_info_btn(target_frame, "Focus Protection", "When enabled, keys will ONLY be pressed if the selected window is currently active (in the foreground).").pack(side="left", padx=5)

        ctk.CTkButton(target_frame, text="↻", width=30, height=25, command=self.populate_window_list, fg_color="#333", hover_color="#444").pack(side="right")
        self.window_dropdown = ctk.CTkOptionMenu(target_frame, variable=self.target_window_title, dynamic_resizing=False, width=150, fg_color="#333", button_color="#444")
        self.window_dropdown.pack(side="right", padx=5, fill="x", expand=True)
        self.window_dropdown.set("Select Window")

    def build_live_card(self):
        card = ctk.CTkFrame(self.main_container, fg_color=COLOR_CARD, corner_radius=15)
        card.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 5))
        ctk.CTkLabel(head, text="LIVE INPUT", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_SUB).pack(side="left")
        ctk.CTkLabel(head, text="LIVE MIDI", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_SUB).pack(side="left")

        self.live_dot = ctk.CTkLabel(head, text="●", font=ctk.CTkFont(size=16), text_color=COLOR_BTN_DISABLED_TEXT)
        self.live_dot.pack(side="right")

        self.note_display = ctk.CTkLabel(head, text="--", font=ctk.CTkFont(family="Consolas", size=14, weight="bold"), text_color=COLOR_TEXT_SUB, width=50)
        self.note_display.pack(side="right", padx=(0, 10))

        # Device Dropdown
        device_frame = ctk.CTkFrame(card, fg_color="transparent")
        device_frame.grid(row=1, column=0, padx=20, pady=(5, 10), sticky="ew")
        device_frame.grid_columnconfigure(0, weight=1)
        
        self.device_var = ctk.StringVar(value="Select Device...")
        self.device_menu = ctk.CTkOptionMenu(device_frame, variable=self.device_var, command=self.on_device_select, fg_color="#333", button_color="#444", button_hover_color="#555", text_color="white")
        self.device_menu.grid(row=0, column=0, sticky="ew")

        ctk.CTkButton(device_frame, text="↻", width=30, height=25, command=self.populate_midi_devices, fg_color="#333", hover_color="#444").grid(row=0, column=1, padx=(5,0))


        # Controls Row
        live_ctrl_frame = ctk.CTkFrame(card, fg_color="transparent")
        live_ctrl_frame.grid(row=2, column=0, padx=20, pady=(0, 15), sticky="ew")
        live_ctrl_frame.grid_columnconfigure((0, 1), weight=1)

        self.start_live_btn = ctk.CTkButton(
            live_ctrl_frame,
            text="▶ Start Live",
            command=self.manual_start_live,
            fg_color=COLOR_LIVE_GO,
            hover_color="#1f7f33",
            text_color="white",
            text_color_disabled=COLOR_BTN_DISABLED_TEXT,
            state="disabled"
        )
        self.start_live_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.stop_live_btn = ctk.CTkButton(
            live_ctrl_frame,
            text="⏹ Stop Live",
            command=self.stop_live,
            fg_color=COLOR_DANGER,
            hover_color="#a82522",
            text_color="white",
            text_color_disabled=COLOR_BTN_DISABLED_TEXT,
            state="disabled"
        )
        self.stop_live_btn.grid(row=0, column=1, padx=(5, 0), sticky="ew")

    def build_file_card(self):
        card = ctk.CTkFrame(self.main_container, fg_color=COLOR_CARD, corner_radius=15)
        card.grid(row=4, column=0, padx=20, pady=10, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 5))
        ctk.CTkLabel(head, text="MIDI FILE PLAYER", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_SUB).pack(side="left")
        ctk.CTkLabel(head, text="AUTO PLAYER", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_SUB).pack(side="left")
        self.file_note_display = ctk.CTkLabel(head, text="--", font=ctk.CTkFont(family="Consolas", size=14, weight="bold"), text_color=COLOR_TEXT_SUB, width=50)
        self.file_note_display.pack(side="right")

        file_frame = ctk.CTkFrame(card, fg_color="transparent")
        file_frame.grid(row=1, column=0, padx=20, pady=5, sticky="ew")

        self.file_lbl = ctk.CTkLabel(file_frame, text="No file selected", text_color="gray")
        self.file_lbl.pack(side="left", fill="x", expand=True, anchor="w")
        ctk.CTkButton(file_frame, text="Select File", width=80, command=self.select_file, fg_color="#333", hover_color="#444").pack(side="right")

        # New: Playback Speed Control
        speed_frame = ctk.CTkFrame(card, fg_color="transparent")
        speed_frame.grid(row=2, column=0, padx=20, pady=(5, 10), sticky="ew")
        speed_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(speed_frame, text="Playback Speed:", font=ctk.CTkFont(size=12)).grid(row=0, column=0, sticky="w")
        
        self.speed_slider = ctk.CTkSlider(
            speed_frame,
            from_=0.25, to=4.0, # Range from 0.25x to 4.0x speed
            number_of_steps=15, # Steps for 0.25, 0.5, 0.75, 1.0, ..., 4.0
            variable=self.speed_modifier_var,
            command=self.on_speed_change,
            button_color=COLOR_PRIMARY,
            progress_color=COLOR_PRIMARY
        )
        self.speed_slider.grid(row=0, column=1, padx=(10, 0), sticky="ew")

        self.speed_label = ctk.CTkLabel(speed_frame, text="1.00x", font=ctk.CTkFont(size=12, weight="bold"))
        self.speed_label.grid(row=0, column=2, padx=(10, 0), sticky="e")

        ctrl_frame = ctk.CTkFrame(card, fg_color="transparent")
        ctrl_frame.grid(row=3, column=0, padx=20, pady=(10, 15), sticky="ew") # Moved to row 3
        ctrl_frame.grid_columnconfigure((0,1,2), weight=1)
        
        self.btn_play = ctk.CTkButton(
            ctrl_frame,
            text="▶ Play",
            command=self.start_file,
            fg_color=COLOR_BTN_DISABLED_BG,
            hover_color="#185ABD",
            text_color="white",
            text_color_disabled=COLOR_BTN_DISABLED_TEXT,
            state="disabled"
        )
        self.btn_play.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.btn_pause = ctk.CTkButton(
            ctrl_frame,
            text="⏸ Pause",
            command=self.pause_file,
            fg_color=COLOR_BTN_DISABLED_BG,
            hover_color="#B27B16",
            text_color=COLOR_TEXT_ON_WARN, # Black text on Yellow
            text_color_disabled=COLOR_BTN_DISABLED_TEXT,
            state="disabled"
        )
        self.btn_pause.grid(row=0, column=1, padx=5, sticky="ew")

        self.btn_stop = ctk.CTkButton(
            ctrl_frame,
            text="⏹ Stop",
            command=self.stop_file,
            fg_color=COLOR_BTN_DISABLED_BG,
            hover_color="#a82522",
            text_color="white",
            text_color_disabled=COLOR_BTN_DISABLED_TEXT,
            state="disabled"
        )
        self.btn_stop.grid(row=0, column=2, padx=(5, 0), sticky="ew")

    def build_footer(self):
        footer = ctk.CTkFrame(self, height=40, fg_color=COLOR_BG)
        footer.grid(row=1, column=0, sticky="ew")
        self.pin_check = ctk.CTkCheckBox(footer, text="Always on Top", variable=self.pin_var, command=self.toggle_pin, font=ctk.CTkFont(size=12), checkmark_color=COLOR_BG, fg_color=COLOR_TEXT_SUB)
        self.pin_check.pack(side="left", padx=20, pady=10)
        ctk.CTkButton(footer, text="☕ Donate", width=80, height=24, fg_color="#333", hover_color="#FF5E5B", font=ctk.CTkFont(size=11), command=lambda: webbrowser.open("https://ko-fi.com/unbutteredbagel")).pack(side="right", padx=20)

    def on_speed_change(self, value):
        self.speed_label.configure(text=f"{value:.2f}x")
        self.sync_config()

    def on_window_select(self, value):
        self.sync_config()

    def sync_config(self, _=None):
        self.safe_speed = self.speed_modifier_var.get()
        self.safe_use_target = self.use_target_window.get()
        self.safe_target_title = self.target_window_title.get()
        self.safe_jitter = self.jitter_var.get()
        self.safe_fallback = self.fallback_var.get()

    # --- Debugging ---
    def open_debug_console(self):
        if self.debug_win is None or not self.debug_win.winfo_exists():
            self.debug_win = ctk.CTkToplevel(self)
            self.debug_win.title("Debug Console")
            self.debug_win.geometry("400x300")
            self.debug_win.attributes("-topmost", True)
            self.debug_text = ctk.CTkTextbox(self.debug_win, font=ctk.CTkFont(family="Consolas", size=12))
            self.debug_text.pack(fill="both", expand=True, padx=5, pady=5)
            self.debug_text.configure(state="disabled")
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            self.log(f"Debug Console Opened. Admin Mode: {is_admin}")
            
            # Add Monitor Checkbox
            ctk.CTkCheckBox(self.debug_win, text="Monitor Key Input", variable=self.debug_monitor_var, font=ctk.CTkFont(size=12)).pack(pady=5)
        self.debug_win.lift()

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] {message}"
        print(full_msg)
        # Schedule UI update on main thread to prevent crashes
        self.after(0, lambda: self._update_log_ui(full_msg))

    def _update_log_ui(self, full_msg):
        if self.debug_win is not None and self.debug_win.winfo_exists() and self.debug_text:
            self.debug_text.configure(state="normal")
            self.debug_text.insert("end", full_msg + "\n")
            self.debug_text.see("end")
            self.debug_text.configure(state="disabled")

    # --- Logic ---

    def populate_window_list(self):
        wins = get_open_windows()
        if wins:
            self.window_dropdown.configure(values=wins)
        else:
            self.window_dropdown.configure(values=["No Windows Found"])

    def populate_midi_devices(self):
        try:
            devices = mido.get_input_names()
            if devices:
                self.device_menu.configure(values=devices)
                self.device_var.set("Select Device...")
            else:
                self.device_menu.configure(values=["No Device Found"])
                self.device_var.set("No Device Found")
        except Exception as e:
            self.device_menu.configure(values=[f"Error: {e}"])
            self.device_var.set("Error")

    def on_device_select(self, choice):
        if choice in ["No Device Found", "Error", "Select Device..."]: return
        if self.live_running:
            self.stop_live()
        self.start_live(choice)

    def update_status_ui(self, main_text, sub_text, color):
        self.status_indicator.configure(fg_color=color)
        self.status_main.configure(text=main_text)
        self.status_sub.configure(text=sub_text)

    # --- Live Input Control ---
    def manual_start_live(self):
        device = self.device_var.get()
        if device not in ["No Device Found", "Error", "Select Device..."]:
            self.start_live(device)

    def start_live(self, device_name):
        self.live_running = True
        self.live_thread = threading.Thread(target=self.live_loop, args=(device_name,), daemon=True)
        self.live_thread.start()

        self.start_live_btn.configure(state="disabled")
        self.stop_live_btn.configure(state="normal")
        self.device_menu.configure(state="disabled")
        self.live_dot.configure(text_color=COLOR_LIVE_GO)
        self.update_status_ui("Live Active", f"Input: {device_name}", COLOR_LIVE_GO)

    def stop_live(self):
        self.live_running = False
        self.release_all_held_keys()
        self.stop_live_btn.configure(state="disabled")
        self.start_live_btn.configure(state="normal")
        self.device_menu.configure(state="normal")
        self.live_dot.configure(text_color=COLOR_BTN_DISABLED_TEXT)

        if self.file_playing:
            self.update_status_ui("Playing File", "Live input stopped", COLOR_FILE_GO)
        else:
            self.update_status_ui("Ready", "Live input stopped", COLOR_BTN_DISABLED_BG)

    def live_loop(self, device):
        try:
            with mido.open_input(device) as port:
                while self.live_running:
                    for msg in port.iter_pending():
                        if not self.check_can_press(): continue
                        self.process_msg(msg, source='live')
                    time.sleep(0.001)
        except Exception as e:
            print(f"Live Error: {e}")
            self.live_running = False
            self.after(0, self.stop_live)

    # --- File Player Control ---
    def select_file(self):
        f = filedialog.askopenfilename(filetypes=[("MIDI", "*.mid *.midi")])
        if f:
            self.current_midi_file = f
            self.file_lbl.configure(text=os.path.basename(f))
            self.btn_play.configure(state="normal", fg_color=COLOR_FILE_GO)

    def start_file(self):
        self.log("Attempting to start file...")
        if not hasattr(self, 'current_midi_file'): return

        # Guard: If already playing (and not paused), ignore to prevent double-threads
        if self.file_playing and not self.file_paused: return

        if self.use_target_window.get():
            target = self.window_dropdown.get()
            if target and target != "Select Window":
                focus_window_by_title(target)

        if self.file_playing and self.file_paused:
            self.log("Resuming from pause via start_file")
            self.file_paused = False
            self.btn_pause.configure(text="⏸ Pause", fg_color=COLOR_WARN, text_color=COLOR_TEXT_ON_WARN)
            self.update_status_ui("Playing File", os.path.basename(self.current_midi_file), COLOR_FILE_GO)
            return

        self.file_playing = True
        self.file_paused = False
        self.file_thread = threading.Thread(target=self.file_loop, args=(self.current_midi_file,), daemon=True)
        self.file_thread.start()
        self.log(f"File thread started: {self.current_midi_file}")

        self.btn_play.configure(state="disabled", fg_color=COLOR_BTN_DISABLED_BG)
        self.btn_pause.configure(state="normal", text="⏸ Pause", fg_color=COLOR_WARN, text_color=COLOR_TEXT_ON_WARN)
        self.btn_stop.configure(state="normal", fg_color=COLOR_DANGER)
        self.update_status_ui("Playing File", os.path.basename(self.current_midi_file), COLOR_FILE_GO)

    def pause_file(self):
        # Logic (Immediate)
        self.log(f"Pause requested. Current state: Paused={self.file_paused}")
        self.file_paused = not self.file_paused
        if self.file_paused:
            self.release_all_held_keys()
        
        # UI Updates
        if self.file_paused:
            self.btn_pause.configure(text="▶ Resume", fg_color=COLOR_FILE_GO, text_color="white")
            self.update_status_ui("Paused", "File playback paused", COLOR_WARN)
        else:
            self.btn_pause.configure(text="⏸ Pause", fg_color=COLOR_WARN, text_color=COLOR_TEXT_ON_WARN)
            self.update_status_ui("Playing File", os.path.basename(self.current_midi_file), COLOR_FILE_GO)

    def stop_file(self):
        # Logic (Immediate)
        self.log("Stop requested.")
        self.file_playing = False
        self.file_paused = False
        self.release_all_held_keys()
        
        # UI Updates
        self.update_stop_ui()

    def update_stop_ui(self):
        self.btn_play.configure(state="normal", fg_color=COLOR_FILE_GO)
        self.btn_pause.configure(state="disabled", text="⏸ Pause", fg_color=COLOR_BTN_DISABLED_BG, text_color=COLOR_BTN_DISABLED_TEXT)
        self.btn_stop.configure(state="disabled", fg_color=COLOR_BTN_DISABLED_BG)

        if self.live_running:
            self.update_status_ui("Live Active", "File playback stopped", COLOR_LIVE_GO)
        else:
            self.update_status_ui("Ready", "Playback stopped", COLOR_BTN_DISABLED_BG)

    def file_loop(self, filepath):
        try:
            self.log("File loop running")
            mid = mido.MidiFile(filepath)
            # Iterate over messages to manually control timing for speed modification
            for msg in mid:
                if not self.file_playing: break
                
                # Check pause before waiting
                while self.file_paused and self.file_playing:
                    time.sleep(0.1)
                
                # Manually sleep based on message time and speed modifier
                if msg.time > 0:
                    wait_duration = msg.time / self.safe_speed
                    start_time = time.time()
                    
                    while True:
                        now = time.time()
                        elapsed = now - start_time
                        remaining = wait_duration - elapsed
                        
                        if remaining <= 0: break
                        if not self.file_playing: break
                        
                        if self.file_paused:
                            while self.file_paused and self.file_playing:
                                time.sleep(0.1)
                            start_time = time.time()
                            wait_duration = remaining
                            continue
                        
                        time.sleep(min(0.01, remaining))

                if not self.file_playing: break # Check again in case stop was pressed during sleep

                if not self.check_can_press(): continue
                self.process_msg(msg, source='file')
        except Exception as e:
            self.log(f"File Error: {e}")
            print(f"File Error: {e}")
        finally:
            self.log("File loop finished")
            self.after(0, self.stop_file)

    def release_all_held_keys(self):
        with self.key_lock:
            if not self.held_keys: return
            keys_to_release = list(self.held_keys)
            self.held_keys.clear()
            self.log(f"Releasing keys: {keys_to_release}")
            
        for k in keys_to_release:
            pydirectinput.keyUp(k)
        self.after(0, lambda: self.update_note_ui(None, False))

    # --- Shared Logic ---
    def update_note_ui(self, name, active):
        color = COLOR_PRIMARY if active else COLOR_TEXT_SUB
        if active:
            self.note_display.configure(text=name, text_color=color)
            self.file_note_display.configure(text=name, text_color=color)
        else:
            self.note_display.configure(text_color=color)
            self.file_note_display.configure(text_color=color)

    def process_msg(self, msg, source=None):
        if msg.type == 'note_on' and msg.velocity > 0:
            # Apply a more subtle jitter only to note_on events for a more natural feel
            if self.safe_jitter:
                time.sleep(max(0, random.gauss(0.005, 0.002))) # 5ms mean, 2ms std dev

            name = midi_to_note_name(msg.note)
            self.after(0, lambda: self.update_note_ui(name, True))
            k = self.resolve_key(msg.note)
            if k:
                with self.key_lock:
                    # Atomic check: Don't press if we just stopped/paused
                    if source == 'file' and (not self.file_playing or self.file_paused): return
                    if source == 'live' and not self.live_running: return
                    
                    press_keys_for_midi(k, 'down')
                    self._track_key_internal(k, True)
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            self.after(0, lambda: self.update_note_ui(None, False))
            k = self.resolve_key(msg.note)
            if k:
                with self.key_lock:
                    press_keys_for_midi(k, 'up')
                    self._track_key_internal(k, False)

    def _track_key_internal(self, key, is_down):
        keys = key if isinstance(key, list) else [key]
        for k in keys:
            if is_down:
                self.held_keys.add(k)
            else:
                self.held_keys.discard(k)

    def check_can_press(self):
        if not self.safe_use_target: return True
        target = self.safe_target_title
        if not target or target == "Select Window": return True
        return get_active_window_title() == target

    def resolve_key(self, note):
        key = self.key_map.get(note)
        if key: return key
        if self.safe_fallback:
            return find_fallback_key(note, self.key_map)
        return None

    def toggle_pin(self):
        self.attributes("-topmost", self.pin_var.get())

    def on_closing(self):
        if keyboard:
            keyboard.unhook_all()
        self.live_running = False # Stop threads before destroying
        self.release_all_held_keys()
        self.live_running = False
        self.file_playing = False
        self.destroy()

    # --- Hotkey Control ---
    def setup_hotkeys(self):
        self.log("Setting up hotkeys (Raw Hook)...")
        if keyboard:
            try:
                keyboard.unhook_all()
                time.sleep(0.05) # Brief pause to ensure hooks clear
                keyboard.hook(self.on_key_event)
                self.log("Global hook registered.")
            except Exception as e:
                self.log(f"Warning: Could not set up global hotkeys. Administrator rights might be required. {e}")

    def on_key_event(self, event):
        if event.event_type == keyboard.KEY_DOWN:
            key = event.name.lower() if event.name else "unknown"
            
            # Debug Monitoring
            if self.debug_monitor_var.get():
                self.log(f"Input detected: {key}")

            # Check Configured Hotkeys
            hk = self.current_metadata.get("hotkeys", {})
            pp = hk.get("play_pause", "f9").lower()
            stop = hk.get("stop", "f10").lower()

            if key == pp:
                self.on_play_pause_hotkey()
            elif key == stop:
                self.on_stop_hotkey()

    def on_play_pause_hotkey(self):
        # Debounce: Prevent rapid firing if key is held
        if hasattr(self, '_last_pp_time') and time.time() - self._last_pp_time < 0.2:
            return
        self._last_pp_time = time.time()

        # Offload logic to thread so hook returns INSTANTLY (prevents hook timeout)
        threading.Thread(target=self._handle_play_pause_logic, daemon=True).start()

    def _handle_play_pause_logic(self):
        self.log("Hotkey: Play/Pause pressed")
        if not hasattr(self, 'current_midi_file') or not self.current_midi_file:
            self.log("Hotkey ignored: No file selected")
            return # No file selected

        if not self.file_playing:
            # CRITICAL: Must use .after() because start_file accesses UI elements (crash if called from thread)
            self.after(0, self.start_file)
        else:
            self.log("Hotkey: Toggling Pause")
            # Pause/Resume Logic - IMMEDIATE
            self.file_paused = not self.file_paused
            if self.file_paused:
                self.release_all_held_keys()
            
            # Schedule UI update
            self.after(0, self._update_pause_ui_from_hotkey)

    def _update_pause_ui_from_hotkey(self):
        # Sync UI with the state set in hotkey
        if self.file_paused:
            self.btn_pause.configure(text="▶ Resume", fg_color=COLOR_FILE_GO, text_color="white")
            self.update_status_ui("Paused", "File playback paused", COLOR_WARN)
        else:
            self.btn_pause.configure(text="⏸ Pause", fg_color=COLOR_WARN, text_color=COLOR_TEXT_ON_WARN)
            self.update_status_ui("Playing File", os.path.basename(self.current_midi_file), COLOR_FILE_GO)

    def on_stop_hotkey(self):
        # Debounce: Prevent rapid firing if key is held
        if hasattr(self, '_last_stop_time') and time.time() - self._last_stop_time < 0.2:
            return
        self._last_stop_time = time.time()

        # Offload logic to thread so hook returns INSTANTLY
        threading.Thread(target=self._handle_stop_logic, daemon=True).start()

    def _handle_stop_logic(self):
        self.log("Hotkey: Stop pressed")
        # Stop Logic - IMMEDIATE
        self.file_playing = False
        self.file_paused = False
        self.release_all_held_keys()
        
        # Schedule UI update
        self.after(0, self.update_stop_ui)

    def open_hotkey_editor(self):
        if not keyboard:
            messagebox.showerror("Error", "The 'keyboard' library is not installed.\nRun: pip install keyboard")
            return
        HotkeyEditor(self, self.current_metadata.get("hotkeys", {"play_pause": "f9", "stop": "f10"}), self.update_hotkeys_from_editor)

    def update_hotkeys_from_editor(self, new_hotkeys):
        self.current_metadata["hotkeys"] = new_hotkeys
        self.save_current_map()
        self.setup_hotkeys()

    # --- Profile Dialogs ---
    def open_profile_manager(self):
        self.scan_profiles() # Refresh cache
        ProfileManager(self, self.profile_cache, self.load_profile, self.scan_profiles)

    def load_profile(self, filename):
        self.current_filename = filename
        self.key_map, self.current_metadata = load_profile_data(filename)
        self.profile_lbl.configure(text=self.current_metadata.get("name", filename))
        # Update window title to show loaded profile
        self.title(f"MIDI Keybind Pro - {self.current_metadata.get('name', filename)}")

    def save_current_map(self):
        save_profile_data(self.current_filename, self.key_map, self.current_metadata)

    def open_editor(self):
        SleekEditor(self, self.key_map, self.update_key_map)

    def update_key_map(self, new_map):
        self.key_map = new_map
        save_profile_data(self.current_filename, self.key_map, self.current_metadata)

# --- Profile Manager Class ---
class ProfileManager(ctk.CTkToplevel):
    def __init__(self, parent, profiles, load_callback, refresh_callback):
        super().__init__(parent)
        self.title("Profile Manager")
        self.geometry("500x400")
        self.profiles = profiles
        self.load_callback = load_callback
        self.refresh_callback = refresh_callback
        self.parent = parent

        self.attributes("-topmost", True)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=15)
        ctk.CTkLabel(top_frame, text="Configuration Profiles", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        ctk.CTkButton(top_frame, text="+ New", width=80, fg_color=COLOR_LIVE_GO, command=self.create_new).pack(side="right")

        # List
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="#222")
        self.scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self.scroll.grid_columnconfigure(0, weight=1)
        
        self.populate_list()
        self.grab_set()

    def populate_list(self):
        for widget in self.scroll.winfo_children(): widget.destroy()
        
        for prof in self.profiles:
            row = ctk.CTkFrame(self.scroll, fg_color="#2b2b2b")
            row.pack(fill="x", pady=2)
            
            info_frame = ctk.CTkFrame(row, fg_color="transparent")
            info_frame.pack(side="left", padx=10, pady=5)
            
            name = prof["metadata"].get("name", "Unknown")
            link = prof["metadata"].get("linked_window", "")
            
            ctk.CTkLabel(info_frame, text=name, font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
            if link:
                ctk.CTkLabel(info_frame, text=f"🔗 Auto-switch: {link}", font=ctk.CTkFont(size=11), text_color=COLOR_PRIMARY).pack(anchor="w")
            else:
                ctk.CTkLabel(info_frame, text="No auto-switch linked", font=ctk.CTkFont(size=11), text_color="#666").pack(anchor="w")
                ctk.CTkLabel(info_frame, text="Manual switch only", font=ctk.CTkFont(size=11), text_color="#666").pack(anchor="w")

            ctk.CTkButton(row, text="Load", width=50, height=24, fg_color="#444", hover_color=COLOR_PRIMARY, command=lambda f=prof["filename"]: self.do_load(f)).pack(side="right", padx=5)
            ctk.CTkButton(row, text="⚙", width=30, height=24, fg_color="transparent", border_width=1, border_color="#555", command=lambda p=prof: self.edit_meta(p)).pack(side="right", padx=5)

    def do_load(self, filename):
        self.load_callback(filename)
        self.destroy()

    def create_new(self):
        self.edit_meta(None)

    def edit_meta(self, profile_data):
        # If profile_data is None, we are creating new
        is_new = profile_data is None
        title = "Create Profile" if is_new else "Edit Profile Settings"
        
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("300x250")
        dialog.transient(self)
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Profile Name").pack(pady=(15, 5))
        name_entry = ctk.CTkEntry(dialog)
        name_entry.pack(pady=5)
        if not is_new: name_entry.insert(0, profile_data["metadata"].get("name", ""))

        ctk.CTkLabel(dialog, text="Auto-Switch Window Title (Optional)").pack(pady=(15, 5))
        
        # Use ComboBox to allow selecting open windows OR typing custom ones
        link_entry = ctk.CTkComboBox(dialog, values=get_open_windows())
        link_entry.pack(pady=5)
        if not is_new: 
            link_entry.set(profile_data["metadata"].get("linked_window", ""))
        else:
            link_entry.set("")

        def save():
            name = name_entry.get()
            link = link_entry.get()
            if not name: return
            
            if is_new:
                safe_name = "".join([c for c in name if c.isalnum() or c in (' ', '-', '_')]).strip()
                filename = f"{safe_name.replace(' ', '_')}.json"
                mappings = create_default_88_key_map()
            else:
                filename = profile_data["filename"]
                mappings, _ = load_profile_data(filename)

            save_profile_data(filename, mappings, {"name": name, "linked_window": link})
            self.refresh_callback() # Refresh parent cache
            self.profiles = self.parent.profile_cache # Update local list
            self.populate_list()
            dialog.destroy()

        ctk.CTkButton(dialog, text="Save", command=save, fg_color=COLOR_LIVE_GO).pack(pady=20)

# --- Sleek Editor Class ---
class SleekEditor(ctk.CTkToplevel):
    def __init__(self, parent, key_map, callback):
        super().__init__(parent)
        self.title("Keymap Editor")
        self.geometry("400x600")
        self.callback = callback
        self.attributes("-topmost", True)
        self.temp_map = copy.deepcopy(key_map)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Double-click to edit mappings", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, pady=15)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background="#2b2b2b", foreground="white", fieldbackground="#2b2b2b", borderwidth=0, rowheight=28)
        style.map('Treeview', background=[('selected', COLOR_PRIMARY)])
        style.configure("Treeview.Heading", background="#333", foreground="white", relief="flat")

        cols = ("MIDI", "Note", "Keys")
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        self.tree.heading("MIDI", text="MIDI")
        self.tree.heading("Note", text="NOTE")
        self.tree.heading("Keys", text="MAPPED KEY")
        self.tree.column("MIDI", width=60, anchor="center")
        self.tree.column("Note", width=60, anchor="center")
        self.tree.column("Keys", width=150, anchor="center")

        self.tree.grid(row=1, column=0, sticky="nsew", padx=20)
        self.populate()
        self.tree.bind("<Double-1>", self.on_click)

        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.grid(row=2, column=0, pady=20)

        ctk.CTkButton(action_frame, text="Save Changes", command=self.save, fg_color=COLOR_LIVE_GO, hover_color="#238636").pack(side="left", padx=5)
        ctk.CTkButton(action_frame, text="Cancel", command=self.destroy, fg_color="transparent", border_width=1, text_color="#AAAAAA").pack(side="left", padx=5)
        ctk.CTkButton(action_frame, text="Clear All", command=self.clear, fg_color="#333", hover_color=COLOR_DANGER).pack(side="left", padx=5)

        self.grab_set()

    def populate(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        for note in range(21, 109):
            key = self.temp_map.get(note, "-")
            d_key = '+'.join(key) if isinstance(key, list) else key
            self.tree.insert("", "end", values=(note, midi_to_note_name(note), d_key))

    def on_click(self, event):
        item = self.tree.identify('item', event.x, event.y)
        if not item: return
        vals = self.tree.item(item, "values")
        note = int(vals[0])
        dialog = SleekKeyCapture(self, f"Press Key for {vals[1]}")
        res = dialog.result
        if res is not None:
            if res: self.temp_map[note] = res[0] if len(res)==1 else res
            else: self.temp_map.pop(note, None)
            self.populate()

    def clear(self):
        if messagebox.askyesno("Confirm", "Clear all bindings?"):
            self.temp_map.clear()
            self.populate()

    def save(self):
        self.callback(self.temp_map)
        self.destroy()

class SleekKeyCapture(ctk.CTkToplevel):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.geometry("300x200")
        self.title("")
        self.result = None
        self.attributes("-topmost", True)
        self.keys = []
        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=14)).pack(pady=(20, 5))
        self.lbl = ctk.CTkLabel(self, text="...", font=ctk.CTkFont(size=24, weight="bold"), text_color=COLOR_PRIMARY)
        self.lbl.pack(pady=10)
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(side="bottom", pady=20)
        ctk.CTkButton(btn_frame, text="Clear", width=60, fg_color="#444", command=self.do_clear).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Unbind", width=60, fg_color=COLOR_DANGER, command=self.do_unbind).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Save", width=60, fg_color=COLOR_LIVE_GO, command=self.do_save).pack(side="left", padx=5)
        self.bind("<KeyPress>", self.on_key)
        self.focus_force()
        self.wait_window()

    def on_key(self, event):
        k = event.keysym.lower()
        if k not in self.keys:
            self.keys.append(k)
            self.lbl.configure(text=" + ".join(self.keys))
    def do_clear(self):
        self.keys = []
        self.lbl.configure(text="...")
    def do_unbind(self):
        self.result = []
        self.destroy()
    def do_save(self):
        self.result = self.keys
        self.destroy()

class HotkeyEditor(ctk.CTkToplevel):
    def __init__(self, parent, current_hotkeys, callback):
        super().__init__(parent)
        self.title("Global Hotkeys")
        self.geometry("350x250")
        self.callback = callback
        self.attributes("-topmost", True)
        self.hotkeys = current_hotkeys.copy()
        self.capturing = False
        
        self.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self, text="Global Media Controls", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(20, 15))
        
        self.btn_pp = self.create_row("Play / Pause", "play_pause")
        self.btn_stop = self.create_row("Stop Playback", "stop")
        
        ctk.CTkButton(self, text="Save & Close", command=self.save, fg_color=COLOR_LIVE_GO).pack(pady=20)
        self.grab_set()
        
    def create_row(self, label, key_key):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(f, text=label).pack(side="left")
        btn = ctk.CTkButton(f, text=self.hotkeys.get(key_key, "None"), width=120, 
                            command=lambda: self.start_capture(key_key))
        btn.pack(side="right")
        return btn

    def start_capture(self, key_key):
        if self.capturing: return
        self.capturing = True
        
        btn = self.btn_pp if key_key == "play_pause" else self.btn_stop
        btn.configure(text="Press key...", fg_color=COLOR_WARN, text_color=COLOR_TEXT_ON_WARN)
        
        threading.Thread(target=self.capture_thread, args=(key_key, btn), daemon=True).start()

    def capture_thread(self, key_key, btn):
        try:
            time.sleep(0.2) # Debounce click
            hk = keyboard.read_hotkey(suppress=True)
            self.after(0, lambda: self.finish_capture(key_key, btn, hk))
        except Exception as e:
            print(f"Capture failed: {e}")
            self.after(0, self.cancel_capture)

    def cancel_capture(self):
        self.capturing = False

    def finish_capture(self, key_key, btn, hotkey):
        self.hotkeys[key_key] = hotkey
        btn.configure(text=hotkey, fg_color=COLOR_PRIMARY, text_color="white")
        self.capturing = False

    def save(self):
        self.callback(self.hotkeys)
        self.destroy()

if __name__ == "__main__":
    pydirectinput.PAUSE = 0
    app = MidiKeyTranslatorApp()
    app.mainloop()