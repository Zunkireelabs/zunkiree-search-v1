import tiktoken


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Count tokens in text using tiktoken."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def chunk_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    model: str = "gpt-4",
) -> list[dict]:
    """
    Split text into chunks with overlap.

    Args:
        text: The text to chunk
        chunk_size: Target tokens per chunk
        chunk_overlap: Tokens to overlap between chunks
        model: Model for tokenization

    Returns:
        List of dicts with 'content', 'token_count', and 'chunk_index'
    """
    if not text or not text.strip():
        return []

    # Split by paragraphs first
    paragraphs = text.split("\n\n")
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks = []
    current_chunk = []
    current_tokens = 0
    chunk_index = 0

    for para in paragraphs:
        para_tokens = count_tokens(para, model)

        # If single paragraph exceeds chunk size, split by sentences
        if para_tokens > chunk_size:
            # Split by sentences
            sentences = _split_into_sentences(para)
            for sentence in sentences:
                sentence_tokens = count_tokens(sentence, model)

                if current_tokens + sentence_tokens > chunk_size and current_chunk:
                    # Save current chunk
                    chunk_text = " ".join(current_chunk)
                    chunks.append({
                        "content": chunk_text,
                        "token_count": current_tokens,
                        "chunk_index": chunk_index,
                    })
                    chunk_index += 1

                    # Start new chunk with overlap
                    overlap_text = _get_overlap_text(current_chunk, chunk_overlap, model)
                    current_chunk = [overlap_text] if overlap_text else []
                    current_tokens = count_tokens(overlap_text, model) if overlap_text else 0

                current_chunk.append(sentence)
                current_tokens += sentence_tokens
        else:
            # Check if adding this paragraph exceeds chunk size
            if current_tokens + para_tokens > chunk_size and current_chunk:
                # Save current chunk
                chunk_text = "\n\n".join(current_chunk)
                chunks.append({
                    "content": chunk_text,
                    "token_count": current_tokens,
                    "chunk_index": chunk_index,
                })
                chunk_index += 1

                # Start new chunk with overlap
                overlap_text = _get_overlap_text(current_chunk, chunk_overlap, model)
                current_chunk = [overlap_text] if overlap_text else []
                current_tokens = count_tokens(overlap_text, model) if overlap_text else 0

            current_chunk.append(para)
            current_tokens += para_tokens

    # Don't forget the last chunk
    if current_chunk:
        chunk_text = "\n\n".join(current_chunk)
        chunks.append({
            "content": chunk_text,
            "token_count": count_tokens(chunk_text, model),
            "chunk_index": chunk_index,
        })

    return chunks


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    import re
    # Simple sentence splitting
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def _get_overlap_text(chunks: list[str], overlap_tokens: int, model: str) -> str:
    """Get text for overlap from end of chunks."""
    if not chunks:
        return ""

    # Take last chunk content
    last_text = chunks[-1] if isinstance(chunks[-1], str) else " ".join(chunks[-1:])

    # Simple approach: take last N characters roughly equivalent to overlap_tokens
    # Approximate 4 characters per token
    char_limit = overlap_tokens * 4

    if len(last_text) <= char_limit:
        return last_text

    return "..." + last_text[-char_limit:]
