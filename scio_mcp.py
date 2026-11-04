"""Scio MCP tools. Start through scio_console.py --mcp http or --mcp stdio."""
import threading
from urllib.error import HTTPError, URLError

import scio_console as scio

LOCK = threading.RLock()


def build_server(port=8765):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError('Install MCP support: python -m pip install "mcp>=1.28,<2"') from exc
    server = FastMCP("Scio", host="127.0.0.1", port=port,
                     stateless_http=True, json_response=True)

    @server.tool()
    def list_models() -> dict:
        """List known Scio model aliases and the saved default. Availability depends on your account."""
        return {"models": scio.MODELS,
                "default": scio.read_json(scio.DATA_DIR / "settings.json", {}).get("model", "auto")}

    @server.tool()
    def list_chats() -> list[dict]:
        """List locally saved chat IDs, titles and requested models (not all server chats)."""
        with LOCK:
            return scio.read_json(scio.DATA_DIR / "chats.json", [])

    @server.tool()
    def create_chat(title: str, model: str = "auto") -> dict:
        """Create a real Scio chat and save its ID locally. This changes your Scio account."""
        with LOCK:
            try:
                chat = scio.create_chat(scio.get_token(interactive=False), title, model)
            except HTTPError as exc:
                raise RuntimeError(f"Scio HTTP {exc.code}; check your token and account access.") from None
            path = scio.DATA_DIR / "chats.json"
            chats = scio.read_json(path, [])
            chats.append(chat)
            scio.save_json(path, chats)
            return chat

    @server.tool()
    def send_message(session_id: str, message: str, model: str | None = None) -> dict:
        """Send a message to an existing Scio chat and return the answer. Model overrides the saved chat model for this call. The message is saved on Scio and may consume account quota. Do not automatically retry errors: a request may already have arrived."""
        with LOCK:
            chats = scio.read_json(scio.DATA_DIR / "chats.json", [])
            chat = next((c for c in chats if c["id"] == session_id), {})
            default = scio.read_json(scio.DATA_DIR / "settings.json", {}).get("model", "auto")
            selected = model or chat.get("model", default)
            try:
                return scio.ask(scio.get_token(interactive=False), session_id, message, selected)
            except HTTPError as exc:
                raise RuntimeError(f"Scio HTTP {exc.code}; check your login and chat access. Check Scio before retrying.") from None
            except (URLError, TimeoutError):
                raise RuntimeError("Connection failed. Check Scio before retrying; the message may have arrived.") from None

    return server


def run(transport="stdio", port=8765):
    build_server(port).run(transport="streamable-http" if transport == "http" else "stdio")
