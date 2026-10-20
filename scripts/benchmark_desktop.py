#!/usr/bin/env python3
"""Measure the packaged desktop process tree during guided usage scenarios."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import tomllib

import psutil


ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = {
    "idle": (60, "Leave the Argus window open without interacting."),
    "typical": (
        180,
        "Use voice or text for a few short requests and open the ordinary interface panels.",
    ),
    "intense": (
        300,
        "Run one demanding workflow, such as creating a presentation from local source files.",
    ),
}


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


def _process_tree_snapshot(process: psutil.Process) -> tuple[float, int, int, int]:
    candidates = [process]
    try:
        candidates.extend(process.children(recursive=True))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    cpu_seconds = 0.0
    rss_bytes = 0
    count = 0
    for item in candidates:
        try:
            times = item.cpu_times()
            cpu_seconds += times.user + times.system
            rss_bytes += item.memory_info().rss
            count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return cpu_seconds, rss_bytes, count, len(candidates) - 1


def _measure_phase(
    process: psutil.Process,
    name: str,
    duration: float,
    interval: float,
) -> tuple[list[dict], dict]:
    samples: list[dict] = []
    previous_cpu, _, _, _ = _process_tree_snapshot(process)
    previous_time = time.monotonic()
    phase_started = datetime.now(timezone.utc).isoformat()
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
            break
        time.sleep(min(interval, max(0.0, deadline - time.monotonic())))
        now = time.monotonic()
        cpu_seconds, rss_bytes, process_count, child_count = _process_tree_snapshot(process)
        elapsed = max(now - previous_time, 1e-9)
        sample = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "scenario": name,
            "elapsed_seconds": round(now - (deadline - duration), 3),
            "sample_interval_seconds": round(elapsed, 3),
            "cpu_percent_one_core": round(max(0.0, cpu_seconds - previous_cpu) / elapsed * 100, 3),
            "rss_bytes": rss_bytes,
            "rss_mib": round(rss_bytes / 1024**2, 3),
            "process_count": process_count,
            "child_process_count": child_count,
        }
        samples.append(sample)
        previous_cpu = cpu_seconds
        previous_time = now
    phase_status = "measured" if samples else "process_exited_before_sampling"
    return samples, {
        "scenario": name,
        "status": phase_status,
        "requested_duration_seconds": duration,
        "started_at_utc": phase_started,
        "sample_count": len(samples),
        "completed_duration_seconds": samples[-1]["elapsed_seconds"] if samples else 0,
    }


def _write_outputs(out_dir: Path, report: dict, samples: list[dict]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"desktop-{report['metadata']['version']}-{stamp}"
    json_path = out_dir / f"{stem}.json"
    csv_path = out_dir / f"{stem}.csv"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = [
        "timestamp_utc", "scenario", "elapsed_seconds", "sample_interval_seconds",
        "cpu_percent_one_core", "rss_bytes", "rss_mib", "process_count", "child_process_count",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(samples)
    return json_path, csv_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=[*SCENARIOS, "all"], default="idle")
    parser.add_argument("--duration-seconds", type=float, help="Override the default duration for each selected scenario")
    parser.add_argument("--sample-interval", type=float, default=1.0)
    parser.add_argument("--startup-wait", type=float, default=8.0)
    parser.add_argument(
        "--live-api",
        action="store_true",
        help="Allow the app to use an already-configured Gemini key for interactive scenarios",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs" / "benchmarks")
    parser.add_argument("--app-command", nargs="+", help="Override the command (default: dist/ARGUS/ARGUS)")
    args = parser.parse_args()
    if args.sample_interval <= 0 or args.startup_wait < 0:
        parser.error("sample interval must be positive and startup wait cannot be negative")

    command = args.app_command or [str(ROOT / "dist" / "ARGUS" / "ARGUS")]
    command = [str(Path(item) if item.startswith(".") else item) for item in command]
    if not Path(command[0]).is_absolute() and "/" in command[0]:
        command[0] = str((ROOT / command[0]).resolve())
    if not Path(command[0]).exists():
        parser.error(f"app executable not found: {command[0]} (build it with PyInstaller first)")

    with (ROOT / "pyproject.toml").open("rb") as stream:
        version = tomllib.load(stream)["project"]["version"]
    work_dir = tempfile.TemporaryDirectory(prefix="argus-desktop-benchmark-")
    env = os.environ.copy()
    isolated_home = Path(work_dir.name) / "home"
    isolated_home.mkdir(parents=True, exist_ok=True)
    env.update({
        "ARGUS_CLI": "1",
        "ARGUS_SKIP_CLAP_GATE": "1",
        "ARGUS_DATA_DIR": work_dir.name,
    })
    if os.name == "nt":
        env["USERPROFILE"] = str(isolated_home)
        env["APPDATA"] = str(isolated_home / "AppData" / "Roaming")
        env["LOCALAPPDATA"] = str(isolated_home / "AppData" / "Local")
    else:
        env["HOME"] = str(isolated_home)
    if not args.live_api:
        env["PYTHON_KEYRING_BACKEND"] = "keyring.backends.fail.Keyring"
        env["GEMINI_API_KEY"] = ""

    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    app_log_path = args.output_dir / f"desktop-{version}-{log_stamp}-app.log"
    app_log = app_log_path.open("w", encoding="utf-8")
    process_handle = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=app_log,
        stderr=subprocess.STDOUT,
        start_new_session=(os.name != "nt"),
    )
    process = psutil.Process(process_handle.pid)
    time.sleep(args.startup_wait)
    report = {
        "metadata": {
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "version": version,
            "operating_system": platform.platform(),
            "python_version_used_for_benchmark": platform.python_version(),
            "hardware": _hardware(),
            "app_command": [Path(command[0]).name, *command[1:]],
            "sample_interval_seconds": args.sample_interval,
            "network_calls_disabled": not args.live_api,
            "live_api_enabled_by_user": args.live_api,
            "data_directory_is_temporary": True,
            "app_log_file": app_log_path.name,
        },
        "scenario_plan": [],
        "samples": [],
    }
    selected = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    try:
        for name in selected:
            default_duration, instructions = SCENARIOS[name]
            duration = args.duration_seconds if args.duration_seconds is not None else default_duration
            if duration <= 0:
                parser.error("scenario duration must be positive")
            if name == "idle":
                print(f"Scenario idle: {instructions} Sampling for {duration:g}s.", flush=True)
            elif sys.stdin.isatty():
                input(f"Scenario {name}: {instructions}\nPress Enter when ready to start {duration:g}s of sampling. ")
            else:
                report["scenario_plan"].append({
                    "scenario": name,
                    "status": "not_run_non_interactive",
                    "instructions": instructions,
                    "requested_duration_seconds": duration,
                    "sample_count": 0,
                })
                continue
            samples, phase = _measure_phase(process, name, duration, args.sample_interval)
            phase["instructions"] = instructions
            report["scenario_plan"].append(phase)
            report["samples"].extend(samples)
            if phase["status"] != "measured":
                break
    finally:
        if process_handle.poll() is None:
            try:
                if os.name == "nt":
                    process_handle.terminate()
                else:
                    os.killpg(process_handle.pid, signal.SIGTERM)
                process_handle.wait(timeout=5)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                process_handle.kill()
                process_handle.wait(timeout=5)
        app_log.close()
        work_dir.cleanup()

    json_path, csv_path = _write_outputs(args.output_dir, report, report["samples"])
    print(f"Wrote {len(report['samples'])} samples to {json_path} and {csv_path}")
    for phase in report["scenario_plan"]:
        print(f"{phase['scenario']}: {phase['status']} ({phase['sample_count']} samples)")
    return 0 if report["samples"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
