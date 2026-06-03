# Proposed Plan v1: Local Arabic Selection Translator

## Goal

Build a local Python script that lets me select Arabic text in VS Code, press a hotkey, and see a concise English translation in a small popup.

This is for personal use only. The implementation should stay simple and follow `iterations/coding_agent.md`.

## Environment Variables

Use the existing `.env` file and require these variables:

- `OPENAI_MODEL`
- `OPENAI_API_KEY`
- `OPENAI_API_BASE`

The script should load `.env` at startup. If any variable is missing or empty, let the script fail loudly with a clear exception.

Recommended value for cost control:

```env
OPENAI_MODEL=gpt-5.4-nano
```

If translation quality is too weak, manually change it to:

```env
OPENAI_MODEL=gpt-5.4-mini
```

## Implementation

Create one Python script at the repo root:

```text
arabic_translate_popup.py
```

Use these dependencies:

- `openai`
- `python-dotenv`
- `pyperclip`
- `pynput`
- `tkinter`

Behavior:

- Start the script from terminal with `python3 arabic_translate_popup.py`.
- Keep it running while reading in VS Code.
- Select Arabic text.
- Press `ctrl+option+a`.
- The script copies the current selection, sends it to OpenAI, and shows the translation in a small always-on-top popup near the mouse pointer.
- Press `escape` to close the popup.
- Cache translations in memory by exact selected text, so repeated selections do not call the API again during the same run.

OpenAI request:

- Use the Responses API through the Python SDK.
- Configure the client with:
  - API key from `OPENAI_API_KEY`
  - base URL from `OPENAI_API_BASE`
- Use model from `OPENAI_MODEL`.
- Use a short instruction:

```text
Translate the Arabic text into concise natural English. Preserve names, URLs, IDs, and numbers. Return only the translation.
```

Cost controls:

- Only call the API when the hotkey is pressed.
- Do not implement automatic hover translation.
- Keep the prompt short.
- Ask for concise output only.
- Cache exact repeated selections in memory.

## Coding Rules To Follow

Follow `iterations/coding_agent.md`:

- Keep the code simple and experimental.
- Do not add extensive error handling.
- Let errors fail loudly.
- Do not add fallbacks.
- Do not create functions for logic used only once.
- Use simple loops instead of dense comprehensions.
- Add concise comments for each function and method.
- Do not add default values for function parameters.

Practical interpretation:

- Functions are acceptable for repeated behavior such as loading config, translating text, and showing a popup.
- One-off startup wiring should stay in the main script body.
- No retry system, no alternate model fallback, no silent clipboard fallback.

## Verification

Manual checks:

- Run with a valid `.env` and confirm the script starts.
- Run with an empty env value and confirm it fails loudly.
- Select a single Arabic word in VS Code and press `ctrl+option+a`.
- Select a full Arabic sentence and press `ctrl+option+a`.
- Repeat the same selection and confirm it uses cached translation.
- Confirm the popup closes with `escape`.

## Out Of Scope

- VS Code extension.
- Browser extension.
- Automatic hover translation.
- Word-by-word morphology.
- Production-level validation, retries, logging, packaging, or deployment.
