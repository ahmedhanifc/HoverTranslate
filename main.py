import json
import os
import queue
import sys
import time
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk

import pyperclip
from dotenv import load_dotenv
from openai import OpenAI
from pynput import keyboard
from pynput import mouse


HOTKEY = "<ctrl>+<alt>+a"
POPUP_WIDTH = 620
POPUP_BOTTOM_MARGIN = 70
MOUSE_DRAG_THRESHOLD = 4
HISTORY_LIMIT = 100
APP_DIR = Path.home() / ".arabic_hover"
HISTORY_PATH = APP_DIR / "history.json"
LANGUAGES = [
    "Auto-detect",
    "Arabic",
    "English",
    "Urdu",
    "French",
    "Spanish",
    "Turkish",
    "Persian",
    "German",
    "Chinese",
]
TARGET_LANGUAGES = [
    "Arabic",
    "English",
    "Urdu",
    "French",
    "Spanish",
    "Turkish",
    "Persian",
    "German",
    "Chinese",
]
INPUT_LISTENER_STARTUP_TIMEOUT = 0.35


def build_input_listener_error(listener_name, error=None):
    python_version = ".".join(str(part) for part in sys.version_info[:3])
    message = (
        "Arabic Hover could not start the macOS keyboard/mouse listeners.\n\n"
        "Use a Python 3.13 environment, reinstall requirements.txt, and grant "
        "Accessibility plus Input Monitoring permissions to the terminal or "
        "editor running python main.py.\n\n"
        f"Failed listener: {listener_name}\n"
        f"Python: {python_version}\n"
        "See README.md -> macOS Permissions for the full setup steps."
    )
    if error is not None:
        message += f"\nError: {error!r}"
    return message


def stop_input_listeners(listeners):
    for listener in listeners:
        try:
            if listener.is_alive():
                listener.stop()
        except RuntimeError:
            pass


def start_input_listeners(listener_specs):
    started_listeners = []
    for listener_name, listener in listener_specs:
        try:
            listener.start()
            started_listeners.append(listener)
            listener.join(INPUT_LISTENER_STARTUP_TIMEOUT)
        except Exception as error:
            stop_input_listeners(started_listeners)
            raise RuntimeError(
                build_input_listener_error(listener_name, error)
            ) from error

        if not listener.is_alive():
            stop_input_listeners(started_listeners)
            raise RuntimeError(build_input_listener_error(listener_name))

    return started_listeners


def require_env(name):
    """Return a required environment variable or fail loudly."""
    value = os.environ.get(name)
    if value is None:
        raise RuntimeError(f"{name} is required in .env")
    value = value.strip()
    if value == "":
        raise RuntimeError(f"{name} is empty in .env")
    return value


def build_translation_instructions(source_language, target_language):
    """Create the model instruction for the selected language pair."""
    if source_language == "Auto-detect":
        source_text = "the detected language"
    else:
        source_text = source_language

    return (
        f"Translate the selected text from {source_text} into {target_language}. "
        "Use concise natural language. Preserve names, URLs, IDs, and numbers. "
        "Return only the translation."
    )


def load_history():
    """Load local translation history from disk."""
    if not HISTORY_PATH.exists():
        return []

    with HISTORY_PATH.open("r", encoding="utf-8") as history_file:
        return json.load(history_file)


def save_history(entries):
    """Write local translation history to disk."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("w", encoding="utf-8") as history_file:
        json.dump(entries, history_file, ensure_ascii=False, indent=2)


def record_history(history_state, entry):
    """Save one translation and refresh the history window."""
    history_state["entries"].insert(0, entry)
    del history_state["entries"][HISTORY_LIMIT:]
    save_history(history_state["entries"])
    refresh_history_window(history_state)


def replace_text(text_widget, text):
    """Replace text widget contents without letting the user edit them."""
    text_widget.configure(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", text)
    text_widget.configure(state="disabled")


def copy_selected_text(keyboard_controller):
    """Copy selected text from the active app and restore the old clipboard."""
    old_clipboard = pyperclip.paste()
    pyperclip.copy("")

    keyboard_controller.press(keyboard.Key.cmd)
    keyboard_controller.press("c")
    keyboard_controller.release("c")
    keyboard_controller.release(keyboard.Key.cmd)

    time.sleep(0.15)
    selected_text = pyperclip.paste().strip()
    pyperclip.copy(old_clipboard)

    return selected_text


def translate_text(client, model, cache, selected_text, source_language, target_language):
    """Translate selected text, using an exact in-memory cache."""
    cache_key = (selected_text, source_language, target_language)
    if cache_key in cache:
        return cache[cache_key]

    response = client.responses.create(
        model=model,
        instructions=build_translation_instructions(source_language, target_language),
        input=selected_text,
        max_output_tokens=220,
        store=False,
    )

    translation = response.output_text.strip()
    cache[cache_key] = translation

    return translation


def mark_internal_click(app_state):
    """Ignore the next mouse release when it began inside this app."""
    app_state["ignore_next_mouse_release"] = True


def bind_internal_click(widget, app_state):
    """Mark clicks that start inside Tk windows."""
    widget.bind("<ButtonPress-1>", lambda event: mark_internal_click(app_state), add="+")


def build_language_status(settings_state):
    """Return compact display text for the active language pair."""
    return f"{settings_state['source_language']} -> {settings_state['target_language']}"


def hide_translator_box(root, popup_state):
    """Hide the translator box and clear its copied text."""
    root.withdraw()
    popup_state["current_text"] = ""
    replace_text(popup_state["text"], "")


def deactivate_translator(root, popup_state, app_state):
    """Deactivate translation mode and hide the translator box."""
    app_state["active"] = False
    hide_translator_box(root, popup_state)


def keep_translator_box_topmost(root):
    """Reassert that the translator box is above normal windows."""
    root.attributes("-topmost", True)
    root.lift()


def position_translator_box(root):
    """Position the translator box at the bottom center of the screen."""
    root.update_idletasks()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    popup_height = root.winfo_reqheight()
    popup_x = int((screen_width - POPUP_WIDTH) // 2)
    popup_y = int(screen_height - popup_height - POPUP_BOTTOM_MARGIN)
    root.geometry(f"{POPUP_WIDTH}x{popup_height}+{popup_x}+{popup_y}")


def update_popup_text(popup_state, text):
    """Update the visible translation text and keep the layout stable."""
    line_count = text.count("\n") + 1
    estimated_wrapped_lines = int(len(text) / 72) + 1
    text_height = max(2, min(8, line_count + estimated_wrapped_lines - 1))
    popup_state["current_text"] = text
    popup_state["text"].configure(height=text_height)
    replace_text(popup_state["text"], text)


def show_translator_box(root, popup_state, app_state, text):
    """Show or update the persistent translator box."""
    update_popup_text(popup_state, text)
    root.deiconify()
    keep_translator_box_topmost(root)
    position_translator_box(root)
    root.update_idletasks()


def apply_language_settings(settings_state, source_var, target_var):
    """Apply selected languages to future translations."""
    if target_var.get() == "Auto-detect":
        raise RuntimeError("Target language cannot be Auto-detect")

    settings_state["source_language"] = source_var.get()
    settings_state["target_language"] = target_var.get()
    if settings_state["language_label"] is not None:
        settings_state["language_label"].configure(text=build_language_status(settings_state))


def close_settings_window(settings_state):
    """Close the settings window and clear its state."""
    settings_state["window"].destroy()
    settings_state["window"] = None
    settings_state["language_label"] = None


def create_settings_window(root, settings_state, history_state, app_state):
    """Open the compact settings window for language selection."""
    if settings_state["window"] is not None:
        settings_state["window"].lift()
        return

    settings_window = tk.Toplevel(root)
    settings_window.title("Settings")
    settings_window.resizable(False, False)
    settings_window.attributes("-topmost", True)
    settings_window.configure(bg="#f6f4ea", padx=14, pady=14)

    source_var = tk.StringVar(value=settings_state["source_language"])
    target_var = tk.StringVar(value=settings_state["target_language"])

    language_status = tk.Label(
        settings_window,
        text=build_language_status(settings_state),
        bg="#f6f4ea",
        fg="#333333",
        anchor="w",
        font=("Arial", 12),
    )
    source_label = tk.Label(settings_window, text="From", bg="#f6f4ea", anchor="w")
    source_combo = ttk.Combobox(
        settings_window,
        values=LANGUAGES,
        textvariable=source_var,
        state="readonly",
        width=22,
    )
    target_label = tk.Label(settings_window, text="To", bg="#f6f4ea", anchor="w")
    target_combo = ttk.Combobox(
        settings_window,
        values=TARGET_LANGUAGES,
        textvariable=target_var,
        state="readonly",
        width=22,
    )
    apply_button = tk.Button(
        settings_window,
        text="Apply",
        command=lambda: apply_language_settings(
            settings_state,
            source_var,
            target_var,
        ),
    )
    history_button = tk.Button(
        settings_window,
        text="History",
        command=lambda: create_history_window(root, history_state, app_state),
    )

    language_status.grid(row=0, column=0, sticky="ew", pady=(0, 12))
    source_label.grid(row=1, column=0, sticky="w", pady=(0, 4))
    source_combo.grid(row=2, column=0, sticky="ew", pady=(0, 12))
    target_label.grid(row=3, column=0, sticky="w", pady=(0, 4))
    target_combo.grid(row=4, column=0, sticky="ew", pady=(0, 12))
    apply_button.grid(row=5, column=0, sticky="ew", pady=(0, 8))
    history_button.grid(row=6, column=0, sticky="ew")

    for widget in [
        settings_window,
        language_status,
        source_label,
        source_combo,
        target_label,
        target_combo,
        apply_button,
        history_button,
    ]:
        bind_internal_click(widget, app_state)

    settings_state["window"] = settings_window
    settings_state["language_label"] = language_status
    settings_window.protocol("WM_DELETE_WINDOW", lambda: close_settings_window(settings_state))


def format_history_list_item(entry):
    """Return one compact history list label."""
    timestamp = entry["timestamp"].replace("T", " ")[:16]
    source_language = entry["source_language"]
    target_language = entry["target_language"]
    return f"{timestamp}  {source_language} -> {target_language}"


def show_history_entry(history_state, index):
    """Show the selected history entry details."""
    entry = history_state["entries"][index]
    replace_text(history_state["source_text"], entry["source_text"])
    replace_text(history_state["translation_text"], entry["translation"])


def handle_history_selection(event, history_state):
    """Update history detail panes from the selected list item."""
    selection = history_state["listbox"].curselection()
    if len(selection) == 0:
        return

    show_history_entry(history_state, selection[0])


def copy_history_translation(history_state):
    """Copy the selected history translation."""
    selection = history_state["listbox"].curselection()
    if len(selection) == 0:
        return

    entry = history_state["entries"][selection[0]]
    pyperclip.copy(entry["translation"])


def refresh_history_window(history_state):
    """Refresh the history window if it is open."""
    if history_state["listbox"] is None:
        return

    history_state["listbox"].delete(0, tk.END)
    for entry in history_state["entries"]:
        history_state["listbox"].insert(tk.END, format_history_list_item(entry))

    if len(history_state["entries"]) > 0:
        history_state["listbox"].selection_set(0)
        show_history_entry(history_state, 0)


def close_history_window(history_state):
    """Close the history window and clear widget references."""
    history_state["window"].destroy()
    history_state["window"] = None
    history_state["listbox"] = None
    history_state["source_text"] = None
    history_state["translation_text"] = None


def create_history_window(root, history_state, app_state):
    """Open the local translation history window."""
    if history_state["window"] is not None:
        history_state["window"].lift()
        return

    history_window = tk.Toplevel(root)
    history_window.title("History")
    history_window.geometry("760x420")
    history_window.attributes("-topmost", True)
    history_window.configure(bg="#f6f4ea", padx=12, pady=12)

    list_frame = tk.Frame(history_window, bg="#f6f4ea")
    detail_frame = tk.Frame(history_window, bg="#f6f4ea")
    listbox = tk.Listbox(list_frame, width=32, exportselection=False)
    source_label = tk.Label(detail_frame, text="Source", bg="#f6f4ea", anchor="w")
    source_text = tk.Text(
        detail_frame,
        height=6,
        wrap="word",
        bg="#fffef7",
        fg="#111111",
        padx=8,
        pady=8,
        relief="solid",
        borderwidth=1,
        font=("Arial", 13),
    )
    translation_label = tk.Label(detail_frame, text="Translation", bg="#f6f4ea", anchor="w")
    translation_text = tk.Text(
        detail_frame,
        height=8,
        wrap="word",
        bg="#fffef7",
        fg="#111111",
        padx=8,
        pady=8,
        relief="solid",
        # borderwidth=1,
        font=("Arial", 13),
    )
    copy_button = tk.Button(
        detail_frame,
        text="Copy Translation",
        command=lambda: copy_history_translation(history_state),
    )

    list_frame.pack(side="left", fill="y", padx=(0, 12))
    detail_frame.pack(side="left", fill="both", expand=True)
    listbox.pack(fill="both", expand=True)
    source_label.pack(fill="x")
    source_text.pack(fill="both", expand=True, pady=(4, 10))
    translation_label.pack(fill="x")
    translation_text.pack(fill="both", expand=True, pady=(4, 10))
    copy_button.pack(anchor="e")

    history_state["window"] = history_window
    history_state["listbox"] = listbox
    history_state["source_text"] = source_text
    history_state["translation_text"] = translation_text

    listbox.bind("<<ListboxSelect>>", lambda event: handle_history_selection(event, history_state))
    for widget in [
        history_window,
        list_frame,
        detail_frame,
        listbox,
        source_label,
        source_text,
        translation_label,
        translation_text,
        copy_button,
    ]:
        bind_internal_click(widget, app_state)

    refresh_history_window(history_state)
    history_window.protocol("WM_DELETE_WINDOW", lambda: close_history_window(history_state))


def create_translator_box(root, popup_state, settings_state, history_state, app_state):
    """Create the persistent always-on-top translator box."""
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg="#fffef7")

    container = tk.Frame(root, bg="#fffef7")
    settings_button = tk.Label(
        container,
        text="⚙",
        bg="#fffef7",
        fg="#000000",
        padx=0,
        pady=0,
        cursor="hand2",
        font=("Arial", 15, "bold"),
    )
    text_area = tk.Text(
        container,
        bg="#fffef7",
        fg="#111111",
        padx=14,
        pady=10,
        wrap="word",
        font=("Arial", 15),
        height=2,
        relief="flat",
        borderwidth=0,
        highlightthickness=0,
        insertborderwidth=0,
    )

    container.pack(fill="both", expand=True)
    text_area.pack(fill="both", expand=True, padx=14, pady=12)
    settings_button.place(relx=1.0, x=-10, y=8, anchor="ne")
    settings_button.lift()

    popup_state["text"] = text_area

    replace_text(text_area, "")
    root.bind("<Escape>", lambda event: deactivate_translator(root, popup_state, app_state))
    text_area.bind("<Escape>", lambda event: deactivate_translator(root, popup_state, app_state))
    settings_button.bind(
        "<ButtonRelease-1>",
        lambda event: create_settings_window(
            root,
            settings_state,
            history_state,
            app_state,
        ),
    )

    for widget in [
        root,
        container,
        settings_button,
        text_area,
    ]:
        bind_internal_click(widget, app_state)


def activate_translator(root, popup_state, app_state):
    """Activate translation mode and show the idle translator box."""
    app_state["active"] = True
    app_state["last_request"] = None
    show_translator_box(root, popup_state, app_state, "Translator active")


def toggle_translator(root, popup_state, app_state):
    """Toggle translation mode on or off."""
    if app_state["active"]:
        deactivate_translator(root, popup_state, app_state)
    else:
        activate_translator(root, popup_state, app_state)


def build_history_entry(selected_text, translation, source_language, target_language, model):
    """Build one serializable history record."""
    return {
        "source_text": selected_text,
        "translation": translation,
        "source_language": source_language,
        "target_language": target_language,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
    }


def handle_selection_finished(
    client,
    model,
    cache,
    root,
    popup_state,
    app_state,
    settings_state,
    history_state,
    keyboard_controller,
):
    """Copy the settled selection, translate it, and update the fixed box."""
    time.sleep(0.2)
    selected_text = copy_selected_text(keyboard_controller)
    if selected_text == "":
        return

    source_language = settings_state["source_language"]
    target_language = settings_state["target_language"]
    request_key = (selected_text, source_language, target_language)
    if request_key == app_state["last_request"]:
        return

    show_translator_box(root, popup_state, app_state, "Translating...")
    translation = translate_text(
        client,
        model,
        cache,
        selected_text,
        source_language,
        target_language,
    )
    app_state["last_request"] = request_key
    show_translator_box(root, popup_state, app_state, translation)
    record_history(
        history_state,
        build_history_entry(
            selected_text,
            translation,
            source_language,
            target_language,
            model,
        ),
    )


def is_shift_key(key):
    """Return whether a pynput key is either Shift key."""
    return key in {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r}


def handle_mouse_click(x, y, button, pressed, app_state, event_queue):
    """Queue selection handling after drag or Shift-click selection."""
    if button != mouse.Button.left:
        return
    if pressed:
        app_state["mouse_down_x"] = x
        app_state["mouse_down_y"] = y
        return
    if app_state["ignore_next_mouse_release"]:
        app_state["ignore_next_mouse_release"] = False
        return

    drag_x = abs(x - app_state["mouse_down_x"])
    drag_y = abs(y - app_state["mouse_down_y"])
    dragged_enough = drag_x > MOUSE_DRAG_THRESHOLD or drag_y > MOUSE_DRAG_THRESHOLD
    selection_gesture = dragged_enough or app_state["shift_pressed"]
    if app_state["active"] and selection_gesture:
        event_queue.put("selection_finished")


def handle_key_press(key, app_state, event_queue):
    """Track Shift and queue deactivation when escape is pressed while active."""
    if is_shift_key(key):
        app_state["shift_pressed"] = True
    if key == keyboard.Key.esc and app_state["active"]:
        event_queue.put("deactivate")


def handle_key_release(key, app_state):
    """Track when Shift is no longer held."""
    if is_shift_key(key):
        app_state["shift_pressed"] = False


def poll_requests(
    client,
    model,
    cache,
    root,
    popup_state,
    app_state,
    settings_state,
    history_state,
    event_queue,
    keyboard_controller,
):
    """Process queued listener events from the Tk main thread."""
    while not event_queue.empty():
        event_name = event_queue.get()
        if event_name == "toggle_active":
            toggle_translator(root, popup_state, app_state)
        if event_name == "deactivate":
            deactivate_translator(root, popup_state, app_state)
        if event_name == "selection_finished" and app_state["active"]:
            handle_selection_finished(
                client,
                model,
                cache,
                root,
                popup_state,
                app_state,
                settings_state,
                history_state,
                keyboard_controller,
            )
    if app_state["active"]:
        keep_translator_box_topmost(root)

    root.after(
        100,
        poll_requests,
        client,
        model,
        cache,
        root,
        popup_state,
        app_state,
        settings_state,
        history_state,
        event_queue,
        keyboard_controller,
    )


load_dotenv()

openai_model = require_env("OPENAI_MODEL")
openai_api_key = require_env("OPENAI_API_KEY")
openai_api_base = require_env("OPENAI_API_BASE")

openai_client = OpenAI(api_key=openai_api_key, base_url=openai_api_base)
translation_cache = {}
requests = queue.Queue()
keyboard_controller = keyboard.Controller()

root = tk.Tk()
root.title("Translator")
root.withdraw()
popup_state = {"text": None, "current_text": ""}
settings_state = {
    "source_language": "Auto-detect",
    "target_language": "English",
    "window": None,
    "language_label": None,
}
history_state = {
    "entries": load_history(),
    "window": None,
    "listbox": None,
    "source_text": None,
    "translation_text": None,
}
app_state = {
    "active": False,
    "last_request": None,
    "mouse_down_x": 0,
    "mouse_down_y": 0,
    "shift_pressed": False,
    "ignore_next_mouse_release": False,
}
create_translator_box(root, popup_state, settings_state, history_state, app_state)

hotkey_listener = keyboard.GlobalHotKeys(
    {
        HOTKEY: lambda: requests.put("toggle_active"),
    }
)

key_listener = keyboard.Listener(
    on_press=lambda key: handle_key_press(key, app_state, requests),
    on_release=lambda key: handle_key_release(key, app_state),
)

mouse_listener = mouse.Listener(
    on_click=lambda x, y, button, pressed: handle_mouse_click(
        x,
        y,
        button,
        pressed,
        app_state,
        requests,
    )
)

try:
    start_input_listeners(
        [
            ("global hotkey", hotkey_listener),
            ("keyboard listener", key_listener),
            ("mouse listener", mouse_listener),
        ]
    )
except RuntimeError as error:
    root.destroy()
    print(error, file=sys.stderr)
    raise SystemExit(1) from error

print("Translator running.")
print("Press ctrl+option+a to toggle translation mode.")

root.after(
    100,
    poll_requests,
    openai_client,
    openai_model,
    translation_cache,
    root,
    popup_state,
    app_state,
    settings_state,
    history_state,
    requests,
    keyboard_controller,
)
root.mainloop()
