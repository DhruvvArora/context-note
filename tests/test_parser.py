import json
import zipfile

import pytest

from context_note.parser import parse_conversations, read_export


def test_parses_flat_text_and_content_blocks():
    raw = [
        {
            "uuid": "c1",
            "name": "Chunking strategy",
            "project": {"name": "context-note"},
            "chat_messages": [
                {"sender": "human", "text": "how should we chunk long messages?"},
                {
                    "sender": "assistant",
                    "content": [
                        {"type": "text", "text": "split on paragraph boundaries"},
                        {"type": "tool_use", "input": {}},
                    ],
                },
            ],
        }
    ]
    messages = list(parse_conversations(raw))
    assert [m.role for m in messages] == ["human", "assistant"]
    assert messages[0].text == "how should we chunk long messages?"
    assert messages[1].text == "split on paragraph boundaries"
    assert messages[0].project_name == "context-note"
    assert messages[0].conversation_id == "c1"
    assert messages[1].index_in_conversation == 1


def test_project_as_bare_string():
    raw = [
        {
            "id": "c2",
            "name": "n",
            "project": "Job Search",
            "messages": [{"role": "user", "text": "hello there friend"}],
        }
    ]
    messages = list(parse_conversations(raw))
    assert messages[0].project_name == "Job Search"


def test_missing_project_is_none():
    raw = [{"uuid": "c3", "chat_messages": [{"sender": "human", "text": "hi there"}]}]
    messages = list(parse_conversations(raw))
    assert messages[0].project_name is None
    assert messages[0].conversation_name == "(untitled)"


def test_skips_convo_without_id():
    raw = [{"name": "no id here", "chat_messages": [{"sender": "human", "text": "hi"}]}]
    assert list(parse_conversations(raw)) == []


def test_skips_non_dict_entries():
    raw = ["not a dict", None, 42]
    assert list(parse_conversations(raw)) == []


def test_skips_messages_with_no_text():
    raw = [
        {
            "uuid": "c4",
            "chat_messages": [
                {"sender": "human", "content": [{"type": "image", "url": "x"}]},
                {"sender": "human", "text": "  "},
                {"sender": "human", "text": "actual content"},
            ],
        }
    ]
    messages = list(parse_conversations(raw))
    assert len(messages) == 1
    assert messages[0].text == "actual content"


def test_read_export_json(tmp_path):
    raw = [{"uuid": "c5", "chat_messages": [{"sender": "human", "text": "from json file"}]}]
    path = tmp_path / "conversations.json"
    path.write_text(json.dumps(raw))
    messages = list(read_export(path))
    assert len(messages) == 1
    assert messages[0].text == "from json file"


def test_read_export_zip(tmp_path):
    raw = [{"uuid": "c6", "chat_messages": [{"sender": "human", "text": "from zip file"}]}]
    path = tmp_path / "export.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("data/conversations.json", json.dumps(raw))
    messages = list(read_export(path))
    assert len(messages) == 1
    assert messages[0].text == "from zip file"


def test_read_export_zip_without_conversations_json(tmp_path):
    path = tmp_path / "bad.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("readme.txt", "nothing useful")
    with pytest.raises(ValueError):
        list(read_export(path))


def test_read_export_unsupported_suffix(tmp_path):
    path = tmp_path / "export.txt"
    path.write_text("nope")
    with pytest.raises(ValueError):
        list(read_export(path))


def test_read_export_top_level_must_be_list(tmp_path):
    path = tmp_path / "conversations.json"
    path.write_text(json.dumps({"not": "a list"}))
    with pytest.raises(ValueError):
        list(read_export(path))
