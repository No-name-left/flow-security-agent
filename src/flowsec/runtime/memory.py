from __future__ import annotations

from typing import Protocol

from .contracts import ClassMemoryRecord, ExperienceRecord


class ExperienceMemory(Protocol):
    def retrieve(
        self,
        context: str,
        *,
        limit: int,
        filters: dict[str, str] | None = None,
    ) -> tuple[ExperienceRecord, ...]:
        ...

    def add(self, record: ExperienceRecord) -> None:
        ...


class InMemoryExperienceStore:
    """Deterministic fixture store, not the final retrieval implementation."""

    def __init__(self, records: list[ExperienceRecord] | None = None):
        if any(not record.feedback.verified for record in records or []):
            raise ValueError("unverified records cannot preload Experience Memory")
        self.records = list(records or [])

    def retrieve(
        self,
        context: str,
        *,
        limit: int,
        filters: dict[str, str] | None = None,
    ) -> tuple[ExperienceRecord, ...]:
        terms = {item.casefold() for item in context.split() if item}
        scored: list[tuple[int, int, ExperienceRecord]] = []
        for index, record in enumerate(self.records):
            if filters:
                dumped = record.model_dump(mode="json")
                if any(str(dumped.get(key)) != value for key, value in filters.items()):
                    continue
            haystack = {
                record.experience_id.casefold(),
                *(keyword.casefold() for keyword in record.keywords),
            }
            score = len(terms.intersection(haystack))
            if not terms or score:
                scored.append((-score, index, record))
        scored.sort(key=lambda item: (item[0], item[1]))
        return tuple(item[2] for item in scored[:limit])

    def add(self, record: ExperienceRecord) -> None:
        if not record.feedback.verified:
            raise ValueError("unverified feedback cannot enter Experience Memory")
        if any(item.experience_id == record.experience_id for item in self.records):
            raise ValueError(f"duplicate experience_id: {record.experience_id}")
        self.records.append(record)


class ClassMemory(Protocol):
    def get(self, class_id: str) -> ClassMemoryRecord | None:
        ...

    def add(self, record: ClassMemoryRecord) -> None:
        ...


class InMemoryClassMemory:
    """Separate namespace for class onboarding; never an experience store."""

    def __init__(self, records: list[ClassMemoryRecord] | None = None):
        self.records = {record.class_id: record for record in records or []}

    def get(self, class_id: str) -> ClassMemoryRecord | None:
        return self.records.get(class_id)

    def add(self, record: ClassMemoryRecord) -> None:
        if record.class_id in self.records:
            raise ValueError(f"duplicate class_id: {record.class_id}")
        self.records[record.class_id] = record
