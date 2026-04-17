import json


def extract_text_content(content) -> str:
    """Extract text from a CC message content field.

    Content can be:
    - A string (user messages)
    - A list of content blocks (assistant messages, tool results)
      Block types: text, tool_use, tool_result, thinking
      We extract text from 'text' blocks and skip tool_use/tool_result/thinking.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_result":
                    # tool_result can contain nested content
                    inner = block.get("content", "")
                    if isinstance(inner, str):
                        parts.append(inner)
                    elif isinstance(inner, list):
                        for sub in inner:
                            if isinstance(sub, dict) and sub.get("type") == "text":
                                parts.append(sub.get("text", ""))
        return "\n".join(parts)
    return ""


def parse_session(path: str, start_line: int = 0) -> tuple[list[dict], int]:
    """Parse a CC session JSONL file and return user + assistant messages in order.

    Args:
        path: Path to the session JSONL file.
        start_line: Line number to start parsing from (0-based). Skips lines before this.

    Returns:
        (messages, total_lines) — messages extracted and total line count of the file.
    """
    messages = []
    total_lines = 0
    try:
        with open(path) as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i < start_line:
                    continue
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record.get("type") not in ("user", "assistant"):
                    continue
                msg = record.get("message", {})
                role = msg.get("role")
                raw_content = msg.get("content", "")
                content = extract_text_content(raw_content)
                if role and content.strip():
                    messages.append({"role": role, "content": content})
    except (FileNotFoundError, json.JSONDecodeError):
        return [], 0
    return messages, total_lines
