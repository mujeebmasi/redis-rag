from app.core.indexing_config import CHUNK_OVERLAP, CHUNK_SIZE
from app.services.embedding_service import _split_text


def test_empty_text_gives_no_chunks():
    assert _split_text("") == []
    assert _split_text("   \n\n  ") == []


def test_short_text_is_one_chunk():
    assert _split_text("A small README.") == ["A small README."]


def test_long_text_is_split_with_bounded_chunks():
    paragraphs = [f"Paragraph {i}. " + "word " * 120 for i in range(20)]
    text = "\n\n".join(paragraphs)

    chunks = _split_text(text)

    assert len(chunks) > 1
    # A chunk is at most CHUNK_SIZE, plus the overlap carried from the previous one
    assert all(len(c) <= CHUNK_SIZE + CHUNK_OVERLAP + 1 for c in chunks)
    # Nothing is lost: every paragraph heading appears in some chunk
    for i in range(20):
        assert any(f"Paragraph {i}." in c for c in chunks)


def test_consecutive_chunks_overlap():
    text = "\n\n".join(f"Section {i} " + "x" * 700 for i in range(6))

    chunks = _split_text(text)

    for prev, nxt in zip(chunks, chunks[1:]):
        assert prev[-50:] in nxt
