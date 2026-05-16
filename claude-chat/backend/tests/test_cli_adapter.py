from claude_chat.providers.claude_cli import cli_event_to_canonical


def test_stream_event_to_text_delta() -> None:
    raw = {
        "type": "stream_event",
        "event": {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "hello"},
        },
    }
    out = cli_event_to_canonical(raw)
    assert len(out) == 1
    assert out[0]["type"] == "text_delta"
    assert out[0]["text"] == "hello"


def test_tool_use_mapping() -> None:
    raw = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "read_file",
                    "input": {"path": "foo.py"},
                }
            ]
        },
    }
    out = cli_event_to_canonical(raw)
    assert out[0]["type"] == "tool_use"
    assert out[0]["name"] == "read_file"
