"""Text extraction from PDF/DOCX/TXT plus a rough section split.

The section splitter is intentionally dumb: find lines that look like known
headers, slice the text between them. It gets the common single-column resume
right and gives up gracefully on anything else (everything lands in "other").
"""

import io
import re

import docx2txt
import pdfplumber

# Header keyword -> canonical section name.
SECTION_KEYWORDS = {
    "skills": "skills",
    "technical skills": "skills",
    "technologies": "skills",
    "experience": "experience",
    "work experience": "experience",
    "professional experience": "experience",
    "employment": "experience",
    "education": "education",
    "academic": "education",
    "qualifications": "education",
    "projects": "projects",
    "certifications": "certifications",
}


def extract_text(data: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        return _from_pdf(data)
    if name.endswith(".docx"):
        return docx2txt.process(io.BytesIO(data)) or ""
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="ignore")
    raise ValueError(f"Unsupported file type: {filename}. Use PDF, DOCX or TXT.")


def _from_pdf(data: bytes) -> str:
    pages = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n".join(pages)


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _header_for(line: str) -> str | None:
    """Return the canonical section name if this line looks like a header."""
    stripped = line.strip().strip(":").strip()
    # Headers are short. A 15-word line that happens to contain "experience"
    # is a sentence, not a header.
    if not stripped or len(stripped.split()) > 4:
        return None
    return SECTION_KEYWORDS.get(stripped.lower())


def split_sections(text: str) -> dict[str, str]:
    """Split into {skills, experience, education, other}."""
    sections: dict[str, list[str]] = {}
    current = "other"

    for line in text.split("\n"):
        header = _header_for(line)
        if header:
            current = header
            continue
        sections.setdefault(current, []).append(line)

    result = {
        name: clean_text("\n".join(lines)) for name, lines in sections.items() if lines
    }
    # Guarantee the keys the rest of the app reads.
    for key in ("skills", "experience", "education"):
        result.setdefault(key, "")
    return result
