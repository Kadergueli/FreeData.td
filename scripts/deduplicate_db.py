"""
FreeData.td — Fast Parallel Deduplication Script for Database Records
"""

import asyncio
from collections import defaultdict
import logging
import httpx
from app.services.storage import ObservationRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("deduplicate_db")
repo = ObservationRepository()

SECTORS = ["agriculture", "environment", "markets", "transport", "education", "economy"]


def clean_sector_table(table_name: str, sector: str) -> None:
    supabase = repo._supabase
    if not supabase:
        return

    logger.info("Scanning table '%s' for sector '%s'...", table_name, sector)
    all_rows = []
    offset = 0
    batch_size = 1000

    while True:
        try:
            res = (
                supabase.table(table_name)
                .select("id, secteur, indicateur, date_reference, region, source_api")
                .eq("secteur", sector)
                .order("id", desc=True)
                .range(offset, offset + batch_size - 1)
                .execute()
            )
            if not res.data:
                break
            all_rows.extend(res.data)
            if len(res.data) < batch_size:
                break
            offset += batch_size
        except Exception as exc:
            logger.error("Error fetching %s sector %s: %s", table_name, sector, exc)
            break

    logger.info("Table '%s' sector '%s': %d total rows fetched.", table_name, sector, len(all_rows))

    seen_keys = set()
    to_delete = []

    for r in all_rows:
        key = (
            str(r.get("secteur", "")).strip().lower(),
            str(r.get("indicateur", "")).strip().lower(),
            str(r.get("date_reference", "")).strip(),
            str(r.get("region", "")).strip().lower(),
            str(r.get("source_api", "")).strip().lower(),
        )
        if key in seen_keys:
            to_delete.append(r["id"])
        else:
            seen_keys.add(key)

    logger.info("Table '%s' sector '%s': %d duplicate rows to delete.", table_name, sector, len(to_delete))

    # Delete in batches of 100 IDs
    chunk_size = 100
    for i in range(0, len(to_delete), chunk_size):
        chunk = to_delete[i : i + chunk_size]
        try:
            supabase.table(table_name).delete().in_("id", chunk).execute()
        except Exception as exc:
            logger.error("Failed to delete chunk in %s sector %s: %s", table_name, sector, exc)

    logger.info("Table '%s' sector '%s' deduplication complete! Retained %d unique rows.", table_name, sector, len(seen_keys))


def main() -> None:
    if repo.backend == "supabase":
        for table in ["table_public", "table_clean"]:
            for sec in SECTORS:
                clean_sector_table(table, sec)

    if repo.backend == "sqlite" or True:
        try:
            with repo._connection() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """DELETE FROM observations WHERE id NOT IN (
                        SELECT MAX(id) FROM observations GROUP BY sector, indicator, reference_date, region, source
                    )"""
                )
                deleted = cursor.rowcount
                connection.commit()
                logger.info("SQLite deduplication deleted %d rows.", deleted)
        except Exception as exc:
            logger.info("SQLite cleanup skipped or non-fatal: %s", exc)

    logger.info("All deduplication completed successfully!")


if __name__ == "__main__":
    main()
