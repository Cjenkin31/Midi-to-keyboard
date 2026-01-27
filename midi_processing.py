import mido
import time
import random
import pydirectinput

def live_loop(app, device):
    try:
        with mido.open_input(device) as port:
            while app.live_running:
                for msg in port.iter_pending():
                    if not app.check_can_press(): continue
                    app.process_msg(msg, source='live')
                time.sleep(0.001)
    except Exception as e:
        print(f"Live Error: {e}")
        app.live_running = False
        app.after(0, app.stop_live)

def file_loop(app, filepath):
    try:
        app.log("File loop running")
        mid = mido.MidiFile(filepath)
        # Iterate over messages to manually control timing for speed modification
        for msg in mid:
            if not app.file_playing: break
            
            # Check pause before waiting
            while app.file_paused and app.file_playing:
                time.sleep(0.1)
            
            # Manually sleep based on message time and speed modifier
            if msg.time > 0:
                wait_duration = msg.time / app.safe_speed
                start_time = time.time()
                
                while True:
                    now = time.time()
                    elapsed = now - start_time
                    remaining = wait_duration - elapsed
                    
                    if remaining <= 0: break
                    if not app.file_playing: break
                    
                    if app.file_paused:
                        while app.file_paused and app.file_playing:
                            time.sleep(0.1)
                        start_time = time.time()
                        wait_duration = remaining
                        continue
                    
                    time.sleep(min(0.01, remaining))

            if not app.file_playing: break # Check again in case stop was pressed during sleep

            if not app.check_can_press(): continue
            app.process_msg(msg, source='file')
    except Exception as e:
        app.log(f"File Error: {e}")
        print(f"File Error: {e}")
    finally:
        app.log("File loop finished")
        app.after(0, app.stop_file)

def release_all_held_keys(app):
    with app.key_lock:
        if not app.held_keys: return
        keys_to_release = list(app.held_keys)
        app.held_keys.clear()
        app.log(f"Releasing keys: {keys_to_release}")
        
    for k in keys_to_release:
        pydirectinput.keyUp(k)
    app.after(0, lambda: app.update_note_ui(None, False))
