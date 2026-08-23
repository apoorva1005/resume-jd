"""Vector search: what goes into Chroma's metadata, and what comes back out.

Two halves:

* `build_metadata` -- the filterable facts we attach to each vector at upload
  time. Chroma metadata values must be flat scalars (str/int/float/bool), so
  anything structured is flattened here rather than stored as a nested object.

* `build_where` -- turns a caller's filters into a Chroma `where` clause with
  `user_id` always ANDed in. Going through one builder is what makes the tenant
  scope hard to forget, the same argument `db.py` makes for Mongo queries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.features import extract_years, highest_degree

PREVIEW_CHARS = 200

# Chroma stores the full text alongside the vector, which is what makes
# where_document substring filtering possible. Cap it so a long resume doesn't
# bloat the index -- matching already happens on the vector, and the Mongo
# document remains the complete copy.
MAX_INDEXED_CHARS = 8000


def build_metadata(
    kind: str,
    user_id: str,
    text: str,
    created_at: datetime,
    filename: str | None = None,
    sections: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Filterable metadata for one resume or JD vector."""
    sections = sections or {}

    metadata: dict[str, Any] = {
        "user_id": user_id,
        "kind": kind,
        # ISO for display, epoch for range filters -- Chroma compares numbers,
        # not dates, so a sortable string alone wouldn't support $gte.
        "created_at": created_at.isoformat(),
        "created_ts": int(created_at.timestamp()),
        "source": "file" if filename else "text",
        "filename": filename or "",
        "char_count": len(text),
        # Pulled from the same regex features the scorer uses, so a filter and
        # a score never disagree about how many years a resume claims.
        "years_experience": extract_years(text),
        "degree_rank": highest_degree(text),
    }

    if kind == "resume":
        metadata["has_skills_section"] = bool(sections.get("skills", "").strip())
        metadata["has_experience_section"] = bool(sections.get("experience", "").strip())

    return metadata


def indexed_document(text: str) -> str:
    return text[:MAX_INDEXED_CHARS]


def build_where(user_id: str, filters: Any | None = None) -> dict[str, Any]:
    """Chroma `where` clause: the owner scope, plus any caller filters.

    A single-condition clause is returned bare (`{"user_id": ...}`); more than
    one is wrapped in `$and`, which Chroma requires for multiple conditions.
    """
    conditions: list[dict[str, Any]] = [{"user_id": {"$eq": user_id}}]

    if filters is not None:
        if getattr(filters, "min_years", None) is not None:
            conditions.append({"years_experience": {"$gte": filters.min_years}})

        if getattr(filters, "min_degree_rank", None) is not None:
            conditions.append({"degree_rank": {"$gte": filters.min_degree_rank}})

        if getattr(filters, "source", None):
            conditions.append({"source": {"$eq": filters.source}})

        created_after = getattr(filters, "created_after", None)
        if created_after is not None:
            # A naive datetime from the client is read as UTC; timestamp()
            # would otherwise silently apply the server's local offset.
            if created_after.tzinfo is None:
                created_after = created_after.replace(tzinfo=timezone.utc)
            conditions.append({"created_ts": {"$gte": int(created_after.timestamp())}})

        if getattr(filters, "has_skills_section", None) is not None:
            conditions.append(
                {"has_skills_section": {"$eq": filters.has_skills_section}}
            )

    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def build_where_document(filters: Any | None = None) -> dict[str, Any] | None:
    """Optional substring filter over the indexed text itself.

    Distinct from metadata filtering: this searches the document body, so it
    can require a literal term the embedding might have smoothed over.
    """
    if filters is None:
        return None
    term = (getattr(filters, "must_contain", None) or "").strip()
    if not term:
        return None
    return {"$contains": term}


def describe_filters(where: dict[str, Any]) -> list[str]:
    """Flatten a where clause into readable lines for the API response.

    Echoing back what was actually applied means a surprising result set can be
    explained without turning on server logging.
    """
    conditions = where.get("$and", [where])
    described: list[str] = []
    for condition in conditions:
        for field, test in condition.items():
            if isinstance(test, dict):
                for operator, value in test.items():
                    described.append(f"{field} {operator.lstrip('$')} {value}")
            else:
                described.append(f"{field} eq {test}")
    return described
