import ctypes
import json
import os
import sys
import pydirectinput
from tkinter import messagebox

# --- Windows API Helpers ---
user32 = ctypes.windll.user32

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
        21: "a", 22: "w", 23: "s", 24: "d", 25: "e", 26: "f", 27: "t", 28: "g", 29: "y", 30: "h", 31: "u", 32: "j", 33: "i", 34: "k", 35: "o", 36: "l", 37: "p", 38: ";", 39: "'", 40: "z", 41: "x", 42: "c", 43: "v", 44: "b", 45: "n", 46: "m", 47: ",", 48: ".", 49: "/", 50: "space", 51: "enter", 52: "up", 53: "down", 54: "left", 55: "right", 56: "shift", 57: "ctrl", 58: "alt", 59: "tab", 60: "esc", 61: "1", 62: "2", 63: "3", 64: "4", 65: "5", 66: "6", 71: "7", 72: "8", 73: "9", 74: "0", 75: "q"
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
    default_meta = {"name": display_name, "linked_window": "", "hotkeys": {"play_pause": "f9", "stop": "f10", "transpose_up": "page up", "transpose_down": "page down"}}
    
    try:
        with open(target_path, 'r') as f:
            data = json.load(f)
            # Check for new format with metadata
            if "metadata" in data:
                meta = data["metadata"]
                if meta.get("name") == "Unnamed Profile":
                    meta["name"] = display_name
                if "hotkeys" not in meta:
                    meta["hotkeys"] = default_meta["hotkeys"]
                
                # Ensure new keys exist in old profiles
                for k, v in [("transpose_up", "page up"), ("transpose_down", "page down")]:
                    if k not in meta["hotkeys"]: meta["hotkeys"][k] = v
                
                mappings = {int(k): v for k, v in data["mappings"].items()} if "mappings" in data else create_default_88_key_map()
                return mappings, meta
            else:
                # Legacy format (just mappings)
                return {int(k): v for k, v in data.items()}, default_meta
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
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
    return key_map.get(closest_note)
