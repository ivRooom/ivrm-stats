const RUNTIME_PATH = "/api/minecraft-runtime.json";
const STATUS_PATH = "/api/status.json";
const RUNTIME_STALE_MS = 120_000;
const REFRESH_MS = 30_000;

const STATE_COPY = {
  running: "稼働中",
  starting: "起動中",
  sleeping: "休止中",
  stopped: "停止中",
  unhealthy: "応答異常",
  missing: "構成なし",
  unknown: "確認中",
};

const STARTABILITY_COPY = {
  started: "起動済み",
  starting: "起動中",
  startable: "起動可能",
  unavailable: "起動不可",
  unknown: "確認中",
};

let latestMinecraftService = null;
let latestServers = [];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function fetchJson(path) {
  try {
    const response = await fetch(`${path}?t=${Date.now()}`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}

function normalizeServer(server) {
  return {
    id: String(server?.id || "unknown"),
    name: String(server?.name || "Minecraftサーバー"),
    role: String(server?.role || "unknown"),
    connection: String(server?.connection || "--"),
    runtimeStatus: Object.hasOwn(STATE_COPY, server?.runtimeStatus)
      ? server.runtimeStatus
      : "unknown",
    startability: Object.hasOwn(STARTABILITY_COPY, server?.startability)
      ? server.startability
      : "unknown",
    reason: String(server?.reason || "状態を確認しています"),
    version: server?.version ? String(server.version) : null,
    requiredMemoryMb: Number.isFinite(Number(server?.requiredMemoryMb))
      ? Number(server.requiredMemoryMb)
      : null,
  };
}

function markRuntimeStale(servers, generatedAt) {
  const generated = new Date(generatedAt).getTime();
  if (Number.isFinite(generated) && Date.now() - generated <= RUNTIME_STALE_MS) {
    return servers;
  }
  return servers.map((server) => ({
    ...server,
    runtimeStatus: "unknown",
    startability: "unknown",
    reason: "ホスト監視データの更新を待っています",
  }));
}

function mergeMainProbe(servers, minecraftService) {
  const main = servers.find((server) => server.id === "mc-main");
  if (!main || !minecraftService?.meta) return servers;

  const probeStatus = minecraftService.meta.probeStatus;
  if (probeStatus === "reachable") {
    main.runtimeStatus = "running";
    main.startability = "started";
    main.reason = `Minecraft応答あり${minecraftService.meta.latencyMs != null ? `（${minecraftService.meta.latencyMs}ms）` : ""}`;
    main.version = minecraftService.meta.serverVersion || main.version;
  } else if (probeStatus === "unreachable" && main.runtimeStatus === "running") {
    main.runtimeStatus = "unhealthy";
    main.startability = "started";
    main.reason = "コンテナは起動していますがMinecraft応答を確認できません";
  }
  return servers;
}

function stateClass(server) {
  if (server.runtimeStatus === "running") return "operational";
  if (server.runtimeStatus === "sleeping") return "standby";
  if (server.runtimeStatus === "starting") return "maintenance";
  if (["unhealthy", "missing"].includes(server.runtimeStatus)) return "outage";
  return "unknown";
}

function startabilityClass(server) {
  if (server.startability === "started") return "operational";
  if (server.startability === "startable") return "startable";
  if (server.startability === "starting") return "maintenance";
  if (server.startability === "unavailable") return "outage";
  return "unknown";
}

function formatMemory(value) {
  if (!Number.isFinite(value)) return null;
  if (value >= 1024 && value % 1024 === 0) return `${value / 1024}GB`;
  return `${value}MB`;
}

function renderCard(server) {
  const requiredMemory = formatMemory(server.requiredMemoryMb);
  return `
    <article class="minecraft-server-card" data-state="${stateClass(server)}">
      <header>
        <div>
          <span>${escapeHtml(server.role === "main" ? "MAIN SERVER" : "RESOURCE SERVER")}</span>
          <strong>${escapeHtml(server.name)}</strong>
          <small>${escapeHtml(server.id)}</small>
        </div>
        <span class="minecraft-runtime-pill ${stateClass(server)}">${escapeHtml(STATE_COPY[server.runtimeStatus])}</span>
      </header>
      <dl>
        <div><dt>起動可否</dt><dd><span class="minecraft-startability ${startabilityClass(server)}">${escapeHtml(STARTABILITY_COPY[server.startability])}</span></dd></div>
        <div><dt>接続先</dt><dd><code>${escapeHtml(server.connection)}</code></dd></div>
        ${server.version ? `<div><dt>バージョン</dt><dd>${escapeHtml(server.version)}</dd></div>` : ""}
        ${requiredMemory ? `<div><dt>必要メモリ</dt><dd>${escapeHtml(requiredMemory)}</dd></div>` : ""}
      </dl>
      <p>${escapeHtml(server.reason)}</p>
    </article>`;
}

function updateMinecraftCopy(minecraftService, servers) {
  const main = servers.find((server) => server.id === "mc-main");
  const mode = document.querySelector("#minecraftMode");
  if (mode && main) {
    const version = minecraftService?.meta?.serverVersion || main.version;
    mode.textContent = version
      ? `生活鯖（mc-main） · Minecraft ${version}`
      : "生活鯖（mc-main）";
  }

  const rows = [...document.querySelectorAll(".service-row")];
  const minecraftRow = rows.find(
    (row) => row.querySelector(".service-identity strong")?.textContent?.trim() === "Minecraft Network",
  );
  const description = minecraftRow?.querySelector(".service-identity p");
  if (description && main) {
    const version = minecraftService?.meta?.serverVersion || main.version;
    description.textContent = version
      ? `生活鯖（mc-main） · Minecraft ${version}`
      : "生活鯖（mc-main）";
  }
}

function renderRuntimeUnavailable(container) {
  container.innerHTML = '<div class="minecraft-runtime-empty"><strong>サーバー起動可否を取得できません</strong><p>APIの応答を確認できませんでした。30秒後に自動で再取得します。</p></div>';
}

async function loadMinecraftServers() {
  const container = document.querySelector("#minecraftServerList");
  if (!container) return;

  const [runtime, status] = await Promise.all([
    fetchJson(RUNTIME_PATH),
    fetchJson(STATUS_PATH),
  ]);
  const minecraftService = Array.isArray(status?.services)
    ? status.services.find((service) => service.id === "minecraft-network")
    : null;

  let servers = Array.isArray(runtime?.servers)
    ? runtime.servers.map(normalizeServer)
    : [];
  servers = markRuntimeStale(servers, runtime?.generatedAt);
  servers = mergeMainProbe(servers, minecraftService);

  if (!servers.length) {
    renderRuntimeUnavailable(container);
    return;
  }

  latestMinecraftService = minecraftService;
  latestServers = servers;
  container.innerHTML = servers.map(renderCard).join("");
  updateMinecraftCopy(latestMinecraftService, latestServers);
}

const serviceGroups = document.querySelector("#serviceGroups");
if (serviceGroups) {
  const observer = new MutationObserver(() => {
    if (latestServers.length) updateMinecraftCopy(latestMinecraftService, latestServers);
  });
  observer.observe(serviceGroups, { childList: true, subtree: true });
}

loadMinecraftServers();
window.setInterval(loadMinecraftServers, REFRESH_MS);
document.querySelector("#refreshButton")?.addEventListener("click", () => {
  window.setTimeout(loadMinecraftServers, 250);
});
