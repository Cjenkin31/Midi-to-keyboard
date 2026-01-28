import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox
import copy
import threading
import time
try:
    import keyboard
except ImportError:
    keyboard = None

from constants import *
from utils import *


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
                metadata = {"name": name, "linked_window": link, "hotkeys": {"play_pause": "f9", "stop": "f10"}}
            else:
                filename = profile_data["filename"]
                mappings, metadata = load_profile_data(filename)
                metadata["name"] = name
                metadata["linked_window"] = link

            save_profile_data(filename, mappings, metadata)
            self.refresh_callback() # Refresh parent cache
            self.profiles = self.parent.profile_cache # Update local list
            self.populate_list()
            dialog.destroy()

        ctk.CTkButton(dialog, text="Save", command=save, fg_color=COLOR_LIVE_GO).pack(pady=20)


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
        self.geometry("350x380")
        self.callback = callback
        self.attributes("-topmost", True)
        self.hotkeys = current_hotkeys.copy()
        self.capturing = False
        
        self.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self, text="Global Media Controls", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(20, 15))
        
        self.btn_pp = self.create_row("Play / Pause", "play_pause")
        self.btn_stop = self.create_row("Stop Playback", "stop")
        self.btn_t_up = self.create_row("Transpose Up", "transpose_up")
        self.btn_t_down = self.create_row("Transpose Down", "transpose_down")
        
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
        
        btn = None
        if key_key == "play_pause": btn = self.btn_pp
        elif key_key == "stop": btn = self.btn_stop
        elif key_key == "transpose_up": btn = self.btn_t_up
        elif key_key == "transpose_down": btn = self.btn_t_down
        
        if btn:
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
