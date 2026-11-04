"""Create and reopen Scio chats using your own encrypted, saved login token.

Python 3.10+, no extra packages. Run: python scio_console.py
The message will be added to the selected chat.
"""

import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path
import getpass
import json
import os
import sys
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ENDPOINT = "https://www.sciobot.cz/functions/v1/ai-chat"
# Public browser application key, not a substitute for your login token.
API_KEY = "sb_publishable_S2qw4lKrXTkU8o1rN4EuSg_owDq1Sub"


def show_event(data):
    if data == "[DONE]":
        return
    try:
        event = json.loads(data)
    except json.JSONDecodeError:
        print(data, flush=True)
        return
    if not isinstance(event, dict):
        print(event, flush=True)
    elif event.get("type") == "text-delta":
        print(event.get("delta", event.get("textDelta", "")), end="", flush=True)
    elif event.get("type") == "error":
        print("\nServer error:", event.get("errorText", event), file=sys.stderr)


DIST_DIR = Path(__file__).resolve().parent.parent
if not (DIST_DIR / 'distribution.json').is_file(): DIST_DIR = None
DATA_DIR = Path(os.environ['SCIO_DATA_DIR']).expanduser().resolve() if os.environ.get('SCIO_DATA_DIR') else (
    Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'SCIO CODE' if DIST_DIR
    else Path(__file__).resolve().parent / 'scio_data')


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def protect(data, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Saved tokens require Windows. Use SCIO_TOKEN on other systems.")
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    dll = ctypes.WinDLL("crypt32", use_last_error=True)
    fn = dll.CryptUnprotectData if decrypt else dll.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        free = ctypes.WinDLL("kernel32").LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(target.data)


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def get_token(replace=False, interactive=True):
    path = DATA_DIR / "token.dpapi"
    if not replace:
        if os.environ.get("SCIO_TOKEN"):
            return os.environ["SCIO_TOKEN"].removeprefix("Bearer ").strip()
        if path.exists():
            return protect(path.read_bytes(), decrypt=True).decode()
    if not interactive:
        raise RuntimeError("No saved login. Run scio_console.py once to save your token.")
    token = getpass.getpass("Your Scio bearer token (hidden, saved encrypted): ").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise ValueError("Token cannot be empty.")
    encrypted = protect(token.encode())
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypted)
    return token


def make_request(token, payload):
    return Request(ENDPOINT, data=json.dumps(payload).encode(), method="POST", headers={
        "Authorization": "Bearer " + token, "apikey": API_KEY,
        "Content-Type": "application/json", "Accept": "text/event-stream, application/json",
    })


def create_chat(token, title, model="auto"):
    payload = {"command": {"type": "open-session", "scope": "general",
                          "title": title, "model": validate_model(model), "projectId": None, "enabledFeatures": {}}}
    with urlopen(make_request(token, payload), timeout=60) as response:
        result = json.load(response)
    if not isinstance(result, dict) or not result.get("id"):
        raise ValueError("Server returned an unexpected chat response; check Scio before retrying.")
    return {"id": str(uuid.UUID(result["id"])), "title": result.get("title") or title, "model": model}


def main():
    token = get_token()
    index = DATA_DIR / "chats.json"
    chats = read_json(index, [])
    model = read_json(DATA_DIR / "settings.json", {}).get("model", "auto")
    while True:
        print(f"\nDefault model: {model} | Saved chats:")
        for number, chat in enumerate(chats, 1):
            print(f"  {number}. {chat['title']} ({chat['id']})")
        choice = input("[M]odel | [N]ew chat | [A]dd existing | number | [T]oken replace | [F]orget token | [Q]uit: ").strip().lower()
        if choice == "q":
            return 0
        try:
            if choice == "m":
                model = choose_model(model)
                save_json(DATA_DIR / "settings.json", {"model": model})
                continue
            if choice == "t":
                token = get_token(replace=True)
                continue
            if choice == "f":
                (DATA_DIR / "token.dpapi").unlink(missing_ok=True)
                print("Saved token removed. Exiting.")
                return 0
            if choice == "n":
                title = input("New chat title: ").strip() or "Console chat"
                chat = create_chat(token, title, model)
                chats.append(chat)
                save_json(index, chats)
                print("Created: https://chat.scio.cz/chat/" + chat["id"])
            elif choice == "a":
                identifier = input("Existing chat ID: ").strip()
                identifier = str(uuid.UUID(identifier))
                chat = next((c for c in chats if c["id"] == identifier), None)
                if chat is None:
                    chat = {"id": identifier, "title": input("Local chat label: ").strip() or identifier}
                    chats.append(chat)
                    save_json(index, chats)
            elif choice.isdigit() and 1 <= int(choice) <= len(chats):
                chat = chats[int(choice) - 1]
            else:
                print("Choose an option from the menu.")
                continue
            print("Enter messages; /model changes this chat model; /back opens menu.")
            while True:
                prompt = input("You: ").strip()
                if prompt == "/back":
                    break
                if prompt == "/model":
                    chat["model"] = choose_model(chat.get("model", model))
                    save_json(index, chats)
                    continue
                if not prompt:
                    continue
                send_message(token, chat["id"], prompt, chat.get("model", model))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            print(f"Could not complete action: {exc}")
            if isinstance(exc, HTTPError) and exc.code in (401, 403):
                print("Replace your expired token with T, or check chat access.")


MODELS = {
    "auto": "Automatic",
    "google-weak": "Google / Flash",
    "google-strong": "Google / Pro",
    "anthropic-strong": "Anthropic",
    "openai-weak": "OpenAI",
}


def validate_model(model):
    if model not in MODELS:
        raise ValueError("Unknown Scio model ID. Choose: " + ", ".join(MODELS))
    return model


def choose_model(current):
    keys = list(MODELS)
    for i, key in enumerate(keys, 1):
        print(f"{i}. {MODELS[key]} ({key})")
    value = input(f"Model number or ID [{current}]: ").strip()
    if not value:
        return current
    if value.isdigit() and 1 <= int(value) <= len(keys):
        value = keys[int(value) - 1]
    return validate_model(value)


def events(response):
    lines = []
    for raw in response:
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if lines:
                yield "\n".join(lines)
                lines.clear()
        elif line.startswith("data:"):
            lines.append(line[5:].removeprefix(" "))
    if lines:
        yield "\n".join(lines)


def ask(token, session_id, prompt, model="auto", on_delta=None):
    session_id = str(uuid.UUID(session_id))
    if not prompt.strip():
        raise ValueError("Message cannot be empty.")
    payload = {
        "command": {
            "type": "send-message", "sessionId": session_id,
            "model": validate_model(model),
            "message": {"id": str(uuid.uuid4()), "role": "user",
                        "parts": [{"type": "text", "text": prompt}]},
            "clientContext": {},
        },
        "resumeRunId": str(uuid.uuid4()), "resumeToken": str(uuid.uuid4()),
    }
    chunks = []
    finished = False
    with urlopen(make_request(token, payload), timeout=180) as response:
        if "text/event-stream" not in response.headers.get("Content-Type", ""):
            raise RuntimeError("Expected a streamed response. Check the chat on Scio before retrying.")
        for data in events(response):
            if data == "[DONE]":
                finished = True
                continue
            event = json.loads(data)
            kind = event.get("type")
            if kind == "error":
                raise RuntimeError("Scio: " + str(event.get("errorText", "Unknown stream error")))
            if kind == "text-delta":
                delta = event.get("delta", event.get("textDelta", ""))
                chunks.append(delta)
                if on_delta:
                    on_delta(delta)
            if kind == "finish":
                finished = True
            if kind == "abort":
                raise RuntimeError("Scio aborted the response. Check the chat before retrying.")
    if not finished:
        raise RuntimeError("Stream ended before completion. Check the chat before resending.")
    return {"session_id": session_id, "requested_model": model, "text": "".join(chunks)}


def send_message(token, session_id, prompt, model="auto"):
    print("Assistant: ", end="", flush=True)
    try:
        ask(token, session_id, prompt, model, lambda text: print(text, end="", flush=True))
        print()
        return 0
    except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
        print(f"\nRequest failed: {exc}. Check Scio before retrying.", file=sys.stderr)
        if isinstance(exc, HTTPError) and exc.code in (401, 403):
            print("Use T in the main menu to replace your token; also check chat access.")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp", choices=["stdio", "http"], help="Run an MCP tool server")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        if args.mcp:
            from scio_mcp import run
            run(args.mcp, args.port)
        else:
            sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.", file=sys.stderr)
        sys.exit(130)
