"""
Per-container resource metrics for the demo infra dashboard.

cAdvisor can't see individual containers inside Docker Desktop's VM (it only
reports top-level cgroups), so the infra dashboard would be empty there. This
tiny exporter instead reads `docker stats` via the Docker API — the same socket
Promtail uses — and exposes per-container CPU%, memory, network throughput,
restart count and up/down as Prometheus gauges. Works the same on Docker Desktop
and on a real Linux host.
"""

from __future__ import annotations

import os
import time

import docker
from prometheus_client import Gauge, start_http_server

PROJECT = os.environ.get("DEMO_PROJECT", "demo")
PORT = int(os.environ.get("EXPORTER_PORT", "9110"))
INTERVAL = int(os.environ.get("EXPORTER_INTERVAL", "5"))

_LABELS = ["name", "service"]
CPU = Gauge("demo_container_cpu_percent", "CPU usage percent", _LABELS)
MEM = Gauge("demo_container_mem_bytes", "Memory usage bytes", _LABELS)
MEM_LIMIT = Gauge("demo_container_mem_limit_bytes", "Memory limit bytes", _LABELS)
RX = Gauge("demo_container_net_rx_bps", "Network receive bytes/sec", _LABELS)
TX = Gauge("demo_container_net_tx_bps", "Network transmit bytes/sec", _LABELS)
RESTARTS = Gauge("demo_container_restarts", "Container restart count", _LABELS)
UP = Gauge("demo_container_up", "1 if the container is running", _LABELS)


def _cpu_percent(s: dict) -> float:
    try:
        cpu = s["cpu_stats"]["cpu_usage"]["total_usage"]
        precpu = s["precpu_stats"]["cpu_usage"]["total_usage"]
        system = s["cpu_stats"].get("system_cpu_usage", 0)
        presystem = s["precpu_stats"].get("system_cpu_usage", 0)
        ncpu = s["cpu_stats"].get("online_cpus") or len(
            s["cpu_stats"]["cpu_usage"].get("percpu_usage") or [1]
        )
        cpu_delta = cpu - precpu
        sys_delta = system - presystem
        if cpu_delta > 0 and sys_delta > 0:
            return (cpu_delta / sys_delta) * ncpu * 100.0
    except (KeyError, TypeError):
        pass
    return 0.0


def _net(s: dict) -> tuple[int, int]:
    rx = tx = 0
    for v in (s.get("networks") or {}).values():
        rx += v.get("rx_bytes", 0)
        tx += v.get("tx_bytes", 0)
    return rx, tx


_GAUGES = [CPU, MEM, MEM_LIMIT, RX, TX, RESTARTS, UP]


def _drop_stale(active: set[tuple[str, str]], previous: set[tuple[str, str]]) -> None:
    """Remove series for containers that have gone away, so the dashboard doesn't
    keep showing a phantom container after it's removed."""
    for name, service in previous - active:
        for g in _GAUGES:
            try:
                g.remove(name, service)
            except KeyError:
                pass


def main() -> None:
    client = docker.DockerClient(base_url="unix://var/run/docker.sock")
    start_http_server(PORT)
    prev: dict[str, tuple[int, int, float]] = {}
    prev_active: set[tuple[str, str]] = set()
    while True:
        try:
            containers = client.containers.list(
                filters={"label": f"com.docker.compose.project={PROJECT}"}
            )
        except Exception:
            time.sleep(INTERVAL)
            continue

        now = time.time()
        active: set[tuple[str, str]] = set()
        for c in containers:
            name = c.name
            service = c.labels.get("com.docker.compose.service", name)
            labels = {"name": name, "service": service}
            active.add((name, service))
            RESTARTS.labels(**labels).set(c.attrs.get("RestartCount", 0))
            UP.labels(**labels).set(1 if c.status == "running" else 0)
            try:
                s = c.stats(stream=False)
            except Exception:
                continue
            CPU.labels(**labels).set(_cpu_percent(s))
            mstats = s.get("memory_stats", {})
            MEM.labels(**labels).set(mstats.get("usage", 0))
            MEM_LIMIT.labels(**labels).set(mstats.get("limit", 0))
            rx, tx = _net(s)
            pr = prev.get(name)
            if pr:
                dt = now - pr[2]
                if dt > 0:
                    RX.labels(**labels).set(max(0.0, (rx - pr[0]) / dt))
                    TX.labels(**labels).set(max(0.0, (tx - pr[1]) / dt))
            prev[name] = (rx, tx, now)

        _drop_stale(active, prev_active)
        prev_active = active
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
