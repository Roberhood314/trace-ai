from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--p95-ms", type=float, default=750.0)
    args = parser.parse_args()

    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    latencies: list[float] = []
    failures: list[str] = []
    paths = ["/health", "/health/ready", "/public/wanted?limit=10", "/public/gateway/status"]

    async with httpx.AsyncClient(base_url=args.base_url, timeout=10.0) as client:
        async def one(i: int) -> None:
            path = paths[i % len(paths)]
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.get(path)
                    if response.status_code >= 500:
                        failures.append(f"{path}:{response.status_code}")
                except Exception as exc:
                    failures.append(f"{path}:{exc.__class__.__name__}")
                finally:
                    latencies.append((time.perf_counter() - started) * 1000)

        await asyncio.gather(*(one(i) for i in range(args.requests)))

    ordered = sorted(latencies)
    p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)] if ordered else 999999
    mean = statistics.fmean(latencies) if latencies else 0
    print(f"requests={len(latencies)} failures={len(failures)} mean_ms={mean:.1f} p95_ms={p95:.1f}")
    if failures:
        print("sample_failures=", failures[:10])
    return 1 if failures or p95 > args.p95_ms else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
