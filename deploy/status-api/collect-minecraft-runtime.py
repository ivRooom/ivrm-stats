#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MEMORY_RESERVE_MB = 512


def run(command: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def docker_inspect(name: str) -> dict[str, Any] | None:
    result = run(["docker", "inspect", name])
    if result is None or result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return payload[0] if isinstance(payload, list) and payload else None


def env_map(inspect: dict[str, Any] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in ((inspect or {}).get("Config") or {}).get("Env") or []:
        if isinstance(item, str) and "=" in item:
            key, value = item.split("=", 1)
            result[key] = value
    return result


def parse_memory_mb(value: str | None) -> int | None:
    if not value:
        return None
    raw = value.strip().upper()
    multipliers = {"K": 1 / 1024, "M": 1, "G": 1024, "T": 1024 * 1024}
    try:
        if raw[-1] in multipliers:
            return max(1, round(float(raw[:-1]) * multipliers[raw[-1]]))
        return max(1, round(float(raw) / (1024 * 1024)))
    except ValueError:
        return None


def available_memory_mb() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def mounts_ready(inspect: dict[str, Any] | None) -> bool:
    if not inspect:
        return False
    for mount in inspect.get("Mounts") or []:
        if mount.get("Type") == "bind" and not Path(str(mount.get("Source") or "")).exists():
            return False
    return True


def has_docker_socket(inspect: dict[str, Any] | None) -> bool:
    return bool(inspect) and any(
        mount.get("Destination") == "/var/run/docker.sock"
        for mount in inspect.get("Mounts") or []
    )


def bool_env(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def runtime_state(inspect: dict[str, Any] | None) -> tuple[str, str, bool, bool, int | None]:
    if not inspect:
        return "missing", "none", False, False, None
    state = inspect.get("State") or {}
    exit_code = state.get("ExitCode")
    return (
        str(state.get("Status") or "unknown"),
        str((state.get("Health") or {}).get("Status") or "none"),
        bool(state.get("Running")),
        bool(state.get("OOMKilled")),
        exit_code if isinstance(exit_code, int) else None,
    )


def restart_count(inspect: dict[str, Any] | None) -> int:
    value = (inspect or {}).get("RestartCount")
    return value if isinstance(value, int) else 0


def memory_ready(required_mb: int | None, available_mb: int | None) -> bool | None:
    if required_mb is None or available_mb is None:
        return None
    return available_mb >= required_mb + MEMORY_RESERVE_MB


def published_port(inspect: dict[str, Any] | None, container_port: str) -> bool:
    bindings = ((inspect or {}).get("NetworkSettings") or {}).get("Ports") or {}
    values = bindings.get(container_port)
    return isinstance(values, list) and any(item.get("HostPort") for item in values if isinstance(item, dict))


def public_server(*, server_id: str, name: str, role: str, connection: str, inspect: dict[str, Any] | None, available_mb: int | None, router: dict[str, Any] | None = None) -> dict[str, Any]:
    environment = env_map(inspect)
    state, health, running, oom_killed, exit_code = runtime_state(inspect)
    required_mb = parse_memory_mb(environment.get("MAX_MEMORY") or environment.get("MEMORY"))
    enough_memory = memory_ready(required_mb, available_mb)
    router_state, _, router_running, _, _ = runtime_state(router)
    router_ready = router_running and bool_env(env_map(router).get("AUTO_SCALE_UP")) and has_docker_socket(router)

    if running and health == "starting":
        runtime_status, startability, reason = "starting", "starting", "Minecraftサーバーを起動しています"
    elif running and health == "unhealthy":
        runtime_status, startability, reason = "unhealthy", "started", "コンテナのヘルスチェックに失敗しています"
    elif running:
        runtime_status, startability, reason = "running", "started", "Minecraftサーバーは起動済みです"
    elif inspect is None:
        runtime_status, startability, reason = "missing", "unavailable", "サーバー構成を確認できません"
    elif oom_killed:
        runtime_status, startability, reason = "stopped", "unavailable", "メモリ不足による停止を確認しました"
    elif not mounts_ready(inspect):
        runtime_status, startability, reason = "stopped", "unavailable", "起動に必要なデータを確認できません"
    elif enough_memory is False:
        runtime_status, startability, reason = "stopped", "unavailable", "現在の空きメモリでは安全に起動できません"
    elif role == "resource" and router_ready:
        runtime_status, startability, reason = "sleeping", "startable", "休止中です。接続すると自動起動します"
    else:
        runtime_status, startability, reason = "stopped", "startable", "手動起動できます"

    payload: dict[str, Any] = {
        "id": server_id, "name": name, "role": role, "connection": connection,
        "containerState": state, "health": health, "runtimeStatus": runtime_status,
        "startability": startability, "startable": startability in {"started", "starting", "startable"},
        "reason": reason, "version": environment.get("VERSION") or None,
        "memoryReady": enough_memory, "restartCount": restart_count(inspect), "oomKilled": oom_killed,
    }
    if exit_code is not None:
        payload["lastExitCode"] = exit_code
    if required_mb is not None:
        payload["requiredMemoryMb"] = required_mb
    if role == "resource":
        payload["autoScaleUp"] = router_ready
        payload["routerState"] = router_state
    return payload


def proxy_status(inspect: dict[str, Any] | None) -> dict[str, Any]:
    state, health, running, oom_killed, exit_code = runtime_state(inspect)
    healthy = running and health not in {"unhealthy", "starting"} and published_port(inspect, "25565/tcp")
    payload: dict[str, Any] = {
        "id": "ivrm-velocity", "name": "Minecraft 接続プロキシ", "role": "proxy",
        "connection": "mc.ivrm.jp", "containerState": state, "health": health,
        "runtimeStatus": "running" if healthy else ("starting" if running and health == "starting" else "unhealthy" if running else "stopped"),
        "startability": "started" if running else "unavailable", "startable": running,
        "reason": "Velocityは正常に公開ポートを待受しています" if healthy else "Velocityの稼働状態または公開ポートを確認できません",
        "restartCount": restart_count(inspect), "oomKilled": oom_killed,
        "publicPort": 25565, "publicPortPublished": published_port(inspect, "25565/tcp"),
    }
    if exit_code is not None:
        payload["lastExitCode"] = exit_code
    return payload


def collect() -> dict[str, Any]:
    available_mb = available_memory_mb()
    main = docker_inspect("mc-main")
    velocity = docker_inspect("ivrm-velocity")
    resource = docker_inspect("mc-resource")
    resource_router = docker_inspect("mc-resource-router")
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "topology": {"publicEndpoint": "mc.ivrm.jp:25565", "proxy": "ivrm-velocity", "backend": "mc-main:25565", "legacyPort25566Enabled": False},
        "voiceChat": {"id": "minecraft-voice-chat", "name": "Minecraft ボイスチャット", "protocol": "udp", "port": 24454, "listening": published_port(main, "24454/udp"), "status": "operational" if published_port(main, "24454/udp") else "outage"},
        "servers": [
            proxy_status(velocity),
            public_server(server_id="mc-main", name="生活鯖", role="main", connection="mc.ivrm.jp", inspect=main, available_mb=available_mb),
            public_server(server_id="mc-resource", name="資源鯖", role="resource", connection="mc.ivrm.jp:25999", inspect=resource, router=resource_router, available_mb=available_mb),
        ],
    }


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/opt/ivrm/www/stats/api/minecraft-runtime.json"))
    args = parser.parse_args()
    atomic_write(args.output, collect())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
