"""Small, reproducible authenticated read probe. Not a capacity or production SLO claim."""
import argparse
import asyncio
import json
import os
import platform
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx


async def run(args):
    token = os.environ.get("STRATUM_TOKEN")
    if not token:
        raise SystemExit("Set STRATUM_TOKEN to a valid API bearer token. It is never written to output.")
    semaphore = asyncio.Semaphore(args.concurrency)
    durations, failures = [], []
    async with httpx.AsyncClient(base_url=args.url, timeout=20,
                                 headers={"Authorization": f"Bearer {token}"}) as client:
        warmup = await client.get(args.path)
        warmup.raise_for_status()
        async def request():
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.get(args.path)
                    if response.status_code != 200:
                        failures.append(response.status_code)
                except httpx.HTTPError:
                    failures.append("network")
                durations.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        await asyncio.gather(*(request() for _ in range(args.requests)))
        elapsed = time.perf_counter() - started
    values = sorted(durations)
    result = {"recorded_at": datetime.now(UTC).isoformat(), "platform": platform.platform(),
              "python": platform.python_version(), "path": args.path,
              "requests": args.requests, "concurrency": args.concurrency,
              "failures": len(failures), "wall_seconds": round(elapsed, 3),
              "requests_per_second": round(args.requests / elapsed, 2),
              "p50_ms": round(statistics.median(values), 2),
              "p95_ms": round(values[min(len(values)-1, int(len(values)*0.95))], 2),
              "max_ms": round(max(values), 2),
              "scope": "Authenticated reads, local development dataset. Not a saturation test."}
    output = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n")
    print(output)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--path", default="/v1/incidents?limit=50")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--output")
    args = parser.parse_args()
    if not 1 <= args.requests <= 100000 or not 1 <= args.concurrency <= 200:
        parser.error("Use 1–100000 requests and 1–200 concurrency")
    asyncio.run(run(args))
