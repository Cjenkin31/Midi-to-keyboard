# Bundling this into an application
```
pyinstaller --noconsole --onefile --name="MidiKeybindPro" --icon="icon.ico" --add-data="icon.ico;." --add-data="*.json;." --collect-all customtkinter main.py
```
