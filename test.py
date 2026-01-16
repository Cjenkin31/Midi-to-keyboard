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

# --- Theme Configuration ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# Color Palette
COLOR_BG = "#1a1a1a"
COLOR_CARD = "#2b2b2b"
COLOR_ACCENT = "#3B8ED0"    # Blue
COLOR_SUCCESS = "#2CC985"   # Green
COLOR_DANGER = "#E04F5F"    # Red
COLOR_WARN = "#E5C07B"      # Yellow/Orange for Pause
COLOR_TEXT_MAIN = "#FFFFFF"
COLOR_TEXT_SUB = "#A0A0A0"

DEFAULT_FILENAME = "default_keymap.json"
user32 = ctypes.windll.user32

# --- Windows API Helpers ---
def get_open_windows():
    """Returns a list of titles for visible windows."""
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
    return sorted(list(set(titles))) # Unique and sorted

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

def load_keymap_from_file(filename):
    try:
        with open(filename, 'r') as f:
            return {int(k): v for k, v in json.load(f).items()}
    except (FileNotFoundError, json.JSONDecodeError):
        return create_default_88_key_map()

def save_keymap_to_file(filename, key_map):
    try:
        with open(filename, 'w') as f:
            json.dump(key_map, f, indent=4, sort_keys=True)
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

        self.title("MIDI Keybind Pro")
        self.geometry("500x750")
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
        self.use_target_window = tk.BooleanVar(value=False)
        self.target_window_title = tk.StringVar(value="")

        self.current_filename = DEFAULT_FILENAME
        self.key_map = load_keymap_from_file(self.current_filename)

        # --- UI Construction ---
        self.main_container = ctk.CTkScrollableFrame(self, fg_color=COLOR_BG, corner_radius=0)
        self.main_container.grid(row=0, column=0, sticky="nsew")
        self.main_container.grid_columnconfigure(0, weight=1)

        # 1. Header
        self.build_header()

        # 2. Status Bar (Prominent)
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

    def build_header(self):
        header = ctk.CTkFrame(self.main_container, fg_color="transparent")
        header.grid(row=0, column=0, pady=(20, 10), sticky="ew")
        ctk.CTkLabel(header, text="MIDI Keybind Pro", font=ctk.CTkFont(family="Roboto Medium", size=24)).pack()
        ctk.CTkLabel(header, text="Universal MIDI Input Translator", font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_SUB).pack()

    def build_status_card(self):
        self.status_card = ctk.CTkFrame(self.main_container, fg_color=COLOR_CARD, corner_radius=15)
        self.status_card.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.status_card.grid_columnconfigure(1, weight=1)

        # Icon
        self.status_indicator = ctk.CTkButton(self.status_card, text="", width=15, height=15, corner_radius=10, fg_color=COLOR_DANGER, hover=False, state="disabled")
        self.status_indicator.grid(row=0, column=0, padx=(20, 15), pady=25)

        # Text Container
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

        # Title
        ctk.CTkLabel(card, text="CONFIGURATION", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_SUB).grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")

        # Profile Manager
        prof_frame = ctk.CTkFrame(card, fg_color="transparent")
        prof_frame.grid(row=1, column=0, padx=20, pady=5, sticky="ew")

        self.profile_lbl = ctk.CTkLabel(prof_frame, text=self.current_filename, font=ctk.CTkFont(family="Consolas", size=12))
        self.profile_lbl.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(prof_frame, text="Load", width=60, height=25, fg_color="#444", command=self.load_profile_dialog).pack(side="right", padx=2)
        ctk.CTkButton(prof_frame, text="Save", width=60, height=25, fg_color="#444", command=self.save_profile_as_dialog).pack(side="right", padx=2)
        ctk.CTkButton(prof_frame, text="Edit Map", width=80, height=25, fg_color="#555", command=self.open_editor).pack(side="right", padx=10)

        # Fallback Switch
        self.fallback_switch = ctk.CTkSwitch(card, text="Smart Octave Fallback", variable=self.fallback_var, button_color=COLOR_ACCENT, progress_color=COLOR_ACCENT)
        self.fallback_switch.grid(row=2, column=0, padx=20, pady=10, sticky="w")

        # Target Window Section
        target_frame = ctk.CTkFrame(card, fg_color="transparent")
        target_frame.grid(row=3, column=0, padx=20, pady=(5, 15), sticky="ew")

        self.target_switch = ctk.CTkSwitch(target_frame, text="Focus Protection", variable=self.use_target_window, button_color=COLOR_ACCENT, progress_color=COLOR_ACCENT)
        self.target_switch.pack(side="left")

        # Refresh Windows Button
        ctk.CTkButton(target_frame, text="↻", width=30, height=25, command=self.populate_window_list, fg_color="#444").pack(side="right")

        # Window Dropdown
        self.window_dropdown = ctk.CTkOptionMenu(target_frame, variable=self.target_window_title, dynamic_resizing=False, width=150)
        self.window_dropdown.pack(side="right", padx=5, fill="x", expand=True)
        self.window_dropdown.set("Select Window")

    def build_live_card(self):
        card = ctk.CTkFrame(self.main_container, fg_color=COLOR_CARD, corner_radius=15)
        card.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        # Header
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 5))
        ctk.CTkLabel(head, text="LIVE INPUT", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_SUB).pack(side="left")

        # Live Indicator
        self.live_dot = ctk.CTkLabel(head, text="●", font=ctk.CTkFont(size=16), text_color="gray")
        self.live_dot.pack(side="right")

        # Device Selector
        self.device_var = ctk.StringVar(value="Select Device...")
        self.device_menu = ctk.CTkOptionMenu(card, variable=self.device_var, command=self.on_device_select, fg_color="#444", button_color="#555", button_hover_color="#666")
        self.device_menu.grid(row=1, column=0, padx=20, pady=(5, 10), sticky="ew")

        # Stop Button (Hidden by default, shown when running)
        self.stop_live_btn = ctk.CTkButton(card, text="Stop Live Input", command=self.stop_live, fg_color=COLOR_DANGER, state="disabled")
        self.stop_live_btn.grid(row=2, column=0, padx=20, pady=(0, 15), sticky="ew")

    def build_file_card(self):
        card = ctk.CTkFrame(self.main_container, fg_color=COLOR_CARD, corner_radius=15)
        card.grid(row=4, column=0, padx=20, pady=10, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card, text="MIDI FILE PLAYER", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_SUB).grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")

        # File Select
        file_frame = ctk.CTkFrame(card, fg_color="transparent")
        file_frame.grid(row=1, column=0, padx=20, pady=5, sticky="ew")

        self.file_lbl = ctk.CTkLabel(file_frame, text="No file selected", text_color="gray")
        self.file_lbl.pack(side="left", fill="x", expand=True, anchor="w")
        ctk.CTkButton(file_frame, text="Select", width=60, command=self.select_file, fg_color="#444").pack(side="right")

        # Controls
        ctrl_frame = ctk.CTkFrame(card, fg_color="transparent")
        ctrl_frame.grid(row=2, column=0, padx=20, pady=(10, 15), sticky="ew")
        ctrl_frame.grid_columnconfigure((0,1,2), weight=1)

        self.btn_play = ctk.CTkButton(ctrl_frame, text="▶ Play", command=self.start_file, fg_color=COLOR_SUCCESS, state="disabled")
        self.btn_play.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.btn_pause = ctk.CTkButton(ctrl_frame, text="⏸ Pause", command=self.pause_file, fg_color=COLOR_WARN, text_color="black", state="disabled")
        self.btn_pause.grid(row=0, column=1, padx=5, sticky="ew")

        self.btn_stop = ctk.CTkButton(ctrl_frame, text="⏹ Stop", command=self.stop_file, fg_color=COLOR_DANGER, state="disabled")
        self.btn_stop.grid(row=0, column=2, padx=(5, 0), sticky="ew")

    def build_footer(self):
        footer = ctk.CTkFrame(self, height=40, fg_color=COLOR_BG)
        footer.grid(row=1, column=0, sticky="ew")
        self.pin_check = ctk.CTkCheckBox(footer, text="Always on Top", variable=self.pin_var, command=self.toggle_pin, font=ctk.CTkFont(size=12), checkmark_color=COLOR_BG, fg_color=COLOR_TEXT_SUB)
        self.pin_check.pack(side="left", padx=20, pady=10)

    # --- Logic ---

    # 1. Window List Logic
    def populate_window_list(self):
        wins = get_open_windows()
        if wins:
            self.window_dropdown.configure(values=wins)
        else:
            self.window_dropdown.configure(values=["No Windows Found"])

    # 2. MIDI Device & Auto-Start
    def populate_midi_devices(self):
        try:
            devices = mido.get_input_names()
            if devices:
                self.device_menu.configure(values=devices)
                self.device_var.set("Select Device...")
            else:
                self.device_menu.configure(values=["No Device Found"])
                self.device_var.set("No Device Found")
        except:
            self.device_menu.configure(values=["Error"])

    def on_device_select(self, choice):
        if choice in ["No Device Found", "Error", "Select Device..."]: return
        # Auto-Start logic
        if self.live_running:
            self.stop_live() # Restart if changing device

        self.start_live(choice)

    # 3. Status Updates
    def update_status_ui(self, main_text, sub_text, color):
        self.status_indicator.configure(fg_color=color)
        self.status_main.configure(text=main_text)
        self.status_sub.configure(text=sub_text)

    # 4. Live Input Control
    def start_live(self, device_name):
        self.live_running = True
        self.live_thread = threading.Thread(target=self.live_loop, args=(device_name,), daemon=True)
        self.live_thread.start()

        self.stop_live_btn.configure(state="normal")
        self.device_menu.configure(state="disabled")
        self.live_dot.configure(text_color=COLOR_SUCCESS)
        self.update_status_ui("Live Active", f"Input: {device_name}", COLOR_SUCCESS)

    def stop_live(self):
        self.live_running = False
        self.stop_live_btn.configure(state="disabled")
        self.device_menu.configure(state="normal")
        self.live_dot.configure(text_color="gray")

        # Reset UI status depending on file player state
        if self.file_playing:
            self.update_status_ui("Playing File", "Live input stopped", COLOR_ACCENT)
        else:
            self.update_status_ui("Ready", "Live input stopped", "gray")

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

    # 5. File Player Control
    def select_file(self):
        f = filedialog.askopenfilename(filetypes=[("MIDI", "*.mid *.midi")])
        if f:
            self.current_midi_file = f
            self.file_lbl.configure(text=os.path.basename(f))
            self.btn_play.configure(state="normal")

    def start_file(self):
        if not hasattr(self, 'current_midi_file'): return
        if self.file_playing and self.file_paused:
            # Resume
            self.file_paused = False
            self.btn_pause.configure(text="⏸ Pause", fg_color=COLOR_WARN)
            self.update_status_ui("Playing File", os.path.basename(self.current_midi_file), COLOR_ACCENT)
            return

        # New Start
        self.file_playing = True
        self.file_paused = False
        self.file_thread = threading.Thread(target=self.file_loop, args=(self.current_midi_file,), daemon=True)
        self.file_thread.start()

        self.btn_play.configure(state="disabled")
        self.btn_pause.configure(state="normal", text="⏸ Pause", fg_color=COLOR_WARN)
        self.btn_stop.configure(state="normal")
        self.update_status_ui("Playing File", os.path.basename(self.current_midi_file), COLOR_ACCENT)

    def pause_file(self):
        self.file_paused = not self.file_paused
        if self.file_paused:
            self.btn_pause.configure(text="▶ Resume", fg_color=COLOR_SUCCESS)
            self.update_status_ui("Paused", "File playback paused", COLOR_WARN)
        else:
            self.btn_pause.configure(text="⏸ Pause", fg_color=COLOR_WARN)
            self.update_status_ui("Playing File", os.path.basename(self.current_midi_file), COLOR_ACCENT)

    def stop_file(self):
        self.file_playing = False
        self.file_paused = False
        self.btn_play.configure(state="normal")
        self.btn_pause.configure(state="disabled", text="⏸ Pause", fg_color=COLOR_WARN)
        self.btn_stop.configure(state="disabled")

        if self.live_running:
            self.update_status_ui("Live Active", "File playback stopped", COLOR_SUCCESS)
        else:
            self.update_status_ui("Ready", "Playback stopped", "gray")

    def file_loop(self, filepath):
        try:
            mid = mido.MidiFile(filepath)
            for msg in mid.play():
                if not self.file_playing: break

                # Handle Pause
                while self.file_paused and self.file_playing:
                    time.sleep(0.1)

                if not self.check_can_press(): continue
                self.process_msg(msg)
        except Exception as e:
            print(f"File Error: {e}")
        finally:
            # Auto-stop when done
            self.after(0, self.stop_file)

    # 6. Shared Logic
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
    def load_profile_dialog(self):
        f = filedialog.askopenfilename(filetypes=[("JSON", "*.json")], initialdir=os.getcwd())
        if f:
            self.current_filename = f
            self.key_map = load_keymap_from_file(f)
            self.profile_lbl.configure(text=os.path.basename(f))

    def save_profile_as_dialog(self):
        f = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")], initialdir=os.getcwd())
        if f:
            self.current_filename = f
            save_keymap_to_file(f, self.key_map)
            self.profile_lbl.configure(text=os.path.basename(f))

    def open_editor(self):
        SleekEditor(self, self.key_map, self.update_key_map)

    def update_key_map(self, new_map):
        self.key_map = new_map
        save_keymap_to_file(self.current_filename, self.key_map)

# --- Sleek Editor Class (Same as before) ---
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
        style.map('Treeview', background=[('selected', COLOR_ACCENT)])
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

        ctk.CTkButton(action_frame, text="Save Changes", command=self.save, fg_color=COLOR_SUCCESS, hover_color="#229C68").pack(side="left", padx=5)
        ctk.CTkButton(action_frame, text="Cancel", command=self.destroy, fg_color="transparent", border_width=1, text_color="gray").pack(side="left", padx=5)
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
        self.lbl = ctk.CTkLabel(self, text="...", font=ctk.CTkFont(size=24, weight="bold"), text_color=COLOR_ACCENT)
        self.lbl.pack(pady=10)
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(side="bottom", pady=20)
        ctk.CTkButton(btn_frame, text="Clear", width=60, fg_color="#444", command=self.do_clear).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Unbind", width=60, fg_color=COLOR_DANGER, command=self.do_unbind).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Save", width=60, fg_color=COLOR_SUCCESS, command=self.do_save).pack(side="left", padx=5)
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