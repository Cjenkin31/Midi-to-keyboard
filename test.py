import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import mido
import threading
import time
import pydirectinput
import copy
import json
import os
import ctypes
import webbrowser
import shutil
import sys
try:
    import rtmidi
except ImportError:
    pass

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
    default_meta = {"name": display_name, "linked_window": ""}
    
    try:
        with open(target_path, 'r') as f:
            data = json.load(f)
            # Check for new format with metadata
            if "metadata" in data and "mappings" in data:
                meta = data["metadata"]
                if meta.get("name") == "Unnamed Profile":
                    meta["name"] = display_name
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

        self.title("MIDI Keybind Pro")
        self.geometry("500x820")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Application State ---
        self.live_running = False
        self.file_playing = False
        self.file_paused = False
        self.file_thread = None
        self.live_thread = None

        # Configuration
        self.pin_var = tk.BooleanVar(value=True)
        self.fallback_var = tk.BooleanVar(value=True)
        self.use_target_window = tk.BooleanVar(value=True)
        self.target_window_title = tk.StringVar(value="")

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
        self.toggle_pin()
        self.after(1000, self.auto_switch_loop)

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

    def auto_switch_loop(self):
        """Checks active window and switches profile if a link is found."""
        active = get_active_window_title()
        if active:
            for prof in self.profile_cache:
                link = prof["metadata"].get("linked_window", "")
                if link and link.lower() in active.lower() and prof["filename"] != self.current_filename:
                    self.load_profile(prof["filename"])
                    break
        self.after(1500, self.auto_switch_loop)

    def build_header(self):
        header = ctk.CTkFrame(self.main_container, fg_color="transparent")
        header.grid(row=0, column=0, pady=(20, 10), sticky="ew")
        ctk.CTkLabel(header, text="MIDI Keybind Pro", font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold")).pack()
        ctk.CTkLabel(header, text="Universal MIDI Input Translator", font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_SUB).pack()

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

        self.status_main = ctk.CTkLabel(text_frame, text="Inactive", font=ctk.CTkFont(size=18, weight="bold"), anchor="w")
        self.status_main.pack(anchor="w")

        self.status_sub = ctk.CTkLabel(text_frame, text="Select a device or file to begin", font=ctk.CTkFont(size=13), text_color=COLOR_TEXT_SUB, anchor="w")
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

        ctk.CTkButton(prof_frame, text="Manage Profiles", width=100, height=25, fg_color="#333", hover_color="#444", command=self.open_profile_manager).pack(side="right", padx=2)
        ctk.CTkButton(prof_frame, text="Save Map", width=60, height=25, fg_color="#333", hover_color="#444", command=self.save_current_map).pack(side="right", padx=2)
        ctk.CTkButton(prof_frame, text="Edit Map", width=80, height=25, fg_color=COLOR_PRIMARY, command=self.open_editor).pack(side="right", padx=10)

        fb_frame = ctk.CTkFrame(card, fg_color="transparent")
        fb_frame.grid(row=2, column=0, padx=20, pady=10, sticky="w")
        self.fallback_switch = ctk.CTkSwitch(fb_frame, text="Smart Octave Fallback", variable=self.fallback_var, button_color=COLOR_PRIMARY, progress_color=COLOR_PRIMARY)
        self.fallback_switch.pack(side="left")
        self.create_info_btn(fb_frame, "Smart Octave Fallback", "If a note is not mapped, this attempts to find the same note in a different octave that IS mapped.").pack(side="left", padx=10)

        target_frame = ctk.CTkFrame(card, fg_color="transparent")
        target_frame.grid(row=3, column=0, padx=20, pady=(5, 15), sticky="ew")

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

        self.live_dot = ctk.CTkLabel(head, text="●", font=ctk.CTkFont(size=16), text_color=COLOR_BTN_DISABLED_TEXT)
        self.live_dot.pack(side="right")

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

        ctk.CTkLabel(card, text="MIDI FILE PLAYER", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_SUB).grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")

        file_frame = ctk.CTkFrame(card, fg_color="transparent")
        file_frame.grid(row=1, column=0, padx=20, pady=5, sticky="ew")

        self.file_lbl = ctk.CTkLabel(file_frame, text="No file selected", text_color="gray")
        self.file_lbl.pack(side="left", fill="x", expand=True, anchor="w")
        ctk.CTkButton(file_frame, text="Select File", width=80, command=self.select_file, fg_color="#333", hover_color="#444").pack(side="right")

        ctrl_frame = ctk.CTkFrame(card, fg_color="transparent")
        ctrl_frame.grid(row=2, column=0, padx=20, pady=(10, 15), sticky="ew")
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
                        self.process_msg(msg)
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
        if not hasattr(self, 'current_midi_file'): return
        if self.file_playing and self.file_paused:
            self.file_paused = False
            self.btn_pause.configure(text="⏸ Pause", fg_color=COLOR_WARN, text_color=COLOR_TEXT_ON_WARN)
            self.update_status_ui("Playing File", os.path.basename(self.current_midi_file), COLOR_FILE_GO)
            return

        self.file_playing = True
        self.file_paused = False
        self.file_thread = threading.Thread(target=self.file_loop, args=(self.current_midi_file,), daemon=True)
        self.file_thread.start()

        self.btn_play.configure(state="disabled", fg_color=COLOR_BTN_DISABLED_BG)
        self.btn_pause.configure(state="normal", text="⏸ Pause", fg_color=COLOR_WARN, text_color=COLOR_TEXT_ON_WARN)
        self.btn_stop.configure(state="normal", fg_color=COLOR_DANGER)
        self.update_status_ui("Playing File", os.path.basename(self.current_midi_file), COLOR_FILE_GO)

    def pause_file(self):
        self.file_paused = not self.file_paused
        if self.file_paused:
            self.btn_pause.configure(text="▶ Resume", fg_color=COLOR_FILE_GO, text_color="white")
            self.update_status_ui("Paused", "File playback paused", COLOR_WARN)
        else:
            self.btn_pause.configure(text="⏸ Pause", fg_color=COLOR_WARN, text_color=COLOR_TEXT_ON_WARN)
            self.update_status_ui("Playing File", os.path.basename(self.current_midi_file), COLOR_FILE_GO)

    def stop_file(self):
        self.file_playing = False
        self.file_paused = False
        self.btn_play.configure(state="normal", fg_color=COLOR_FILE_GO)
        self.btn_pause.configure(state="disabled", text="⏸ Pause", fg_color=COLOR_BTN_DISABLED_BG, text_color=COLOR_BTN_DISABLED_TEXT)
        self.btn_stop.configure(state="disabled", fg_color=COLOR_BTN_DISABLED_BG)

        if self.live_running:
            self.update_status_ui("Live Active", "File playback stopped", COLOR_LIVE_GO)
        else:
            self.update_status_ui("Ready", "Playback stopped", COLOR_BTN_DISABLED_BG)

    def file_loop(self, filepath):
        try:
            mid = mido.MidiFile(filepath)
            for msg in mid.play():
                if not self.file_playing: break
                while self.file_paused and self.file_playing:
                    time.sleep(0.1)
                if not self.check_can_press(): continue
                self.process_msg(msg)
        except Exception as e:
            print(f"File Error: {e}")
        finally:
            self.after(0, self.stop_file)

    # --- Shared Logic ---
    def process_msg(self, msg):
        if msg.type == 'note_on' and msg.velocity > 0:
            k = self.resolve_key(msg.note)
            if k: press_keys_for_midi(k, 'down')
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            k = self.resolve_key(msg.note)
            if k: press_keys_for_midi(k, 'up')

    def check_can_press(self):
        if not self.use_target_window.get(): return True
        target = self.window_dropdown.get()
        if not target or target == "Select Window": return True
        return get_active_window_title() == target

    def resolve_key(self, note):
        key = self.key_map.get(note)
        if key: return key
        if self.fallback_var.get():
            return find_fallback_key(note, self.key_map)
        return None

    def toggle_pin(self):
        self.attributes("-topmost", self.pin_var.get())

    def on_closing(self):
        self.live_running = False
        self.file_playing = False
        self.destroy()

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

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=15)
        ctk.CTkLabel(top_frame, text="Configuration Profiles", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        ctk.CTkButton(top_frame, text="+ Create New", width=100, fg_color=COLOR_LIVE_GO, command=self.create_new).pack(side="right")

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

if __name__ == "__main__":
    pydirectinput.PAUSE = 0
    app = MidiKeyTranslatorApp()
    app.mainloop()