"""Pure-function helpers for exporting selected datasets as a tarball."""

from __future__ import annotations

import csv
import io
import logging
import re
import tarfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection
    from labretriever import VirtualDB

logger = logging.getLogger("shiny")

_SAFE_NAME_RE = re.compile(r"[^\w.\-]")


def _safe_dir_name(display_name: str) -> str:
    """
    Sanitize a display name for use as a tarball directory entry.

    Replaces any character outside ``[a-zA-Z0-9_.-]`` with ``_`` and strips
    leading/trailing dots and underscores to prevent path traversal.

    :param display_name: Raw display name.
    :returns: Filesystem-safe directory name.

    """
    sanitized = _SAFE_NAME_RE.sub("_", display_name)
    sanitized = sanitized.strip("_.")
    return sanitized or "dataset"


@dataclass(frozen=True)
class ExportDataset:
    """
    One dataset's export specification — SQL queries to execute, not materialised
    DataFrames.

    Queries are executed lazily inside :func:`build_export_tarball` so that
    only one dataset's data is in memory at a time.

    """

    display_name: str
    metadata_sql: str
    metadata_params: dict[str, Any]
    data_sql: str
    data_params: dict[str, Any]
    description: str | None = None


def build_readme(display_name: str, description: str) -> str:
    """
    Build README.md content for a single dataset subdirectory.

    :param display_name: Human-readable dataset name.
    :param description: Dataset description from the DataCard config.
    :returns: Markdown string.

    """
    return (
        f"# {display_name}\n"
        f"\n"
        f"{description}\n"
        f"\n"
        f"## Contents\n"
        f"\n"
        f"- **metadata.csv** -- Sample-level metadata for this dataset. Each row\n"
        f"  represents one sample (one regulator interrogation under specific\n"
        f"  experimental conditions).\n"
        f"\n"
        f"- **annotated_features.csv** -- Full genomic data for this dataset. Each\n"
        f"  row represents a measurement at a specific genomic feature (gene) for a\n"
        f"  specific sample.\n"
    )


def get_dataset_description(vdb: VirtualDB, db_name: str) -> str | None:
    """
    Retrieve the DataCard config description for a dataset.

    Uses private VirtualDB attributes; returns ``None`` on any failure.

    .. todo:: Replace with public VirtualDB API when available (issue #213).

    :param vdb: VirtualDB instance.
    :param db_name: Dataset name.
    :returns: Description string or ``None``.

    """
    try:
        repo_id, config_name = vdb._db_name_map[db_name]
        card = vdb._datacards.get(repo_id)
        if card is None:
            return None
        config = card.get_config(config_name)
        if config is None:
            return None
        return config.description or None
    except Exception:
        logger.warning(
            "Failed to retrieve DataCard description for %s (private API)",
            db_name,
            exc_info=True,
        )
        return None


def _query_to_csv_bytes(
    cursor: DuckDBPyConnection, sql: str, params: dict[str, Any]
) -> bytes:
    """
    Execute a SQL query on a DuckDB cursor and return the result serialized as CSV bytes
    with LF line endings.

    Uses ``csv.writer`` instead of ``pd.DataFrame.to_csv`` to avoid pandas
    serialization overhead.

    .. todo:: Replace ``vdb._conn.cursor()`` access with public API (issue #213).

    :param cursor: A DuckDB cursor (thread-safe for reads when each thread
        holds its own cursor obtained via ``conn.cursor()``).
    :param sql: SQL query string.
    :param params: Bound parameter values.
    :returns: UTF-8 encoded CSV bytes.

    """
    result = cursor.execute(sql, params) if params else cursor.execute(sql)
    cols = [d[0] for d in result.description]
    rows = result.fetchall()

    buf = io.BytesIO()
    wrapper = io.TextIOWrapper(buf, encoding="utf-8", newline="")
    writer = csv.writer(wrapper, lineterminator="\n")
    writer.writerow(cols)
    writer.writerows(rows)
    wrapper.flush()
    wrapper.detach()
    return buf.getvalue()


def build_export_tarball(
    datasets: list[ExportDataset],
    vdb: VirtualDB,
    progress_callback: Callable[[str], None] | None = None,
) -> io.BytesIO:
    """
    Assemble a ``.tar.gz`` archive in memory from a list of export dataset
    specifications.

    Each dataset becomes a subdirectory with a sanitized name (see
    :func:`_safe_dir_name`).  SQL queries are executed one at a time via
    :func:`_query_to_csv_bytes` so only one dataset's data is in memory at
    once.

    Uses ``tarfile`` pipe mode (``w|gz``) for streaming writes into an
    in-memory ``BytesIO`` buffer — no temp files on disk.  The full buffer
    is returned to the caller for chunked yielding.

    A thread-safe DuckDB cursor is created via ``vdb._conn.cursor()`` so
    this function can safely run in a worker thread while the main event
    loop continues to use ``vdb._conn`` for reactive queries.

    :param datasets: Dataset export specs (SQL queries, not DataFrames).
    :param vdb: VirtualDB instance for executing queries.
    :param progress_callback: Optional callable invoked with the display name
        of each dataset after it has been written to the tarball.
    :returns: ``BytesIO`` buffer positioned at the start, ready for reading.

    """
    # Create a thread-local cursor so we don't race with the event loop's
    # use of vdb._conn.  DuckDB cursors are safe for concurrent reads.
    cursor = vdb._conn.cursor()

    out = io.BytesIO()
    try:
        with tarfile.open(mode="w|gz", fileobj=out) as tar:
            for ds in datasets:
                dir_name = _safe_dir_name(ds.display_name)

                # Query both files before writing either — if one fails,
                # skip the entire dataset rather than leaving a partial
                # directory.
                try:
                    meta_bytes = _query_to_csv_bytes(
                        cursor, ds.metadata_sql, ds.metadata_params
                    )
                    data_bytes = _query_to_csv_bytes(
                        cursor, ds.data_sql, ds.data_params
                    )
                except Exception:
                    logger.exception(
                        "Failed to query dataset %s during export",
                        ds.display_name,
                    )
                    continue

                # metadata.csv
                meta_info = tarfile.TarInfo(name=f"{dir_name}/metadata.csv")
                meta_info.size = len(meta_bytes)
                tar.addfile(meta_info, io.BytesIO(meta_bytes))

                # annotated_features.csv
                data_info = tarfile.TarInfo(name=f"{dir_name}/annotated_features.csv")
                data_info.size = len(data_bytes)
                tar.addfile(data_info, io.BytesIO(data_bytes))

                # README.md (optional)
                if ds.description:
                    readme_content = build_readme(ds.display_name, ds.description)
                    readme_bytes = readme_content.encode("utf-8")
                    readme_info = tarfile.TarInfo(name=f"{dir_name}/README.md")
                    readme_info.size = len(readme_bytes)
                    tar.addfile(readme_info, io.BytesIO(readme_bytes))

                if progress_callback:
                    progress_callback(ds.display_name)
    finally:
        cursor.close()

    out.seek(0)
    return out


__all__ = [
    "ExportDataset",
    "build_readme",
    "get_dataset_description",
    "build_export_tarball",
    "_safe_dir_name",
    "_query_to_csv_bytes",
]
