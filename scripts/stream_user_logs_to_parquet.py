"""Stream user_logs from the .7z archives straight into month-partitioned Parquet.

The full CSV is ~30 GB uncompressed. Extracting it first would need that much free disk,
so this script pipes `7z x -so` into a streaming Arrow CSV reader and writes one Parquet
file per (month, source) under parquet_dir/user_logs/year_month=YYYYMM/. Spark reads the
result with partition discovery, exactly like the output of convert_to_parquet.py.

    python scripts/stream_user_logs_to_parquet.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
import yaml

SOURCES = {"v1": "user_logs.csv.7z", "v2": "user_logs_v2.csv.7z"}
SCHEMA = {
    "msno": pa.string(), "date": pa.int32(),
    "num_25": pa.int32(), "num_50": pa.int32(), "num_75": pa.int32(),
    "num_985": pa.int32(), "num_100": pa.int32(), "num_unq": pa.int32(),
    "total_secs": pa.float64(),
}
FLUSH_ROWS = 1_000_000


def convert(archive: Path, tag: str, out: Path) -> int:
    for old in out.glob(f"year_month=*/part-{tag}.parquet"):
        old.unlink()
    proc = subprocess.Popen(["7z", "x", "-so", str(archive)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    reader = pacsv.open_csv(
        proc.stdout,
        read_options=pacsv.ReadOptions(block_size=64 << 20),
        convert_options=pacsv.ConvertOptions(column_types=SCHEMA),
    )
    writers: dict[int, pq.ParquetWriter] = {}
    buffers: dict[int, list[pa.Table]] = {}
    sizes: dict[int, int] = {}
    total, t0 = 0, time.time()

    def flush(ym: int) -> None:
        if not buffers.get(ym):
            return
        table = pa.concat_tables(buffers[ym])
        if ym not in writers:
            d = out / f"year_month={ym}"
            d.mkdir(parents=True, exist_ok=True)
            writers[ym] = pq.ParquetWriter(d / f"part-{tag}.parquet", table.schema, compression="zstd")
        writers[ym].write_table(table)
        buffers[ym], sizes[ym] = [], 0

    for batch in reader:
        table = pa.Table.from_batches([batch])
        ym_col = pc.divide(table["date"], 100)
        for ym in pc.unique(ym_col).to_pylist():
            part = table.filter(pc.equal(ym_col, ym))
            buffers.setdefault(ym, []).append(part)
            sizes[ym] = sizes.get(ym, 0) + part.num_rows
            if sizes[ym] >= FLUSH_ROWS:
                flush(ym)
        total += table.num_rows
        if total % (20 * FLUSH_ROWS) < table.num_rows:
            print(f"[{tag}] {total / 1e6:,.0f}M rows · {time.time() - t0:,.0f}s", flush=True)

    for ym in list(buffers):
        flush(ym)
    for w in writers.values():
        w.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"7z exited with {proc.returncode} for {archive}")
    print(f"[{tag}] done: {total:,} rows into {len(writers)} months in {time.time() - t0:,.0f}s", flush=True)
    return total


def main() -> None:
    cfg = yaml.safe_load(Path("configs/default_config.yaml").read_text())
    raw = Path(cfg["paths"]["raw_dir"]).expanduser()
    out = Path(cfg["paths"]["parquet_dir"]).expanduser() / "user_logs"
    out.mkdir(parents=True, exist_ok=True)
    tags = sys.argv[1:] or list(SOURCES)
    for tag in tags:
        convert(raw / SOURCES[tag], tag, out)


if __name__ == "__main__":
    main()
