import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
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

from constants import *
from utils import *
from ui_components import *
from midi_processing import *

class MidiKeyTranslatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.extract_bundled_configs()

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

        self.pin_var = tk.BooleanVar(value=True)
        self.fallback_var = tk.BooleanVar(value=True)
        self.jitter_var = tk.BooleanVar(value=False)
        self.use_target_window = tk.BooleanVar(value=True)
        self.speed_modifier_var = tk.DoubleVar(value=1.0)
        self.target_window_title = tk.StringVar(value="")
        self.transpose_var = tk.IntVar(value=0)

        self.safe_speed = 1.0
        self.safe_use_target = True
        self.safe_target_title = ""
        self.safe_jitter = False
        self.safe_fallback = True

        self.current_filename = DEFAULT_FILENAME
        self.key_map, self.current_metadata = load_profile_data(self.current_filename)
        
        self.profile_cache = []
        self.scan_profiles()

        self.main_container = ctk.CTkScrollableFrame(self, fg_color=COLOR_BG, corner_radius=0)
        self.main_container.grid(row=0, column=0, sticky="nsew")
        self.main_container.grid_columnconfigure(0, weight=1)

        self.build_header()
        self.build_status_card()
        self.build_config_card()
        self.build_live_card()
        self.build_file_card()
        self.build_footer()

        self.populate_midi_devices()
        self.populate_window_list()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.setup_hotkeys()
        self.toggle_pin()
        self.after(1000, self.check_initial_profile)
        self.after(200, self.check_disclaimer)

    def extract_bundled_configs(self):
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
        self.profile_cache = []
        try:
            for f in os.listdir("."):
                if f.lower().endswith(".json"):
                    _, meta = load_profile_data(f)
                    self.profile_cache.append({"filename": f, "metadata": meta})
        except Exception as e:
            print(f"Scan error: {e}")

    def check_initial_profile(self):
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
        
        dialog = ctk.CTkToplevel(self)
        dialog.title("Welcome!")
        dialog.geometry("420x340")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.transient(self)
        dialog.grab_set()

        try:
            x = self.winfo_x() + (self.winfo_width() // 2) - 210
            y = self.winfo_y() + (self.winfo_height() // 2) - 170
            dialog.geometry(f"+{x}+{y}")
        except:
            pass

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

        # Transpose Control
        trans_frame = ctk.CTkFrame(card, fg_color="transparent")
        trans_frame.grid(row=5, column=0, padx=20, pady=(0, 15), sticky="ew")
        
        ctk.CTkLabel(trans_frame, text="Transpose:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkButton(trans_frame, text="-", width=30, height=24, command=lambda: self.change_transpose(-1)).pack(side="left", padx=(10, 5))
        self.transpose_lbl = ctk.CTkLabel(trans_frame, text="0", width=30, font=ctk.CTkFont(family="Consolas", weight="bold"))
        self.transpose_lbl.pack(side="left")
        ctk.CTkButton(trans_frame, text="+", width=30, height=24, command=lambda: self.change_transpose(1)).pack(side="left", padx=5)
        self.create_info_btn(trans_frame, "Transposition", "Shifts all incoming notes up or down by semitones.\nHotkeys can be configured in settings.").pack(side="left", padx=10)

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

        self.note_display = ctk.CTkLabel(head, text="--", font=ctk.CTkFont(family="Consolas", size=14, weight="bold"), text_color=COLOR_TEXT_SUB, width=50)
        self.note_display.pack(side="right", padx=(0, 10))

        device_frame = ctk.CTkFrame(card, fg_color="transparent")
        device_frame.grid(row=1, column=0, padx=20, pady=(5, 10), sticky="ew")
        device_frame.grid_columnconfigure(0, weight=1)
        
        self.device_var = ctk.StringVar(value="Select Device...")
        self.device_menu = ctk.CTkOptionMenu(device_frame, variable=self.device_var, command=self.on_device_select, fg_color="#333", button_color="#444", button_hover_color="#555", text_color="white")
        self.device_menu.grid(row=0, column=0, sticky="ew")

        ctk.CTkButton(device_frame, text="↻", width=30, height=25, command=self.populate_midi_devices, fg_color="#333", hover_color="#444").grid(row=0, column=1, padx=(5,0))

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
        self.file_note_display = ctk.CTkLabel(head, text="--", font=ctk.CTkFont(family="Consolas", size=14, weight="bold"), text_color=COLOR_TEXT_SUB, width=50)
        self.file_note_display.pack(side="right")

        file_frame = ctk.CTkFrame(card, fg_color="transparent")
        file_frame.grid(row=1, column=0, padx=20, pady=5, sticky="ew")

        self.file_lbl = ctk.CTkLabel(file_frame, text="No file selected", text_color="gray")
        self.file_lbl.pack(side="left", fill="x", expand=True, anchor="w")
        ctk.CTkButton(file_frame, text="Select File", width=80, command=self.select_file, fg_color="#333", hover_color="#444").pack(side="right")

        speed_frame = ctk.CTkFrame(card, fg_color="transparent")
        speed_frame.grid(row=2, column=0, padx=20, pady=(5, 10), sticky="ew")
        speed_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(speed_frame, text="Playback Speed:", font=ctk.CTkFont(size=12)).grid(row=0, column=0, sticky="w")
        
        self.speed_slider = ctk.CTkSlider(
            speed_frame,
            from_=0.25, to=4.0,
            number_of_steps=15,
            variable=self.speed_modifier_var,
            command=self.on_speed_change,
            button_color=COLOR_PRIMARY,
            progress_color=COLOR_PRIMARY
        )
        self.speed_slider.grid(row=0, column=1, padx=(10, 0), sticky="ew")

        self.speed_label = ctk.CTkLabel(speed_frame, text="1.00x", font=ctk.CTkFont(size=12, weight="bold"))
        self.speed_label.grid(row=0, column=2, padx=(10, 0), sticky="e")

        ctrl_frame = ctk.CTkFrame(card, fg_color="transparent")
        ctrl_frame.grid(row=3, column=0, padx=20, pady=(10, 15), sticky="ew")
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
            text_color=COLOR_TEXT_ON_WARN,
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
            
            ctk.CTkCheckBox(self.debug_win, text="Monitor Key Input", variable=self.debug_monitor_var, font=ctk.CTkFont(size=12)).pack(pady=5)
        self.debug_win.lift()

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] {message}"
        print(full_msg)
        self.after(0, lambda: self._update_log_ui(full_msg))

    def _update_log_ui(self, full_msg):
        if self.debug_win is not None and self.debug_win.winfo_exists() and self.debug_text:
            self.debug_text.configure(state="normal")
            self.debug_text.insert("end", full_msg + "\n")
            self.debug_text.see("end")
            self.debug_text.configure(state="disabled")

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

    def manual_start_live(self):
        device = self.device_var.get()
        if device not in ["No Device Found", "Error", "Select Device..."]:
            self.start_live(device)

    def start_live(self, device_name):
        self.live_running = True
        self.live_thread = threading.Thread(target=live_loop, args=(self, device_name,), daemon=True)
        self.live_thread.start()

        self.start_live_btn.configure(state="disabled")
        self.stop_live_btn.configure(state="normal")
        self.device_menu.configure(state="disabled")
        self.live_dot.configure(text_color=COLOR_LIVE_GO)
        self.update_status_ui("Live Active", f"Input: {device_name}", COLOR_LIVE_GO)

    def stop_live(self):
        self.live_running = False
        release_all_held_keys(self)
        self.stop_live_btn.configure(state="disabled")
        self.start_live_btn.configure(state="normal")
        self.device_menu.configure(state="normal")
        self.live_dot.configure(text_color=COLOR_BTN_DISABLED_TEXT)

        if self.file_playing:
            self.update_status_ui("Playing File", "Live input stopped", COLOR_FILE_GO)
        else:
            self.update_status_ui("Ready", "Live input stopped", COLOR_BTN_DISABLED_BG)

    def select_file(self):
        f = filedialog.askopenfilename(filetypes=[("MIDI", "*.mid *.midi")])
        if f:
            self.current_midi_file = f
            self.file_lbl.configure(text=os.path.basename(f))
            self.btn_play.configure(state="normal", fg_color=COLOR_FILE_GO)

    def start_file(self):
        self.log("Attempting to start file...")
        if not hasattr(self, 'current_midi_file'): return

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
        self.file_thread = threading.Thread(target=file_loop, args=(self, self.current_midi_file,), daemon=True)
        self.file_thread.start()
        self.log(f"File thread started: {self.current_midi_file}")

        self.btn_play.configure(state="disabled", fg_color=COLOR_BTN_DISABLED_BG)
        self.btn_pause.configure(state="normal", text="⏸ Pause", fg_color=COLOR_WARN, text_color=COLOR_TEXT_ON_WARN)
        self.btn_stop.configure(state="normal", fg_color=COLOR_DANGER)
        self.update_status_ui("Playing File", os.path.basename(self.current_midi_file), COLOR_FILE_GO)

    def pause_file(self):
        self.log(f"Pause requested. Current state: Paused={self.file_paused}")
        self.file_paused = not self.file_paused
        if self.file_paused:
            release_all_held_keys(self)
        
        if self.file_paused:
            self.btn_pause.configure(text="▶ Resume", fg_color=COLOR_FILE_GO, text_color="white")
            self.update_status_ui("Paused", "File playback paused", COLOR_WARN)
        else:
            self.btn_pause.configure(text="⏸ Pause", fg_color=COLOR_WARN, text_color=COLOR_TEXT_ON_WARN)
            self.update_status_ui("Playing File", os.path.basename(self.current_midi_file), COLOR_FILE_GO)

    def stop_file(self):
        self.log("Stop requested.")
        self.file_playing = False
        self.file_paused = False
        release_all_held_keys(self)
        
        self.update_stop_ui()

    def update_stop_ui(self):
        self.btn_play.configure(state="normal", fg_color=COLOR_FILE_GO)
        self.btn_pause.configure(state="disabled", text="⏸ Pause", fg_color=COLOR_BTN_DISABLED_BG, text_color=COLOR_BTN_DISABLED_TEXT)
        self.btn_stop.configure(state="disabled", fg_color=COLOR_BTN_DISABLED_BG)

        if self.live_running:
            self.update_status_ui("Live Active", "File playback stopped", COLOR_LIVE_GO)
        else:
            self.update_status_ui("Ready", "Playback stopped", COLOR_BTN_DISABLED_BG)

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
            if self.safe_jitter:
                time.sleep(max(0, random.gauss(0.005, 0.002)))

            # Apply transposition
            note_val = msg.note + self.transpose_var.get()
            if not (0 <= note_val <= 127): return

            name = midi_to_note_name(note_val)
            self.after(0, lambda: self.update_note_ui(name, True))
            k = self.resolve_key(note_val)
            if k:
                with self.key_lock:
                    if source == 'file' and (not self.file_playing or self.file_paused): return
                    if source == 'live' and not self.live_running: return
                    
                    press_keys_for_midi(k, 'down')
                    self._track_key_internal(k, True)
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            note_val = msg.note + self.transpose_var.get()
            if not (0 <= note_val <= 127): return

            self.after(0, lambda: self.update_note_ui(None, False))
            k = self.resolve_key(note_val)
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
        self.live_running = False
        release_all_held_keys(self)
        self.live_running = False
        self.file_playing = False
        self.destroy()

    def setup_hotkeys(self):
        self.log("Setting up hotkeys (Raw Hook)...")
        if keyboard:
            try:
                keyboard.unhook_all()
                time.sleep(0.05)
                keyboard.hook(self.on_key_event)
                self.log("Global hook registered.")
            except Exception as e:
                self.log(f"Warning: Could not set up global hotkeys. Administrator rights might be required. {e}")

    def on_key_event(self, event):
        if event.event_type == keyboard.KEY_DOWN:
            key = event.name.lower() if event.name else "unknown"
            
            if self.debug_monitor_var.get():
                self.log(f"Input detected: {key}")

            hk = self.current_metadata.get("hotkeys", {})
            pp = hk.get("play_pause", "f9").lower()
            stop = hk.get("stop", "f10").lower()
            t_up = hk.get("transpose_up", "page up").lower()
            t_down = hk.get("transpose_down", "page down").lower()

            if key == pp:
                self.on_play_pause_hotkey()
            elif key == stop:
                self.on_stop_hotkey()
            elif key == t_up:
                self.change_transpose(1)
            elif key == t_down:
                self.change_transpose(-1)

    def on_play_pause_hotkey(self):
        if hasattr(self, '_last_pp_time') and time.time() - self._last_pp_time < 0.2:
            return
        self._last_pp_time = time.time()

        threading.Thread(target=self._handle_play_pause_logic, daemon=True).start()

    def _handle_play_pause_logic(self):
        self.log("Hotkey: Play/Pause pressed")
        if not hasattr(self, 'current_midi_file') or not self.current_midi_file:
            self.log("Hotkey ignored: No file selected")
            return

        if not self.file_playing:
            self.after(0, self.start_file)
        else:
            self.log("Hotkey: Toggling Pause")
            self.file_paused = not self.file_paused
            if self.file_paused:
                release_all_held_keys(self)
            
            self.after(0, self._update_pause_ui_from_hotkey)

    def _update_pause_ui_from_hotkey(self):
        if self.file_paused:
            self.btn_pause.configure(text="▶ Resume", fg_color=COLOR_FILE_GO, text_color="white")
            self.update_status_ui("Paused", "File playback paused", COLOR_WARN)
        else:
            self.btn_pause.configure(text="⏸ Pause", fg_color=COLOR_WARN, text_color=COLOR_TEXT_ON_WARN)
            self.update_status_ui("Playing File", os.path.basename(self.current_midi_file), COLOR_FILE_GO)

    def on_stop_hotkey(self):
        if hasattr(self, '_last_stop_time') and time.time() - self._last_stop_time < 0.2:
            return
        self._last_stop_time = time.time()

        threading.Thread(target=self._handle_stop_logic, daemon=True).start()

    def _handle_stop_logic(self):
        self.log("Hotkey: Stop pressed")
        self.file_playing = False
        self.file_paused = False
        release_all_held_keys(self)
        
        self.after(0, self.update_stop_ui)

    def change_transpose(self, delta):
        new_val = self.transpose_var.get() + delta
        self.transpose_var.set(new_val)
        
        if hasattr(self, 'transpose_lbl'):
            prefix = "+" if new_val > 0 else ""
            self.transpose_lbl.configure(text=f"{prefix}{new_val}")
            
        release_all_held_keys(self)

    def open_hotkey_editor(self):
        if not keyboard:
            messagebox.showerror("Error", "The 'keyboard' library is not installed.\nRun: pip install keyboard")
            return
        HotkeyEditor(self, self.current_metadata.get("hotkeys", {"play_pause": "f9", "stop": "f10"}), self.update_hotkeys_from_editor)

    def update_hotkeys_from_editor(self, new_hotkeys):
        self.current_metadata["hotkeys"] = new_hotkeys
        self.save_current_map()
        self.setup_hotkeys()

    def open_profile_manager(self):
        self.scan_profiles()
        ProfileManager(self, self.profile_cache, self.load_profile, self.scan_profiles)

    def load_profile(self, filename):
        self.current_filename = filename
        self.key_map, self.current_metadata = load_profile_data(filename)
        self.profile_lbl.configure(text=self.current_metadata.get("name", filename))
        self.title(f"MIDI Keybind Pro - {self.current_metadata.get('name', filename)}")

    def save_current_map(self):
        save_profile_data(self.current_filename, self.key_map, self.current_metadata)

    def open_editor(self):
        SleekEditor(self, self.key_map, self.update_key_map)

    def update_key_map(self, new_map):
        self.key_map = new_map
        save_profile_data(self.current_filename, self.key_map, self.current_metadata)

if __name__ == "__main__":
    pydirectinput.PAUSE = 0
    app = MidiKeyTranslatorApp()
    app.mainloop()
