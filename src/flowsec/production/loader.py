from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flowsec.production.guards import AssetAccessPolicy


@dataclass(slots=True)
class ProductionAssetLoader:
    """Manifest-level access guard used before a physical Parquet scan is opened."""

    training_manifest: dict[str, Any]
    policy: AssetAccessPolicy

    def visible_assets(self) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for asset in self.training_manifest.get("assets", []):
            role = str(asset.get("ku_role", "K_known"))
            self.policy.assert_role_allowed(role)
            output.append(asset)
        return output

    def resolve(self, role: str, preset: str | None = None) -> dict[str, Any]:
        for asset in self.training_manifest.get("assets", []):
            if asset.get("role") != role:
                continue
            if preset is not None and asset.get("preset") != preset:
                continue
            self.policy.assert_role_allowed(str(asset.get("ku_role", "K_known")))
            return asset
        raise KeyError((role, preset))
