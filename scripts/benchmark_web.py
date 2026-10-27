#!/usr/bin/env python3
"""Load-test Argus HTTP sessions and record latency plus API CPU/RAM."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import secrets
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import tomllib

import psutil


ROOT = Path(__file__).resolve().parent.parent
PATHS = ("/auth/me", "/actions", "/status")
SATURATION_P95_MS = 1000.0
SATURATION_ERROR_RATE = 0.01


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text(errors="replace").splitlines():
            if line.lower().startswith(("model name", "hardware")):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "not reported by operating system"


def _hardware() -> dict:
    memory = psutil.virtual_memory()
    return {
        "machine": platform.machine(),
        "processor": _cpu_model(),
        "logical_cpu_count": psutil.cpu_count(logical=True),
        "physical_cpu_count": psutil.cpu_count(logical=False),
        "memory_total_bytes": memory.total,
        "memory_total_gib": round(memory.total / 1024**3, 2),
    }


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _json_request(
    url: str,
    method: str = "GET",
    token: str = "",
    payload: dict | None = None,
    extra_headers: dict | None = None,
) -> tuple[int, dict | None]:
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json", **(extra_headers or {})}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = response.read()
            parsed = json.loads(data) if data else None
            return response.status, parsed if isinstance(parsed, dict) else None
    except urllib.error.HTTPError as exc:
        return exc.code, None


def _wait_for_api(base_url: str, process: subprocess.Popen | None, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"API process exited with code {process.returncode} before becoming healthy")
        try:
            status, payload = _json_request(f"{base_url}/health")
            if status == 200 and payload and payload.get("ok"):
                return
        except (OSError, TimeoutError, urllib.error.URLError):
            pass
        time.sleep(0.25)
    raise TimeoutError(f"API did not become healthy at {base_url}/health within {timeout:g}s")


BENCHMARK_CLIENT_HEADER = "X-Benchmark-Client"


def _create_tokens(base_url: str, count: int) -> list[str]:
    run_id = uuid.uuid4().hex[:12]
    tokens = []
    for index in range(count):
        status, payload = _json_request(
            f"{base_url}/auth/signup",
            method="POST",
            # Signup is limited to 10 accounts per address per hour; give each
            # benchmark account its own address through the API's test header.
            extra_headers={BENCHMARK_CLIENT_HEADER: f"10.77.{index // 250}.{index % 250 + 1}"},
            payload={
                "email": f"load-{run_id}-{index}@example.com",
                "display_name": f"Load Session {index}",
                "password": f"Argus-Benchmark-{secrets.token_hex(8)}",
            },
        )
        if status != 201 or not payload or not payload.get("access_token"):
            raise RuntimeError(f"Could not create benchmark account {index}: HTTP {status}")
        tokens.append(payload["access_token"])
    return tokens


def _process_snapshot(process: psutil.Process) -> tuple[float, int]:
    items = [process]
    try:
        items.extend(process.children(recursive=True))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    cpu_seconds = 0.0
    rss_bytes = 0
    for item in items:
        try:
            cpu = item.cpu_times()
            cpu_seconds += cpu.user + cpu.system
            rss_bytes += item.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return cpu_seconds, rss_bytes


def _docker_snapshot(container_id: str) -> tuple[float, int]:
    result = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}|{{.MemUsage}}", container_id],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    cpu_text, memory_text = result.stdout.strip().split("|", 1)
    cpu_percent = float(cpu_text.rstrip("%"))
    used_text = memory_text.split("/", 1)[0].strip()
    match = re.fullmatch(r"([0-9.]+)(B|KiB|MiB|GiB)", used_text)
    if not match:
        raise ValueError(f"Unrecognized Docker memory value: {used_text}")
    scale = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}[match.group(2)]
    return cpu_percent, int(float(match.group(1)) * scale)


def _session_worker(
    base_url: str,
    token: str,
    session_id: str,
    stop_at: float,
    result_rows: list[dict],
    result_lock: threading.Lock,
    run_id: str,
    concurrency: int,
) -> None:
    while time.monotonic() < stop_at:
        for path in PATHS:
            if time.monotonic() >= stop_at:
                return
            started = time.perf_counter()
            status = 0
            error = ""
            try:
                status, _ = _json_request(f"{base_url}{path}", token=token)
                if status != 200:
                    error = f"http_{status}"
            except Exception as exc:
                error = type(exc).__name__
            elapsed_ms = (time.perf_counter() - started) * 1000
            with result_lock:
                result_rows.append({
                    "run_id": run_id,
                    "concurrency": concurrency,
                    "session_id": session_id,
                    "endpoint": path,
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "latency_ms": round(elapsed_ms, 3),
                    "http_status": status,
                    "error": error,
                })
        time.sleep(0.05)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _run_stage(
    base_url: str,
    tokens: list[str],
    concurrency: int,
    duration: float,
    sample_interval: float,
    process: psutil.Process | None,
    container_id: str | None,
    run_id: str,
) -> tuple[dict, list[dict], list[dict]]:
    request_rows: list[dict] = []
    resource_rows: list[dict] = []
    request_lock = threading.Lock()
    if process is not None:
        previous_cpu, _ = _process_snapshot(process)
    else:
        previous_cpu, _ = _docker_snapshot(container_id or "")
    previous_time = time.monotonic()
    stop_at = time.monotonic() + duration
    started_at = datetime.now(timezone.utc).isoformat()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(
                _session_worker,
                base_url,
                tokens[index],
                f"virtual-{index + 1}",
                stop_at,
                request_rows,
                request_lock,
                run_id,
                concurrency,
            )
            for index in range(concurrency)
        ]
        while time.monotonic() < stop_at:
            time.sleep(min(sample_interval, max(0.0, stop_at - time.monotonic())))
            now = time.monotonic()
            if process is not None:
                cpu_value, rss_bytes = _process_snapshot(process)
                cpu_percent = max(0.0, cpu_value - previous_cpu) / max(now - previous_time, 1e-9) * 100
                previous_cpu = cpu_value
            else:
                cpu_percent, rss_bytes = _docker_snapshot(container_id or "")
            resource_rows.append({
                "run_id": run_id,
                "concurrency": concurrency,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(now - (stop_at - duration), 3),
                "cpu_percent_one_core": round(cpu_percent, 3),
                "rss_bytes": rss_bytes,
                "rss_mib": round(rss_bytes / 1024**2, 3),
            })
            previous_time = now
        for future in futures:
            future.result()

    latencies = [row["latency_ms"] for row in request_rows]
    errors = sum(bool(row["error"]) for row in request_rows)
    mean_rss = statistics.fmean(row["rss_bytes"] for row in resource_rows) if resource_rows else 0
    cpu_mean = statistics.fmean(row["cpu_percent_one_core"] for row in resource_rows) if resource_rows else 0
    p95 = _percentile(latencies, 0.95)
    error_rate = errors / len(request_rows) if request_rows else 1.0
    stage = {
        "concurrent_sessions": concurrency,
        "duration_seconds": duration,
        "started_at_utc": started_at,
        "request_count": len(request_rows),
        "error_count": errors,
        "error_rate": round(error_rate, 6),
        "latency_min_ms": round(min(latencies), 3) if latencies else None,
        "latency_mean_ms": round(statistics.fmean(latencies), 3) if latencies else None,
        "latency_p95_ms": round(p95, 3) if p95 is not None else None,
        "latency_max_ms": round(max(latencies), 3) if latencies else None,
        "cpu_mean_percent_one_core": round(cpu_mean, 3),
        "cpu_percent_per_session_one_core": round(cpu_mean / concurrency, 3),
        "rss_mean_bytes": int(mean_rss),
        "rss_mean_mib": round(mean_rss / 1024**2, 3),
        "rss_mean_mib_per_session_including_service_baseline": round(mean_rss / 1024**2 / concurrency, 3),
        "sample_count": len(resource_rows),
        "saturation_threshold_exceeded": bool(
            (p95 is not None and p95 > SATURATION_P95_MS) or error_rate > SATURATION_ERROR_RATE
        ),
    }
    return stage, request_rows, resource_rows


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", default="1,5,10,20,40")
    parser.add_argument("--duration-seconds", type=float, default=20)
    parser.add_argument("--sample-interval", type=float, default=1.0)
    parser.add_argument("--startup-wait", type=float, default=0.25)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs" / "benchmarks")
    parser.add_argument("--compose", action="store_true", help="Build and test an isolated Docker Compose project")
    args = parser.parse_args()
    if args.duration_seconds <= 0 or args.sample_interval <= 0 or args.startup_wait < 0:
        parser.error("duration and sample interval must be positive; startup wait cannot be negative")
    try:
        levels = sorted({int(value.strip()) for value in args.concurrency.split(",")})
    except ValueError:
        parser.error("--concurrency must be a comma-separated list of positive integers")
    if not levels or levels[0] < 1:
        parser.error("--concurrency values must be positive")

    with (ROOT / "pyproject.toml").open("rb") as stream:
        version = tomllib.load(stream)["project"]["version"]
    run_id = uuid.uuid4().hex[:10]
    temp = tempfile.TemporaryDirectory(prefix="argus-web-benchmark-")
    temp_path = Path(temp.name)
    server: subprocess.Popen | None = None
    server_log = None
    container_id = None
    compose_created = False
    compose_project = f"argus-benchmark-{run_id}"
    host_port = _free_port()
    base_url = f"http://127.0.0.1:{host_port}"
    deployment_mode = "docker-compose-postgres-redis" if args.compose else "native-api-sqlite"

    try:
        if args.compose:
            env_file = temp_path / "compose.env"
            env_file.write_text(
                f"ARGUS_API_HOST_PORT={host_port}\nARGUS_DATA_RETENTION_DAYS=90\n"
                f"CLIENT_IP_HEADER={BENCHMARK_CLIENT_HEADER}\n",
                encoding="utf-8",
            )
            command = [
                "docker", "compose", "--project-name", compose_project,
                "--file", str(ROOT / "docker-compose.yml"),
                "--env-file", str(env_file), "up", "--detach", "--build", "api",
            ]
            subprocess.run(command, cwd=ROOT, check=True, timeout=900)
            compose_created = True
            result = subprocess.run(
                ["docker", "compose", "--project-name", compose_project,
                 "--file", str(ROOT / "docker-compose.yml"), "ps", "--quiet", "api"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            container_id = result.stdout.strip()
            if not container_id:
                raise RuntimeError("Docker Compose did not return an API container ID")
        else:
            database = temp_path / "argus-benchmark.sqlite"
            env = os.environ.copy()
            env.update({
                "ARGUS_ENV": "benchmark",
                "ARGUS_DATA_RETENTION_DAYS": "90",
                "DATABASE_URL": f"sqlite:///{database}",
                "REDIS_URL": "redis://127.0.0.1:6379/0",
                "REDIS_REQUIRED": "0",
                "JWT_SECRET": "benchmark-only-secret-not-used-outside-this-run",
                "ARGUS_ENCRYPTION_KEY": "benchmark-only-encryption-key-not-used-outside-this-run",
                "AUTO_CREATE_TABLES": "1",
                "CLIENT_IP_HEADER": BENCHMARK_CLIENT_HEADER,
            })
            server_log = (temp_path / "api.log").open("w", encoding="utf-8")
            server = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", str(host_port)],
                cwd=ROOT,
                env=env,
                stdout=server_log,
                stderr=subprocess.STDOUT,
            )

        _wait_for_api(base_url, server)
        if args.startup_wait:
            time.sleep(args.startup_wait)
        tokens = _create_tokens(base_url, max(levels))
        # Prime application imports and DB connection pools before the idle baseline.
        for path in PATHS:
            _json_request(f"{base_url}{path}", token=tokens[0])
        time.sleep(1)
        if server is not None:
            process = psutil.Process(server.pid)
            baseline_cpu, baseline_rss = _process_snapshot(process)
        elif container_id:
            baseline_cpu, baseline_rss = _docker_snapshot(container_id)
            process = None
        else:
            raise RuntimeError("API process metrics are unavailable")

        stages = []
        request_rows: list[dict] = []
        resource_rows: list[dict] = []
        for level in levels:
            stage, requests, resources = _run_stage(
                base_url,
                tokens,
                level,
                args.duration_seconds,
                args.sample_interval,
                process,
                container_id,
                run_id,
            )
            stages.append(stage)
            request_rows.extend(requests)
            resource_rows.extend(resources)
            if stage["saturation_threshold_exceeded"]:
                break

        raw_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        stem = f"web-{version}-{deployment_mode}-{raw_stamp}"
        args.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = args.output_dir / f"{stem}.json"
        request_csv = args.output_dir / f"{stem}-requests.csv"
        resources_csv = args.output_dir / f"{stem}-resources.csv"
        report = {
            "metadata": {
                "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                "version": version,
                "operating_system": platform.platform(),
                "python_version_used_for_benchmark": platform.python_version(),
                "hardware": _hardware(),
                "deployment_mode": deployment_mode,
                "database": "PostgreSQL in isolated Docker Compose project" if args.compose else "SQLite temporary file",
                "redis": "Redis Compose service" if args.compose else "Optional local Redis; process fallback used if unavailable",
                "scenario_endpoints": list(PATHS),
                "requests_contain_real_user_data": False,
                "saturation_rule": f"first stage with p95 > {SATURATION_P95_MS:g} ms or error rate > {SATURATION_ERROR_RATE:.0%}",
                "baseline_cpu_value": baseline_cpu,
                "baseline_rss_bytes": baseline_rss,
            },
            "stages": stages,
            "raw_samples": {
                "request_count": len(request_rows),
                "resource_sample_count": len(resource_rows),
            },
        }
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _write_csv(request_csv, request_rows, [
            "run_id", "concurrency", "session_id", "endpoint", "timestamp_utc",
            "latency_ms", "http_status", "error",
        ])
        _write_csv(resources_csv, resource_rows, [
            "run_id", "concurrency", "timestamp_utc", "elapsed_seconds",
            "cpu_percent_one_core", "rss_bytes", "rss_mib",
        ])
        print(f"Wrote {json_path}, {request_csv}, and {resources_csv}")
        for stage in stages:
            print(
                f"sessions={stage['concurrent_sessions']} requests={stage['request_count']} "
                f"errors={stage['error_rate']:.2%} p95={stage['latency_p95_ms']}ms "
                f"cpu/session={stage['cpu_percent_per_session_one_core']}% "
                f"rss/session={stage['rss_mean_mib_per_session_including_service_baseline']}MiB"
            )
        return 0
    finally:
        if compose_created:
            subprocess.run(
                ["docker", "compose", "--project-name", compose_project,
                 "--file", str(ROOT / "docker-compose.yml"), "down", "--volumes", "--remove-orphans"],
                cwd=ROOT,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
            )
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        if server_log is not None:
            server_log.close()
        temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
