from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from flowsec.production.schema import NEAR_SIGNATURE_RULE, content_hash
from flowsec.production.storage import ParquetShardWriter, ProductionCatalog


VARIANT_DEFINITIONS = (
    (
        "EXACT_EVAL_CLEAN",
        "evidence_signature",
        "exact Initial Model View equality",
    ),
    (
        "NEAR_EVAL_CLEAN",
        "near_signature",
        "pre-registered recursively quantized Initial Model View equality",
    ),
)


def _split_counts(catalog: ProductionCatalog) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for dataset, split, count in catalog.query(
        """
        SELECT dataset,base_split,COUNT(*)
        FROM records
        WHERE retained=1 AND base_split IN ('train','validation','test')
        GROUP BY dataset,base_split
        ORDER BY dataset,base_split
        """
    ):
        output.setdefault(str(dataset), {})[str(split)] = int(count)
    for values in output.values():
        for split in ("train", "validation", "test"):
            values.setdefault(split, 0)
    return output


def build_evaluation_clean_variants(
    *,
    catalog: ProductionCatalog,
    output_root: Path,
    processing: dict[str, Any],
) -> dict[str, Any]:
    """Materialize evaluation-only exclusion IDs for exact and near variants.

    Primary records and every training row remain unchanged. Validation only
    excludes signatures observed in train. Test excludes signatures observed in
    train or in validation after that validation cleaning step.
    """

    primary_counts = _split_counts(catalog)
    variants: dict[str, Any] = {}
    for variant_name, signature_column, semantics in VARIANT_DEFINITIONS:
        prefix = variant_name.lower()
        for table in (f"{prefix}_train", f"{prefix}_effective_validation"):
            catalog.connection.execute(f"DROP TABLE IF EXISTS temp.{table}")
        catalog.connection.execute(
            f"""
            CREATE TEMP TABLE {prefix}_train (
                dataset TEXT NOT NULL,
                signature TEXT NOT NULL,
                PRIMARY KEY(dataset,signature)
            ) WITHOUT ROWID
            """
        )
        catalog.connection.execute(
            f"""
            INSERT OR IGNORE INTO {prefix}_train(dataset,signature)
            SELECT dataset,{signature_column}
            FROM records
            WHERE retained=1 AND base_split='train'
            """
        )
        catalog.connection.execute(
            f"""
            CREATE TEMP TABLE {prefix}_effective_validation (
                dataset TEXT NOT NULL,
                signature TEXT NOT NULL,
                PRIMARY KEY(dataset,signature)
            ) WITHOUT ROWID
            """
        )
        catalog.connection.execute(
            f"""
            INSERT OR IGNORE INTO {prefix}_effective_validation(dataset,signature)
            SELECT validation.dataset,validation.{signature_column}
            FROM records AS validation
            LEFT JOIN {prefix}_train AS earlier
              ON earlier.dataset=validation.dataset
             AND earlier.signature=validation.{signature_column}
            WHERE validation.retained=1
              AND validation.base_split='validation'
              AND earlier.signature IS NULL
            """
        )

        cursor = catalog.connection.execute(
            f"""
            SELECT sample_id,dataset,base_split,reason
            FROM (
                SELECT
                    validation.sample_id AS sample_id,
                    validation.dataset AS dataset,
                    validation.base_split AS base_split,
                    'signature_seen_in_train' AS reason
                FROM records AS validation
                JOIN {prefix}_train AS earlier
                  ON earlier.dataset=validation.dataset
                 AND earlier.signature=validation.{signature_column}
                WHERE validation.retained=1
                  AND validation.base_split='validation'
                UNION ALL
                SELECT
                    test.sample_id AS sample_id,
                    test.dataset AS dataset,
                    test.base_split AS base_split,
                    CASE
                        WHEN earlier.signature IS NOT NULL
                        THEN 'signature_seen_in_train'
                        ELSE 'signature_seen_in_effective_validation'
                    END AS reason
                FROM records AS test
                LEFT JOIN {prefix}_train AS earlier
                  ON earlier.dataset=test.dataset
                 AND earlier.signature=test.{signature_column}
                LEFT JOIN {prefix}_effective_validation AS validation
                  ON validation.dataset=test.dataset
                 AND validation.signature=test.{signature_column}
                WHERE test.retained=1
                  AND test.base_split='test'
                  AND (earlier.signature IS NOT NULL OR validation.signature IS NOT NULL)
            )
            ORDER BY dataset,base_split,sample_id
            """
        )
        writer = ParquetShardWriter(
            output_root / "sensitivity_variants" / variant_name,
            str(processing["parquet_compression"]),
            int(processing["parquet_shard_rows"]),
        )
        excluded: Counter[tuple[str, str]] = Counter()
        reasons: Counter[str] = Counter()
        for sample_id, dataset, split, reason in cursor:
            writer.write(
                {
                    "sample_id": str(sample_id),
                    "dataset": str(dataset),
                    "split": str(split),
                    "exclusion_reason": str(reason),
                }
            )
            excluded[(str(dataset), str(split))] += 1
            reasons[str(reason)] += 1
        asset = writer.close()
        asset["files"] = [
            str(Path(path).relative_to(output_root)) for path in asset["files"]
        ]

        counts: dict[str, Any] = {}
        for dataset, split_values in primary_counts.items():
            removed = {
                split: excluded[(dataset, split)]
                for split in ("train", "validation", "test")
            }
            effective = {
                split: split_values[split] - removed[split]
                for split in ("train", "validation", "test")
            }
            counts[dataset] = {
                "primary": dict(split_values),
                "excluded": removed,
                "effective": effective,
                "train_unchanged": effective["train"] == split_values["train"],
            }
        variants[variant_name] = {
            "status": "REGISTERED",
            "signature_column": signature_column,
            "signature_semantics": semantics,
            "training_policy": "training set is unchanged",
            "validation_policy": "exclude evaluation rows whose signature exists in train",
            "test_policy": "exclude evaluation rows whose signature exists in train or effective validation",
            "primary_replaced": False,
            "counts": counts,
            "exclusion_reasons": dict(sorted(reasons.items())),
            "exclusion_id_asset": asset,
        }

    return {
        "primary": {
            "id": "PRIMARY_CHRONOLOGICAL",
            "policy": "real retained chronological/scenario-held distribution",
            "counts": primary_counts,
        },
        "variants": variants,
        "near_signature_rule": NEAR_SIGNATURE_RULE,
        "near_signature_rule_sha256": content_hash(NEAR_SIGNATURE_RULE),
        "superseded_variant": {
            "id": "NEAR_DUPLICATE_SENSITIVITY_VARIANT",
            "old_policy": "retain highest-isolation split and delete lower-isolation splits",
            "SUPERSEDED_BEFORE_ANY_MODEL_RUN": True,
            "result_driven_change": False,
        },
        "canonical_training_distribution_changed": False,
        "future_training_scale_policy": "use a separate reproducible sampling layer; never model-view deduplication",
    }
