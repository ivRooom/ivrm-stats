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


def docker_inspect(name: str) -> dict[str, Any] | None:
    try:
        result = subprocess.run(
            ["docker", "inspect", name],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return payload[0] if isinstance(payload, list) and payload else None


def env_map(inspect: dict[str, Any] | None) -> dict[str, str]:
    values = ((inspect or {}).get("Config") or {}).get("Env") or []
    result: dict[str, str] = {}
    for item in values:
        if isinstance(item, str) and "=" in item:
            key, value = item.split("=", 1)
            result[key] = value
    return result


def parse_memory_mb(value: str | None) -> int | None:
    if not value:
        return None
    raw = value.strip().upper()
    multipliers = {"K": 1 / 1024, "M": 1, "G": 1024, "T": 1024 * 1024}
    suffix = raw[-1]
    try:
        if suffix in multipliers:
            return max(1, round(float(raw[:-1]) * multipliers[suffix]))
        return max(1, round(float(raw) / (1024 * 1024)))
    except ValueError:
        return None


def available_memory_mb() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def mounts_ready(inspect: dict[str, Any] | None) -> bool:
    if not inspect:
        return False
    mounts = inspect.get("Mounts") or []
    for mount in mounts:
        if mount.get("Type") == "bind":
            source = mount.get("Source")
            if not isinstance(source, str) or not Path(source).exists():
                return False
    return True


def has_docker_socket(inspect: dict[str, Any] | None) -> bool:
    if not inspect:
        return False
    return any(
        mount.get("Destination") == "/var/run/docker.sock"
        for mount in inspect.get("Mounts") or []
    )


def bool_env(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def runtime_state(inspect: dict[str, Any] | None) -> tuple[str, str, bool, bool, int | None]:
    if not inspect:
        return "missing", "none", False, False, None
    state = inspect.get("State") or {}
    container_state = str(state.get("Status") or "unknown")
    health = str((state.get("Health") or {}).get("Status") or "none")
    running = bool(state.get("Running"))
    oom_killed = bool(state.get("OOMKilled"))
    exit_code = state.get("ExitCode")
    return container_state, health, running, oom_killed, exit_code if isinstance(exit_code, int) else None


def memory_ready(required_mb: int | None, available_mb: int | None) -> bool | None:
    if required_mb is None or available_mb is None:
        return None
    return available_mb >= required_mb + MEMORY_RESERVE_MB


def public_server(
    *,
    server_id: str,
    name: str,
    role: str,
    connection: str,
    inspect: dict[str, Any] | None,
    router: dict[str, Any] | None = None,
    available_mb: int | None,
) -> dict[str, Any]:
    environment = env_map(inspect)
    router_environment = env_map(router)
    container_state, health, running, oom_killed, exit_code = runtime_state(inspect)
    required_mb = parse_memory_mb(environment.get("MAX_MEMORY") or environment.get("MEMORY"))
    enough_memory = memory_ready(required_mb, available_mb)
    storage_ready = mounts_ready(inspect)

    router_state, _, router_running, _, _ = runtime_state(router)
    autoscale_up = bool_env(router_environment.get("AUTO_SCALE_UP"))
    router_ready = router_running and autoscale_up and has_docker_socket(router)

    if running:
        if health == "starting":
            runtime_status = "starting"
            startability = "starting"
            reason = "Minecraftサーバーを起動しています"
        elif health == "unhealthy":
            runtime_status = "unhealthy"
            startability = "started"
            reason = "コンテナは起動していますがヘルスチェックに失敗しています"
        else:
            runtime_status = "running"
            startability = "started"
            reason = "Minecraftサーバーは起動済みです"
    elif inspect is None:
        runtime_status = "missing"
        startability = "unavailable"
        reason = "サーバー構成を確認できません"
    elif oom_killed:
        runtime_status = "stopped"
        startability = "unavailable"
        reason = "メモリ不足による停止を確認しました"
    elif not storage_ready:
        runtime_status = "stopped"
        startability = "unavailable"
        reason = "起動に必要なデータを確認できません"
    elif enough_memory is False:
        runtime_status = "stopped"
        startability = "unavailable"
        reason = "現在の空きメモリでは安全に起動できません"
    elif role == "resource" and router_ready:
        runtime_status = "sleeping"
        startability = "startable"
        reason = "休止中です。接続すると自動起動します"
    else:
        runtime_status = "stopped"
        startability = "startable" if enough_memory is not False else "unavailable"
        reason = "手動起動できます" if startability == "startable" else "起動条件を満たしていません"

    payload: dict[str, Any] = {
        "id": server_id,
        "name": name,
        "role": role,
        "connection": connection,
        "containerState": container_state,
        "health": health,
        "runtimeStatus": runtime_status,
        "startability": startability,
        "startable": startability in {"started", "starting", "startable"},
        "reason": reason,
        "version": environment.get("VERSION") or None,
        "memoryReady": enough_memory,
    }
    if exit_code is not None:
        payload["lastExitCode"] = exit_code
    if required_mb is not None:
        payload["requiredMemoryMb"] = required_mb
    if role == "resource":
        payload["autoScaleUp"] = router_ready
        payload["routerState"] = router_state
    return payload


def collect() -> dict[str, Any]:
    available_mb = available_memory_mb()
    main = docker_inspect("mc-main")
    resource = docker_inspect("mc-resource")
    resource_router = docker_inspect("mc-resource-router")

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "servers": [
            public_server(
                server_id="mc-main",
                name="生活鯖",
                role="main",
                connection="mc.ivrm.jp",
                inspect=main,
                available_mb=available_mb,
            ),
            public_server(
                server_id="mc-resource",
                name="資源鯖",
                role="resource",
                connection="mc.ivrm.jp:25999",
                inspect=resource,
                router=resource_router,
                available_mb=available_mb,
            ),
        ],
    }


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/opt/ivrm/www/stats/api/minecraft-runtime.json"),
    )
    args = parser.parse_args()
    atomic_write(args.output, collect())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
