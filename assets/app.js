const state = {
  current: null,
  history: [],
  metric: "cpu",
  refreshing: false,
  refreshTimer: null,
};

const $ = (id) => document.getElementById(id);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const API = {
  current: "/api/current.json",
  history: "/api/history.json",
};

function createDemoCurrent() {
  const now = new Date();
  return {
    collected_at: now.toISOString(),
    status: "online",
    active_container: "mc-gtnh",
    server: {
      name: "GT New Horizons",
      mode: "GTNH 2.8.4 / GregTech Expert",
      connection: "mc.ivrm.jp",
    },
    players: { online: 0, max: 5, names: [] },
    resources: {
      docker_cpu: "2.42%",
      docker_memory: "4.683GiB / 9GiB",
      docker_net: "142kB / 685kB",
      docker_block: "1.56GB / 2.5GB",
      host_memory: "6.0GiB / 10GiB",
      load_average: "0.38, 0.29, 0.21",
    },
    uptime: { container: "12時間 8分", host: "54日 2時間" },
    versions: {
      minecraft: "Minecraft 1.7.10 / GTNH 2.8.4",
      java: "openjdk version 21.0.11 LTS",
    },
    runtime: {
      os: "Oracle Linux Server 9.7",
      kernel: "Linux 5.15 ARM64",
      cpu_model: "Ampere Altra",
      docker: "28.3.2",
      docker_compose: "2.39.1",
    },
    settings: {
      "online-mode": "true",
      "white-list": "true",
      "max-players": "5",
      "allow-flight": "true",
      "view-distance": "6",
      difficulty: "normal",
    },
    backup: {
      latest_local: {
        file: "minecraft-gtnh-demo.tar.gz",
        size: "444M",
        mtime: new Date(now.getTime() - 6 * 60 * 60 * 1000).toISOString(),
      },
    },
    timers: {
      "mc-backup-s3.timer": { active: "active", next: "03:00 / 15:00" },
      "mc-stats-collector.timer": { active: "active", next: "60秒ごと" },
    },
    demo: true,
  };
}

function createDemoHistory() {
  const now = Date.now();
  return Array.from({ length: 72 }, (_, index) => {
    const wave = Math.sin(index / 7) * 3.2 + Math.sin(index / 2.9) * 1.1;
    return {
      collected_at: new Date(now - (71 - index) * 20 * 60 * 1000).toISOString(),
      status: "online",
      players_online: index % 19 === 0 ? 1 : 0,
      players_max: 5,
      cpu_percent: `${Math.max(1.2, 6 + wave).toFixed(2)}%`,
      memory_usage: `${(4.58 + index * 0.002).toFixed(3)}GiB / 9GiB (${(50.8 + index * 0.025).toFixed(1)}%)`,
    };
  });
}

function parseNumber(value, fallback = 0) {
  const match = String(value ?? "").replace(/,/g, "").match(/-?\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : fallback;
}

function parsePercent(value, fallback = 0) {
  return Math.max(0, Math.min(100, parseNumber(value, fallback)));
}

function parseMemoryPercent(value) {
  const percentMatch = String(value ?? "").match(/\((\d+(?:\.\d+)?)%\)/);
  if (percentMatch) return Number(percentMatch[1]);

  const values = String(value ?? "").match(/(\d+(?:\.\d+)?)\s*(GiB|MiB)\s*\/\s*(\d+(?:\.\d+)?)\s*(GiB|MiB)/i);
  if (!values) return 0;

  const used = toGiB(Number(values[1]), values[2]);
  const total = toGiB(Number(values[3]), values[4]);
  return total > 0 ? (used / total) * 100 : 0;
}

function toGiB(value, unit) {
  return String(unit).toLowerCase() === "mib" ? value / 1024 : value;
}

function formatPercent(value) {
  return `${Number(value || 0).toFixed(value >= 10 ? 1 : 2)}%`;
}

function formatDateTime(value, includeSeconds = false) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("ja-JP", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: includeSeconds ? "2-digit" : undefined,
    hour12: false,
  }).format(date);
}

function formatTime(value) {
  if (!value) return "--:--:--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--:--:--";
  return new Intl.DateTimeFormat("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

function formatHistoryTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--:--";
  return new Intl.DateTimeFormat("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function secondsSince(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return Infinity;
  return Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
}

function freshnessLabel(seconds) {
  if (!Number.isFinite(seconds)) return "更新時刻を取得できません";
  if (seconds < 60) return `${seconds}秒前に更新`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分前に更新`;
  return `${Math.floor(seconds / 3600)}時間前に更新`;
}

async function fetchJson(primary, fallbackFactory) {
  const options = { cache: "no-store", headers: { Accept: "application/json" } };
  const primaryResponse = await fetch(`${primary}?t=${Date.now()}`, options).catch(() => null);
  if (primaryResponse?.ok) return primaryResponse.json();
  return fallbackFactory();
}

function setText(id, value, fallback = "--") {
  const element = $(id);
  if (element) element.textContent = value ?? fallback;
}

function setBoolean(id, value) {
  const element = $(id);
  if (!element) return;
  const normalized = String(value).toLowerCase();
  const isTrue = normalized === "true" || normalized === "on" || normalized === "active";
  element.textContent = isTrue ? "有効" : normalized === "false" || normalized === "off" ? "無効" : value || "--";
  element.classList.toggle("boolean-true", isTrue);
  element.classList.toggle("boolean-false", !isTrue && normalized !== "");
}

function setWidth(id, percent) {
  const element = $(id);
  if (element) element.style.width = `${Math.max(0, Math.min(100, percent || 0))}%`;
}

function setStatusClass(element, status) {
  if (!element) return;
  element.classList.remove("online", "degraded", "offline");
  element.classList.add(status);
}

function timerStatus(timer) {
  const active = String(timer?.active ?? "").toLowerCase();
  return active === "active" ? "active" : active || "unknown";
}

function renderCurrent(data) {
  state.current = data;

  const status = String(data.status || "offline").toLowerCase();
  const collectedSeconds = secondsSince(data.collected_at);
  const stale = collectedSeconds > 300;
  const visualStatus = status === "online" && !stale ? "online" : status === "online" ? "degraded" : "offline";

  const globalStatus = $("globalStatus");
  setStatusClass(globalStatus, visualStatus);
  globalStatus.querySelector("span:last-child").textContent = visualStatus === "online" ? "ALL SYSTEMS OPERATIONAL" : visualStatus === "degraded" ? "DATA DELAYED" : "SERVER OFFLINE";

  const statusPill = $("serverStatusPill");
  setStatusClass(statusPill, visualStatus);
  statusPill.textContent = visualStatus === "online" ? "ONLINE" : visualStatus === "degraded" ? "STALE" : "OFFLINE";

  setText("lastUpdated", formatTime(data.collected_at));
  setText("freshnessText", freshnessLabel(collectedSeconds));
  setText("footerTimestamp", `Updated ${formatDateTime(data.collected_at, true)}`);

  setText("serverName", data.server?.name, "未起動");
  setText("serverMode", data.server?.mode, "サーバー情報なし");
  setText("serverAddress", data.server?.connection, "mc.ivrm.jp");
  setText("activeContainer", data.active_container, "not-running");

  const playersOnline = Number(data.players?.online || 0);
  const playersMax = Number(data.players?.max || data.settings?.["max-players"] || 0);
  setText("playersOnline", playersOnline);
  setText("playersMax", playersMax || "--");
  setWidth("playerProgress", playersMax > 0 ? (playersOnline / playersMax) * 100 : 0);
  setText("playerNames", data.players?.names?.length ? data.players.names.join(" / ") : "現在接続中のプレイヤーはいません");

  const cpu = parsePercent(data.resources?.docker_cpu);
  const memory = parseMemoryPercent(data.resources?.docker_memory);
  setText("cpuValue", formatPercent(cpu));
  setText("memoryValue", formatPercent(memory));
  setText("memoryDetail", data.resources?.docker_memory);
  setWidth("cpuMeter", cpu);
  setWidth("memoryMeter", memory);
  setText("uptimeValue", data.uptime?.container);
  setText("hostUptime", `ホスト稼働: ${data.uptime?.host || "--"}`);
  setText("backupSize", data.backup?.latest_local?.size);
  setText("backupTime", `取得時刻: ${formatDateTime(data.backup?.latest_local?.mtime)}`);
  setText("backupHealth", data.backup?.latest_local ? "VERIFIED" : "MISSING");

  setText("minecraftVersion", data.versions?.minecraft);
  setText("javaVersion", data.versions?.java);
  setText("osVersion", data.runtime?.os);
  setText("cpuModel", data.runtime?.cpu_model);
  setText("dockerVersion", data.runtime?.docker ? `${data.runtime.docker} / Compose ${data.runtime?.docker_compose || "--"}` : "--");
  setText("kernelVersion", data.runtime?.kernel);

  setBoolean("onlineMode", data.settings?.["online-mode"]);
  setBoolean("whitelist", data.settings?.["white-list"]);
  setText("maxPlayersSetting", data.settings?.["max-players"]);
  setText("difficulty", data.settings?.difficulty);
  setText("viewDistance", data.settings?.["view-distance"]);
  setBoolean("allowFlight", data.settings?.["allow-flight"]);

  setText("networkStats", data.resources?.docker_net || "--");

  const backupTimer = data.timers?.["mc-backup-s3.timer"] || {};
  const collectorTimer = data.timers?.["mc-stats-collector.timer"] || {};
  const backupTimerActive = timerStatus(backupTimer) === "active";
  const collectorTimerActive = timerStatus(collectorTimer) === "active";

  setText("backupTimerState", backupTimerActive ? "ACTIVE" : "STOPPED");
  setText("collectorTimerState", collectorTimerActive ? "ACTIVE" : "STOPPED");
  setText("backupTimerNext", `次回: ${backupTimer.next || "--"}`);
  setText("collectorTimerNext", `次回: ${collectorTimer.next || "--"}`);
  $("backupTimerState").classList.toggle("active", backupTimerActive);
  $("collectorTimerState").classList.toggle("active", collectorTimerActive);

  const backupAge = secondsSince(data.backup?.latest_local?.mtime);
  const backupOk = Boolean(data.backup?.latest_local) && backupAge < 60 * 60 * 24;
  const memoryOk = memory < 75;
  const memoryWarn = memory >= 75 && memory < 90;

  updateHealthItem("serverHealthIndicator", visualStatus === "online" ? "ok" : visualStatus === "degraded" ? "warn" : "error", visualStatus === "online" ? "正常に応答しています" : visualStatus === "degraded" ? "データ更新が遅れています" : "応答を確認できません", "serverHealthText");
  updateHealthItem("backupIndicator", backupOk && backupTimerActive ? "ok" : "warn", backupOk ? `最新: ${formatDateTime(data.backup?.latest_local?.mtime)}` : "24時間以内のバックアップなし", "backupTimerText");
  updateHealthItem("collectorIndicator", collectorTimerActive && !stale ? "ok" : "warn", collectorTimerActive ? (stale ? "収集は有効ですがデータが遅延" : "定期収集が稼働中") : "タイマーが停止しています", "collectorTimerText");
  updateHealthItem("memoryIndicator", memoryOk ? "ok" : memoryWarn ? "warn" : "error", `${formatPercent(memory)} 使用中`, "memoryHealthText");

  let score = 100;
  if (visualStatus === "degraded") score -= 18;
  if (visualStatus === "offline") score -= 45;
  if (!backupOk) score -= 15;
  if (!backupTimerActive) score -= 10;
  if (!collectorTimerActive || stale) score -= 12;
  if (memory >= 90) score -= 20;
  else if (memory >= 75) score -= 8;
  score = Math.max(0, score);
  renderHealthScore(score);
}

function updateHealthItem(indicatorId, level, text, textId) {
  const indicator = $(indicatorId);
  indicator.classList.remove("ok", "warn", "error");
  indicator.classList.add(level);
  setText(textId, text);
}

function renderHealthScore(score) {
  const circumference = 2 * Math.PI * 56;
  const offset = circumference * (1 - score / 100);
  const ring = $("healthRing");
  ring.style.strokeDashoffset = String(offset);
  ring.style.stroke = score >= 85 ? "var(--success)" : score >= 65 ? "var(--warning)" : "var(--danger)";
  setText("healthRingValue", score);
  setText("healthScore", score >= 85 ? "HEALTHY" : score >= 65 ? "ATTENTION" : "CRITICAL");
  $("healthScore").style.background = score >= 85 ? "var(--success-soft)" : score >= 65 ? "var(--warning-soft)" : "var(--danger-soft)";
  $("healthScore").style.color = score >= 85 ? "var(--success)" : score >= 65 ? "var(--warning)" : "var(--danger)";
}

function normalizeHistory(history, metric) {
  return history.map((row) => {
    let value = 0;
    if (metric === "cpu") value = parsePercent(row.cpu_percent);
    if (metric === "memory") value = parseMemoryPercent(row.memory_usage);
    if (metric === "players") value = Number(row.players_online || 0);
    return {
      time: row.collected_at,
      label: formatHistoryTime(row.collected_at),
      value,
    };
  }).filter((row) => Number.isFinite(row.value));
}

function renderChart(metric = state.metric) {
  state.metric = metric;
  const svg = $("historyChart");
  const empty = $("chartEmpty");
  const data = normalizeHistory(state.history, metric);

  if (!data.length) {
    svg.innerHTML = "";
    empty.hidden = false;
    setText("chartCurrent", "--");
    setText("chartAverage", "--");
    setText("chartMax", "--");
    return;
  }

  empty.hidden = true;

  const width = 900;
  const height = 330;
  const margin = { top: 26, right: 22, bottom: 44, left: 46 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const rawMax = Math.max(...data.map((row) => row.value), metric === "players" ? 1 : 10);
  const maxValue = metric === "players" ? Math.max(rawMax, state.current?.players?.max || 1) : Math.ceil(rawMax / 10) * 10;
  const x = (index) => margin.left + (plotWidth * index) / Math.max(1, data.length - 1);
  const y = (value) => margin.top + plotHeight - (plotHeight * value) / Math.max(1, maxValue);

  const points = data.map((row, index) => [x(index), y(row.value)]);
  const path = smoothPath(points);
  const areaPath = `${path} L ${points.at(-1)[0]} ${margin.top + plotHeight} L ${points[0][0]} ${margin.top + plotHeight} Z`;

  const yTicks = [0, 0.25, 0.5, 0.75, 1];
  const xTickIndexes = [...new Set([0, Math.floor((data.length - 1) / 2), data.length - 1])];
  const suffix = metric === "players" ? "人" : "%";

  svg.innerHTML = `
    <defs>
      <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--accent)" stop-opacity="0.26" />
        <stop offset="78%" stop-color="var(--accent)" stop-opacity="0.015" />
      </linearGradient>
    </defs>
    ${yTicks.map((ratio) => {
      const tickY = margin.top + plotHeight - plotHeight * ratio;
      const tickValue = maxValue * ratio;
      return `<line class="chart-grid-line" x1="${margin.left}" y1="${tickY}" x2="${width - margin.right}" y2="${tickY}" />
        <text class="chart-axis-label" x="${margin.left - 10}" y="${tickY + 4}" text-anchor="end">${formatTick(tickValue, metric)}</text>`;
    }).join("")}
    <path class="chart-area" d="${areaPath}" />
    <path class="chart-path" d="${path}" />
    ${points.length ? `<circle class="chart-dot" cx="${points.at(-1)[0]}" cy="${points.at(-1)[1]}" r="5" />` : ""}
    ${xTickIndexes.map((index) => `<text class="chart-axis-label" x="${x(index)}" y="${height - 12}" text-anchor="${index === 0 ? "start" : index === data.length - 1 ? "end" : "middle"}">${data[index].label}</text>`).join("")}
  `;

  const values = data.map((row) => row.value);
  const current = values.at(-1) || 0;
  const average = values.reduce((sum, value) => sum + value, 0) / values.length;
  const max = Math.max(...values);
  setText("chartCurrent", `${formatMetricValue(current, metric)}${suffix}`);
  setText("chartAverage", `${formatMetricValue(average, metric)}${suffix}`);
  setText("chartMax", `${formatMetricValue(max, metric)}${suffix}`);

  const first = values[0] || 0;
  const delta = current - first;
  const trendText = Math.abs(delta) < 0.05 ? "STABLE" : `${delta > 0 ? "+" : ""}${formatMetricValue(delta, metric)}${suffix}`;
  setText(metric === "cpu" ? "cpuTrend" : metric === "memory" ? "memoryTrend" : "cpuTrend", trendText);
}

function formatTick(value, metric) {
  return metric === "players" ? String(Math.round(value)) : `${Math.round(value)}%`;
}

function formatMetricValue(value, metric) {
  return metric === "players" ? String(Math.round(value)) : Number(value).toFixed(value >= 10 ? 1 : 2);
}

function smoothPath(points) {
  if (!points.length) return "";
  if (points.length === 1) return `M ${points[0][0]} ${points[0][1]}`;
  const line = points.reduce((path, point, index) => {
    if (index === 0) return `M ${point[0]} ${point[1]}`;
    const previous = points[index - 1];
    const controlX = (previous[0] + point[0]) / 2;
    return `${path} C ${controlX} ${previous[1]}, ${controlX} ${point[1]}, ${point[0]} ${point[1]}`;
  }, "");
  return line;
}

async function refreshData({ notify = false } = {}) {
  if (state.refreshing) return;
  state.refreshing = true;
  $("refreshButton").classList.add("loading");

  try {
    const [current, history] = await Promise.all([
      fetchJson(API.current, createDemoCurrent),
      fetchJson(API.history, createDemoHistory),
    ]);
    state.history = Array.isArray(history) ? history : [];
    renderCurrent(current);
    renderChart(state.metric);
    if (notify) showToast("最新データへ更新しました");
  } catch (error) {
    console.error(error);
    setStatusClass($("globalStatus"), "offline");
    $("globalStatus").querySelector("span:last-child").textContent = "API UNAVAILABLE";
    showToast("ステータスAPIに接続できませんでした");
  } finally {
    state.refreshing = false;
    $("refreshButton").classList.remove("loading");
  }
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 2400);
}

function readStoredTheme() {
  try {
    return localStorage.getItem("ivrm-stats-theme");
  } catch {
    return null;
  }
}

function writeStoredTheme(theme) {
  try {
    localStorage.setItem("ivrm-stats-theme", theme);
  } catch {
    // Storage can be unavailable in strict or embedded browsing contexts.
  }
}

function initializeTheme() {
  const stored = readStoredTheme();
  document.documentElement.dataset.theme = stored || "dark";
}

function toggleTheme() {
  const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  document.documentElement.dataset.theme = next;
  writeStoredTheme(next);
  setTimeout(() => renderChart(state.metric), 0);
}

async function copyAddress() {
  const address = $("serverAddress").textContent.trim();
  try {
    await navigator.clipboard.writeText(address);
    showToast(`${address} をコピーしました`);
  } catch {
    const textArea = document.createElement("textarea");
    textArea.value = address;
    textArea.style.position = "fixed";
    textArea.style.opacity = "0";
    document.body.append(textArea);
    textArea.select();
    document.execCommand("copy");
    textArea.remove();
    showToast(`${address} をコピーしました`);
  }
}

function bindEvents() {
  $("refreshButton").addEventListener("click", () => refreshData({ notify: true }));
  $("themeButton").addEventListener("click", toggleTheme);
  $("copyAddressButton").addEventListener("click", copyAddress);

  $$("[data-metric]").forEach((button) => {
    button.addEventListener("click", () => {
      $$("[data-metric]").forEach((item) => item.setAttribute("aria-selected", String(item === button)));
      renderChart(button.dataset.metric);
    });
  });

  window.addEventListener("resize", debounce(() => renderChart(state.metric), 160));
}

function debounce(fn, wait) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

initializeTheme();
bindEvents();
refreshData();
state.refreshTimer = window.setInterval(refreshData, 60_000);
