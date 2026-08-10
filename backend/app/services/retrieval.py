from app.services.embeddings import cosine, embed

CHUNK_MIN_CHARS = 80


def chunk_text(text: str, max_chars: int = 400) -> list[str]:
   
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]

    chunks: list[str] = []
    current = ""
    for block in blocks:
        if len(current) + len(block) + 2 <= max_chars:
            current = f"{current}\n\n{block}" if current else block
        else:
            if current:
                chunks.append(current)
            current = block
    if current:
        chunks.append(current)

    keep = [c for c in chunks if len(c) >= CHUNK_MIN_CHARS]
     return keep or chunks


def top_chunks(resume_text: str, jd_text: str, k: int = 4) -> list[str]:
    chunks = chunk_text(resume_text)
    if len(chunks) <= k:
        return chunks

    jd_vector = embed(jd_text)
    scored = [(cosine(embed(c), jd_vector), c) for c in chunks]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [chunk for _, chunk in scored[:k]]
