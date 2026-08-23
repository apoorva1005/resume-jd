from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.features import extract_years, highest_degree

PREVIEW_CHARS = 200
MAX_INDEXED_CHARS = 8000


def build_metadata(
    kind: str,
    user_id: str,
    text: str,
    created_at: datetime,
    filename: str | None = None,
    sections: dict[str, str] | None = None,
) -> dict[str, Any]:
    sections = sections or {}

    metadata: dict[str, Any] = {
        "user_id": user_id,
        "kind": kind,
         "created_at": created_at.isoformat(),
        "created_ts": int(created_at.timestamp()),
        "source": "file" if filename else "text",
        "filename": filename or "",
        "char_count": len(text),
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
    if filters is None:
        return None
    term = (getattr(filters, "must_contain", None) or "").strip()
    if not term:
        return None
    return {"$contains": term}


def describe_filters(where: dict[str, Any]) -> list[str]:
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
