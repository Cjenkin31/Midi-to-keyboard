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
