# Proposed Plan v2: Persistent Toggle Translator Box

## Summary

Change the translator from "press shortcut to translate once" into a toggle mode:

- Press `ctrl+option+a` to activate translation mode.
- A fixed always-on-top translator box appears at the bottom center of the screen.
- While active, releasing the mouse/trackpad after selecting text triggers translation automatically.
- Press `ctrl+option+a` again to deactivate translation mode and hide the box.
- Keep using `.env`: `OPENAI_MODEL`, `OPENAI_API_KEY`, `OPENAI_API_BASE`.

## Implementation Changes

- Update `main.py` only.
- Keep the existing OpenAI Responses API call:
  - `client.responses.create(...)`
  - `model=openai_model`
  - `instructions=TRANSLATION_INSTRUCTIONS`
  - `input=selected_text`
  - `max_output_tokens=220`
  - `store=False`
- Replace the one-shot hotkey behavior:
  - `ctrl+option+a` queues a `toggle_active` event.
  - When activated, create/show one persistent Tk window.
  - When deactivated, destroy the window.
- Add a global mouse listener:
  - On left mouse/trackpad release, if active, queue `selection_finished`.
  - The Tk polling loop handles the queued event on the main thread.
- On `selection_finished`:
  - Wait briefly for selection state to settle.
  - Copy the current selection with `cmd+c`.
  - Restore the previous clipboard.
  - If copied text is empty, do nothing.
  - If copied text matches the last translated selection, do nothing.
  - Otherwise show `Translating...`, call OpenAI, cache the result, and update the fixed box.
- Position the box bottom middle:
  - Use Tk screen width/height.
  - Set a stable width, e.g. `620px`.
  - Recalculate `x = (screen_width - popup_width) // 2`.
  - Place it near the bottom with a fixed margin, e.g. `screen_height - popup_height - 70`.
  - Use integer geometry values only.
- Keep coding style aligned with `iterations/coding_agent.md`:
  - Simple experimental code.
  - Fail loudly.
  - No fallbacks.
  - No extensive error handling.
  - Concise function comments.
  - No default function parameter values.

## UI Behavior

- Active idle text: `Translator active`
- During request: `Translating...`
- Translation result replaces the box contents.
- Clicking the box copies the translation to clipboard, preserving the current useful behavior.
- `escape` hides/deactivates the translator box.
- The box does not auto-close while active.

## Cost Controls

- No API call on activation.
- No API call for empty selection.
- No API call when the selected text is unchanged from the previous selection.
- Exact-text in-memory cache remains, so repeated text does not call the API again.
- No hover OCR, no background scanning, no polling selected text continuously.

## Test Plan

- Run `python3 -m py_compile main.py`.
- Run `python main.py`.
- Press `ctrl+option+a`; confirm the bottom-center box appears.
- Select one Arabic word with the trackpad and release; confirm it translates.
- Select a full Arabic sentence and release; confirm it translates.
- Click without selecting text; confirm no API call-visible change beyond staying active.
- Select the same text twice; confirm cached result is reused.
- Press `ctrl+option+a` again; confirm the box disappears and mouse releases no longer translate.
- Press `escape` while active; confirm it deactivates/hides the box.

## Assumptions

- Keep `ctrl+option+a` as the toggle shortcut.
- Only mouse/trackpad selection release triggers automatic translation.
- Keyboard-only selection will still require a mouse/trackpad release or a later enhancement.
- The implementation stays local and personal-use only.
