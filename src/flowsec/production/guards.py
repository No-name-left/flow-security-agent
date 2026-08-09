from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


class FinalUnknownAccessError(PermissionError):
    """Raised when a normal training/development path attempts to expose U_final."""


@dataclass(frozen=True, slots=True)
class AssetAccessPolicy:
    phase: str = "development"
    exclude_final_unknown: bool = True
    support_labels_unlocked: bool = False

    def assert_role_allowed(self, ku_role: str) -> None:
        if ku_role == "U_final" and (
            self.exclude_final_unknown or self.phase not in {"final_evaluation", "support"}
        ):
            raise FinalUnknownAccessError(
                "U_final is isolated from normal train/development access"
            )
        if ku_role == "U_final_support" and not (
            self.phase == "support" and self.support_labels_unlocked
        ):
            raise FinalUnknownAccessError(
                "U_final support labels remain locked until the support phase"
            )

    def filter_rows(self, rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for row in rows:
            role = str(row.get("ku_role", "K_known"))
            self.assert_role_allowed(role)
            output.append(row)
        return output


def project_label_schema(
    schema: dict[str, Any],
    *,
    allowed_labels: Iterable[str],
    final_unknown_labels: Iterable[str],
    policy: AssetAccessPolicy,
) -> dict[str, Any]:
    allowed = set(allowed_labels)
    final = set(final_unknown_labels)
    descriptions = schema.get("label_descriptions", {})
    if policy.phase in {"final_evaluation", "support"} and not policy.exclude_final_unknown:
        visible = allowed
    else:
        visible = allowed - final
    return {
        **{key: value for key, value in schema.items() if key != "label_descriptions"},
        "fine_labels": [label for label in schema.get("fine_labels", []) if label in visible],
        "label_descriptions": {
            label: descriptions[label] for label in sorted(visible) if label in descriptions
        },
    }
