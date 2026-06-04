# Arabic Hover

Arabic Hover is a small macOS translation helper. Press a shortcut, select text in any app, and an always-on-top box shows the translation. The app now works with multiple language pairs, not only Arabic.

## What It Does

- Press `ctrl+option+a` to turn translation mode on or off.
- Select text with the mouse or trackpad while translation mode is active.
- The selected text is translated with the OpenAI Responses API.
- The translation appears in a small bottom-center box.
- Use `Copy` to copy the current translation.
- Use the settings button to choose source and target languages.
- Use `History` to view recent translations stored on this Mac.

The default language pair is `Auto-detect -> English`.

## Setup

Create and activate a Python 3.13 environment:

```bash
python3 -V
python3 -m venv .venv
source .venv/bin/activate
```

This app depends on macOS keyboard and mouse listener packages. Use Python 3.13
rather than Python 3.14 until the `pynput`/PyObjC macOS stack is stable there.

Install dependencies:

```bash
pip install -r requirements.txt
```

Create your local environment file:

```bash
cp .env.example .env
```

Fill in `.env`:

```bash
OPENAI_MODEL=gpt-4.1-mini
OPENAI_API_KEY=your_api_key_here
OPENAI_API_BASE=https://api.openai.com/v1
```

Run the app:

```bash
python main.py
```

You can smoke-test the macOS listener dependency before running the full app:

```bash
python -c "from pynput import keyboard; import time; listener = keyboard.Listener(on_press=lambda key: None); listener.start(); time.sleep(0.5); print('listener alive:', listener.is_alive()); listener.stop()"
```

## macOS Permissions

The app copies selected text by sending `cmd+c`, and it listens for a global shortcut and mouse release. macOS may ask for Accessibility or Input Monitoring permissions for your terminal app.

If the app exits with a listener startup message, or if the shortcut or text
selection does not work, check:

- System Settings -> Privacy & Security -> Accessibility
- System Settings -> Privacy & Security -> Input Monitoring

Add Terminal, iTerm, VS Code, or whichever app is running `python main.py`.
Restart that app after changing permissions.

If you see `KeyError: 'AXIsProcessTrusted'`, recreate the environment with
Python 3.13 and reinstall the pinned dependencies:

```bash
deactivate
rm -rf .venv
python3 -V
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Language Settings

Open the settings button in the translator box to choose:

- Source: `Auto-detect`, `Arabic`, `English`, `Urdu`, `French`, `Spanish`, `Turkish`, `Persian`, `German`, `Chinese`
- Target: `Arabic`, `English`, `Urdu`, `French`, `Spanish`, `Turkish`, `Persian`, `German`, `Chinese`

`Auto-detect` is available only for the source language.

## Local History

Translation history is stored locally at:

```text
~/.arabic_hover/history.json
```

Each entry stores the selected source text, translation, source language, target language, timestamp, and model. The app keeps the most recent 100 translations.

Delete `~/.arabic_hover/history.json` to clear local history.

## Security

Do not commit `.env`. Use `.env.example` for placeholders and keep real keys only in your local `.env` file.

If a real API key was committed, rotate or revoke that key before making the repository public.
