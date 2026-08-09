from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

import pyarrow as pa
import pyarrow.parquet as pq

from flowsec.production.schema import canonical_json


CATALOG_COLUMNS = (
    "sample_id", "dataset", "dataset_version", "capture_id", "source_hash",
    "source_file", "timestamp_start", "timestamp_end", "raw_initiator_ip",
    "raw_responder_ip", "raw_initiator_port", "raw_responder_port", "l3_protocol",
    "l4_protocol", "first_frame", "last_frame", "fine_label", "coarse_label",
    "base_split", "packet_sequence_json", "session_summary_json", "capabilities_json",
    "missing_fields_json", "anomaly_ids_json", "original_label", "evidence_signature",
    "exact_signature", "reverse_signature", "near_signature", "source_identity_hash",
    "destination_identity_hash", "communication_pair_hash", "source_verified",
    "retained", "exclusion_reason",
)


class ProductionCatalog:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("PRAGMA temp_store=FILE")
        self.connection.execute("PRAGMA cache_size=-262144")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                record_id INTEGER PRIMARY KEY,
                sample_id TEXT NOT NULL,
                dataset TEXT NOT NULL,
                dataset_version TEXT NOT NULL,
                capture_id TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                source_file TEXT NOT NULL,
                timestamp_start REAL NOT NULL,
                timestamp_end REAL NOT NULL,
                raw_initiator_ip TEXT NOT NULL,
                raw_responder_ip TEXT NOT NULL,
                raw_initiator_port INTEGER NOT NULL,
                raw_responder_port INTEGER NOT NULL,
                l3_protocol TEXT NOT NULL,
                l4_protocol TEXT NOT NULL,
                first_frame INTEGER NOT NULL,
                last_frame INTEGER NOT NULL,
                fine_label TEXT NOT NULL,
                coarse_label TEXT NOT NULL,
                base_split TEXT NOT NULL,
                packet_sequence_json TEXT NOT NULL,
                session_summary_json TEXT NOT NULL,
                capabilities_json TEXT NOT NULL,
                missing_fields_json TEXT NOT NULL,
                anomaly_ids_json TEXT NOT NULL,
                original_label TEXT NOT NULL,
                evidence_signature TEXT NOT NULL,
                exact_signature TEXT NOT NULL,
                reverse_signature TEXT NOT NULL,
                near_signature TEXT NOT NULL,
                source_identity_hash TEXT NOT NULL,
                destination_identity_hash TEXT NOT NULL,
                communication_pair_hash TEXT NOT NULL,
                source_verified INTEGER NOT NULL,
                retained INTEGER NOT NULL DEFAULT 1,
                exclusion_reason TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS quarantine (
                reproducibility_id TEXT PRIMARY KEY,
                dataset TEXT NOT NULL,
                capture_id TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                reason TEXT NOT NULL,
                severity TEXT NOT NULL,
                count INTEGER NOT NULL,
                details_json TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.commit()
        self.connection.close()

    def delete_capture(self, dataset: str, capture_id: str) -> None:
        self.connection.execute(
            "DELETE FROM records WHERE dataset=? AND capture_id=?", (dataset, capture_id)
        )
        self.connection.execute(
            "DELETE FROM quarantine WHERE dataset=? AND capture_id=?", (dataset, capture_id)
        )
        self.connection.commit()

    def insert_records(self, rows: Iterable[dict[str, Any]], batch_size: int = 5000) -> int:
        placeholders = ",".join("?" for _ in CATALOG_COLUMNS)
        statement = (
            f"INSERT INTO records ({','.join(CATALOG_COLUMNS)}) VALUES ({placeholders})"
        )
        batch: list[tuple[Any, ...]] = []
        count = 0
        for row in rows:
            batch.append(tuple(row[column] for column in CATALOG_COLUMNS))
            if len(batch) >= batch_size:
                self.connection.executemany(statement, batch)
                count += len(batch)
                batch.clear()
        if batch:
            self.connection.executemany(statement, batch)
            count += len(batch)
        self.connection.commit()
        return count

    def insert_quarantine(
        self,
        *,
        reproducibility_id: str,
        dataset: str,
        capture_id: str,
        source_hash: str,
        reason: str,
        severity: str,
        count: int,
        details: dict[str, Any],
    ) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO quarantine
            (reproducibility_id,dataset,capture_id,source_hash,reason,severity,count,details_json)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                reproducibility_id,
                dataset,
                capture_id,
                source_hash,
                reason,
                severity,
                int(count),
                canonical_json(details),
            ),
        )
        self.connection.commit()

    def capture_count(self, dataset: str, capture_id: str) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) FROM records WHERE dataset=? AND capture_id=?",
            (dataset, capture_id),
        ).fetchone()
        return int(row[0])

    def create_indexes(self) -> None:
        statements = [
            "CREATE INDEX IF NOT EXISTS idx_records_order ON records(dataset,capture_id,base_split,timestamp_start,sample_id)",
            "CREATE INDEX IF NOT EXISTS idx_records_identity ON records(dataset,sample_id)",
            "CREATE INDEX IF NOT EXISTS idx_records_evidence ON records(dataset,evidence_signature)",
            "CREATE INDEX IF NOT EXISTS idx_records_exact ON records(dataset,exact_signature)",
            "CREATE INDEX IF NOT EXISTS idx_records_reverse ON records(dataset,reverse_signature)",
            "CREATE INDEX IF NOT EXISTS idx_records_near ON records(dataset,near_signature)",
            "CREATE INDEX IF NOT EXISTS idx_records_label ON records(dataset,fine_label,coarse_label,base_split,retained)",
        ]
        for statement in statements:
            self.connection.execute(statement)
        self.connection.commit()

    def apply_identity_deduplication(self) -> dict[str, Any]:
        """Apply Primary deduplication using immutable backend identity only.

        ``sample_id`` is the path-independent identity derived from source content,
        canonical bidirectional session identity, start time and deterministic
        ordinal. Model-view equality is intentionally audited below but never used
        as a Primary retention decision.
        """
        self.create_indexes()
        self.connection.execute(
            "UPDATE records SET retained=1, exclusion_reason=''"
        )

        identity_label_conflict_groups = int(
            self.scalar(
                """
                SELECT COUNT(*) FROM (
                    SELECT dataset,sample_id
                    FROM records
                    GROUP BY dataset,sample_id
                    HAVING COUNT(DISTINCT fine_label || char(31) || coarse_label)>1
                )
                """
            )
            or 0
        )
        self.connection.execute(
            """
            UPDATE records
            SET retained=0, exclusion_reason='identity_label_conflict'
            WHERE (dataset,sample_id) IN (
                SELECT dataset,sample_id
                FROM records
                GROUP BY dataset,sample_id
                HAVING COUNT(DISTINCT fine_label || char(31) || coarse_label)>1
            )
            """
        )
        identity_label_conflict_count = int(
            self.scalar(
                "SELECT COUNT(*) FROM records WHERE exclusion_reason='identity_label_conflict'"
            )
            or 0
        )

        identity_duplicate_groups = int(
            self.scalar(
                """
                SELECT COUNT(*) FROM (
                    SELECT dataset,sample_id
                    FROM records
                    WHERE retained=1
                    GROUP BY dataset,sample_id
                    HAVING COUNT(*)>1
                )
                """
            )
            or 0
        )
        self.connection.execute(
            """
            WITH ranked AS (
                SELECT
                    record_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY dataset,sample_id ORDER BY record_id
                    ) AS identity_ordinal,
                    COUNT(*) OVER (PARTITION BY dataset,sample_id) AS identity_count
                FROM records
                WHERE retained=1
            )
            UPDATE records
            SET retained=0, exclusion_reason='identity_duplicate'
            WHERE record_id IN (
                SELECT record_id
                FROM ranked
                WHERE identity_count>1 AND identity_ordinal>1
            )
            """
        )
        identity_duplicate_count = int(
            self.scalar(
                "SELECT COUNT(*) FROM records WHERE exclusion_reason='identity_duplicate'"
            )
            or 0
        )
        self.connection.execute(
            """
            UPDATE records
            SET retained=0, exclusion_reason='split_boundary_or_gap'
            WHERE retained=1 AND base_split='quarantine'
            """
        )
        self.connection.commit()

        exact_model_view_collision_groups = int(
            self.scalar(
                """
                SELECT COUNT(*) FROM (
                    SELECT dataset,evidence_signature
                    FROM records
                    WHERE retained=1
                    GROUP BY dataset,evidence_signature
                    HAVING COUNT(*)>1
                )
                """
            )
            or 0
        )
        exact_model_view_collision_records = int(
            self.scalar(
                """
                SELECT COALESCE(SUM(group_size),0) FROM (
                    SELECT COUNT(*) AS group_size
                    FROM records
                    WHERE retained=1
                    GROUP BY dataset,evidence_signature
                    HAVING COUNT(*)>1
                )
                """
            )
            or 0
        )
        view_label_collision_groups = int(
            self.scalar(
                """
                SELECT COUNT(*) FROM (
                    SELECT dataset,evidence_signature
                    FROM records
                    WHERE retained=1
                    GROUP BY dataset,evidence_signature
                    HAVING COUNT(DISTINCT fine_label || char(31) || coarse_label)>1
                )
                """
            )
            or 0
        )
        view_label_collision_count = int(
            self.scalar(
                """
                SELECT COALESCE(SUM(group_size),0) FROM (
                    SELECT COUNT(*) AS group_size
                    FROM records
                    WHERE retained=1
                    GROUP BY dataset,evidence_signature
                    HAVING COUNT(DISTINCT fine_label || char(31) || coarse_label)>1
                )
                """
            )
            or 0
        )
        counts = {
            row[0]: int(row[1])
            for row in self.connection.execute(
                "SELECT exclusion_reason,COUNT(*) FROM records WHERE retained=0 GROUP BY exclusion_reason"
            )
        }
        return {
            "policy": "Primary deduplication uses immutable backend identity (dataset + stable sample_id) only; model-view equality is audit-only",
            "backend_identity_field": "sample_id",
            "identity_duplicate_groups": identity_duplicate_groups,
            "identity_duplicate_count": identity_duplicate_count,
            "identity_label_conflict_groups": identity_label_conflict_groups,
            "identity_label_conflict_count": identity_label_conflict_count,
            "exact_model_view_collision_groups": exact_model_view_collision_groups,
            "exact_model_view_collision_records": exact_model_view_collision_records,
            "view_label_collision_groups": view_label_collision_groups,
            "view_label_collision_count": view_label_collision_count,
            "model_view_collision_retention_policy": "retain all distinct backend identities",
            "excluded_counts": counts,
        }

    def rows(self, where: str = "1=1", params: tuple[Any, ...] = ()) -> Iterator[dict[str, Any]]:
        cursor = self.connection.execute(
            f"SELECT {','.join(CATALOG_COLUMNS)} FROM records WHERE {where}", params
        )
        for values in cursor:
            yield dict(zip(CATALOG_COLUMNS, values))

    def scalar(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        row = self.connection.execute(sql, params).fetchone()
        return None if row is None else row[0]

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        return list(self.connection.execute(sql, params))


@dataclass(slots=True)
class ParquetShardWriter:
    root: Path
    compression: str
    max_rows: int
    rows: list[dict[str, Any]] = field(default_factory=list)
    part_number: int = 0
    row_count: int = 0
    byte_size: int = 0
    files: list[str] = field(default_factory=list)
    _logical_digest: Any = field(default_factory=hashlib.sha256)

    def write(self, row: dict[str, Any]) -> None:
        self.rows.append(row)
        self._logical_digest.update(canonical_json(row).encode("utf-8"))
        self._logical_digest.update(b"\n")
        self.row_count += 1
        if len(self.rows) >= self.max_rows:
            self.flush()

    def flush(self) -> None:
        if not self.rows:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"part-{self.part_number:05d}.parquet"
        table = pa.Table.from_pylist(self.rows)
        pq.write_table(
            table,
            path,
            compression=self.compression,
            use_dictionary=True,
            write_statistics=True,
        )
        self.byte_size += path.stat().st_size
        self.files.append(str(path))
        self.part_number += 1
        self.rows.clear()

    def close(self) -> dict[str, Any]:
        self.flush()
        if not self.files:
            self.root.mkdir(parents=True, exist_ok=True)
            marker = self.root / "_EMPTY.json"
            marker.write_text('{"rows":0}\n', encoding="utf-8")
            self.byte_size = marker.stat().st_size
            self.files.append(str(marker))
        return {
            "rows": self.row_count,
            "bytes": self.byte_size,
            "files": self.files,
            "logical_sha256": self._logical_digest.hexdigest(),
        }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
