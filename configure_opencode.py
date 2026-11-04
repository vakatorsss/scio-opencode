"""Generate a local OpenCode 1 provider snippet without modifying existing config."""
import json
from pathlib import Path

import scio_provider as provider


def main():
    provider.local_key()
    key_path = provider.KEY_FILE.resolve().as_posix()
    config = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "scio": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Scio (local adapter)",
                "options": {
                    "baseURL": "http://127.0.0.1:8766/v1",
                    "apiKey": "{file:" + key_path + "}",
                },
                "models": {
                    key: {"name": "Scio " + name, "tool_call": True,
                          "limit": {"context": 32000, "output": 8192}}
                    for key, name in provider.scio.MODELS.items()
                },
            }
        },
        "model": "scio/openai-weak",
    }
    destination = Path(__file__).resolve().parent / "opencode.local.json"
    destination.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated: {destination}")
    print("Merge provider.scio into your OpenCode 1 config; model is an optional default.")
    print("Existing configuration was not changed. Restart OpenCode after merging.")


if __name__ == "__main__":
    main()
