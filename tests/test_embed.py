from context_note.embed import split, to_chunks
from context_note.parser import Message


def test_short_text_is_not_split():
    assert split("short text", max_chars=100, overlap=10) == ["short text"]


def test_splits_on_paragraph_boundaries():
    text = "first paragraph here.\n\nsecond paragraph here.\n\nthird paragraph here."
    pieces = split(text, max_chars=30, overlap=5)
    assert len(pieces) > 1
    assert "".join(pieces).replace("\n\n", "") != ""
    for piece in pieces:
        assert len(piece) <= 30 or "\n\n" not in piece


def test_paragraph_longer_than_max_chars_is_hard_cut_with_overlap():
    para = "x" * 100
    pieces = split(para, max_chars=40, overlap=10)
    assert all(len(p) <= 40 for p in pieces)
    # step = max_chars - overlap, so consecutive pieces should overlap by `overlap` chars
    assert pieces[0][-10:] == pieces[1][:10]


def test_blank_paragraphs_are_dropped():
    text = "a" * 20 + "\n\n\n\n" + "b" * 20
    pieces = split(text, max_chars=15, overlap=2)
    assert all(p.strip() for p in pieces)


def test_to_chunks_preserves_message_metadata():
    msg = Message(
        conversation_id="c1",
        conversation_name="convo",
        project_name="proj",
        role="human",
        text="a" * 50,
        created_at="2026-01-01",
        index_in_conversation=3,
    )
    chunks = to_chunks(msg, max_chars=1200, overlap=100)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.conversation_id == "c1"
    assert chunk.conversation_name == "convo"
    assert chunk.project_name == "proj"
    assert chunk.role == "human"
    assert chunk.created_at == "2026-01-01"
    assert chunk.position == 3
    assert chunk.text == msg.text


def test_to_chunks_splits_long_message_into_multiple_chunks():
    msg = Message(
        conversation_id="c1",
        conversation_name="convo",
        project_name=None,
        role="assistant",
        text="\n\n".join(["paragraph " + str(i) * 20 for i in range(10)]),
        created_at="",
        index_in_conversation=0,
    )
    chunks = to_chunks(msg, max_chars=50, overlap=5)
    assert len(chunks) > 1
    assert all(c.position == 0 for c in chunks)
