import json


def parse_session(path: str) -> list[dict]:
    """Parse a CC session JSONL file and return user + assistant messages in order."""
    messages = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record.get("type") not in ("user", "assistant"):
                    continue
                msg = record.get("message", {})
                role = msg.get("role")
                content = msg.get("content", "")
                if role and content and isinstance(content, str):
                    messages.append({"role": role, "content": content})
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return messages
