const API_PATH = "/api/status-history.json";
const ALLOWED_DAYS = new Set([7, 14, 30]);
const STATUS_COPY = {
  operational: "稼働中",
  maintenance: "メンテナンス",
  degraded: "一部影響",
  outage: "停止",
  unknown: "確認中",
};

const elements = {
  refreshButton: document.querySelector("#refreshButton"),
  rangeButtons: [...document.querySelectorAll("[data-days]")],
  rangeText: document.querySelector("#rangeText"),
  serviceCount: document.querySelector("#serviceCount"),
  impactDayCount: document.querySelector("#impactDayCount"),
  generatedAt: document.querySelector("#generatedAt"),
  historyServiceList: document.querySelector("#historyServiceList"),
  historyIncidentList: document.querySelector("#historyIncidentList"),
  footerTimestamp: document.querySelector("#footerTimestamp"),
  toast: document.querySelector("#toast"),
};

const params = new URLSearchParams(window.location.search);
const initialDays = Number(params.get("days"));
let selectedDays = ALLOWED_DAYS.has(initialDays) ? initialDays : 30;
let toastTimer = null;

function formatDate(value, options = {}) {
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return "--";
  return new Intl.DateTimeFormat("ja-JP", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
    ...options,
  }).format(date);
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return new Intl.DateTimeFormat("ja-JP", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Tokyo",
  }).format(date);
}

function formatAvailability(value) {
  return typeof value === "number" ? `${value.toFixed(value % 1 === 0 ? 0 : 2)}%` : "--";
}

function showToast(message) {
  window.clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.add("visible");
  toastTimer = window.setTimeout(() => elements.toast.classList.remove("visible"), 2600);
}

function setLoading(loading) {
  elements.refreshButton.disabled = loading;
  elements.refreshButton.classList.toggle("loading", loading);
  elements.refreshButton.setAttribute("aria-busy", String(loading));
}

function updateRangeButtons() {
  for (const button of elements.rangeButtons) {
    button.setAttribute("aria-pressed", String(Number(button.dataset.days) === selectedDays));
  }
}

function createHistoryDay(day) {
  const cell = document.createElement("span");
  const status = STATUS_COPY[day.status] ? day.status : "unknown";
  const availability = formatAvailability(day.availability_percent);
  cell.className = "history-day";
  cell.dataset.status = status;
  cell.textContent = new Date(`${day.date}T00:00:00Z`).getUTCDate();
  cell.title = `${formatDate(day.date, { year: "numeric" })}：${STATUS_COPY[status]} / 観測 ${day.samples}件 / 稼働率 ${availability}`;
  cell.setAttribute("aria-label", cell.title);
  return cell;
}

function createServiceCard(service, range) {
  const card = document.createElement("article");
  card.className = "history-card";

  const head = document.createElement("div");
  head.className = "history-card-head";

  const titleWrap = document.createElement("div");
  titleWrap.className = "history-service-title";
  const mark = document.createElement("span");
  mark.className = "history-service-mark";
  mark.textContent = service.name.slice(0, 1).toUpperCase();
  mark.setAttribute("aria-hidden", "true");
  const titleCopy = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent = service.name;
  const description = document.createElement("p");
  description.textContent = `${service.group} · ${service.description}`;
  titleCopy.append(title, description);
  titleWrap.append(mark, titleCopy);

  const metrics = document.createElement("div");
  metrics.className = "history-service-metrics";
  const availabilityMetric = document.createElement("div");
  const availabilityLabel = document.createElement("span");
  availabilityLabel.textContent = "期間内稼働率";
  const availabilityValue = document.createElement("strong");
  availabilityValue.textContent = formatAvailability(service.availability_percent);
  availabilityMetric.append(availabilityLabel, availabilityValue);

  const currentMetric = document.createElement("div");
  const currentLabel = document.createElement("span");
  currentLabel.textContent = "現在の状態";
  const currentValue = document.createElement("strong");
  currentValue.className = "history-current";
  currentValue.dataset.status = STATUS_COPY[service.current_status] ? service.current_status : "unknown";
  currentValue.textContent = STATUS_COPY[currentValue.dataset.status];
  currentMetric.append(currentLabel, currentValue);
  metrics.append(availabilityMetric, currentMetric);
  head.append(titleWrap, metrics);

  const gridWrap = document.createElement("div");
  gridWrap.className = "history-grid-wrap";
  const grid = document.createElement("div");
  grid.className = "history-day-grid";
  grid.style.setProperty("--history-days", String(range.days));
  for (const day of service.days) grid.append(createHistoryDay(day));

  const axis = document.createElement("div");
  axis.className = "history-axis";
  axis.style.setProperty("--history-days", String(range.days));
  const from = document.createElement("span");
  from.textContent = formatDate(range.from_date);
  const to = document.createElement("span");
  to.textContent = `${formatDate(range.to_date)}（今日）`;
  axis.append(from, to);
  gridWrap.append(grid, axis);
  card.append(head, gridWrap);
  return card;
}

function renderIncidents(incidents) {
  elements.historyIncidentList.replaceChildren();
  if (!Array.isArray(incidents) || incidents.length === 0) {
    const state = document.createElement("div");
    state.className = "empty-state";
    const icon = document.createElement("span");
    icon.className = "empty-state-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.innerHTML = '<svg viewBox="0 0 24 24"><path d="m5 12 4 4L19 6"/></svg>';
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = "公開中の障害記録はありません";
    const description = document.createElement("p");
    description.textContent = "現在、この期間に掲載されている障害・メンテナンス情報はありません。";
    copy.append(title, description);
    state.append(icon, copy);
    elements.historyIncidentList.append(state);
    return;
  }

  for (const incident of incidents) {
    const item = document.createElement("article");
    item.className = "incident-item";
    const title = document.createElement("strong");
    title.textContent = String(incident.title || "障害情報");
    const description = document.createElement("p");
    description.textContent = String(incident.message || incident.description || "詳細情報を確認しています。");
    item.append(title, description);
    elements.historyIncidentList.append(item);
  }
}

function renderHistory(data) {
  const range = data.range;
  const services = Array.isArray(data.services) ? data.services : [];
  elements.rangeText.textContent = `${formatDate(range.from_date)} – ${formatDate(range.to_date)}`;
  elements.serviceCount.textContent = String(services.length);
  elements.generatedAt.textContent = formatDateTime(data.generated_at);
  elements.footerTimestamp.textContent = `Updated ${formatDateTime(data.generated_at)}`;

  const impactDates = new Set();
  for (const service of services) {
    for (const day of service.days || []) {
      if (["maintenance", "degraded", "outage"].includes(day.status)) impactDates.add(day.date);
    }
  }
  elements.impactDayCount.textContent = `${impactDates.size}日`;

  elements.historyServiceList.replaceChildren();
  for (const service of services) {
    elements.historyServiceList.append(createServiceCard(service, range));
  }
  if (services.length === 0) {
    const empty = document.createElement("div");
    empty.className = "history-error";
    empty.innerHTML = "<strong>履歴データがありません</strong><p>監視サービスが登録されると、ここに履歴が表示されます。</p>";
    elements.historyServiceList.append(empty);
  }
  renderIncidents(data.incidents);
}

function renderError() {
  elements.historyServiceList.replaceChildren();
  const error = document.createElement("div");
  error.className = "history-error";
  const title = document.createElement("strong");
  title.textContent = "履歴を取得できませんでした";
  const description = document.createElement("p");
  description.textContent = "時間をおいて再度更新してください。現在の稼働状況はトップページから確認できます。";
  error.append(title, description);
  elements.historyServiceList.append(error);
}

async function loadHistory({ announce = false } = {}) {
  setLoading(true);
  updateRangeButtons();
  try {
    const response = await fetch(`${API_PATH}?days=${selectedDays}&t=${Date.now()}`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`status history request failed: ${response.status}`);
    const data = await response.json();
    renderHistory(data);
    if (announce) showToast("稼働履歴を更新しました");
  } catch (error) {
    console.error(error);
    renderError();
    showToast("履歴の取得に失敗しました");
  } finally {
    setLoading(false);
  }
}

elements.refreshButton.addEventListener("click", () => loadHistory({ announce: true }));
for (const button of elements.rangeButtons) {
  button.addEventListener("click", () => {
    const days = Number(button.dataset.days);
    if (!ALLOWED_DAYS.has(days) || days === selectedDays) return;
    selectedDays = days;
    const url = new URL(window.location.href);
    url.searchParams.set("days", String(days));
    window.history.replaceState({}, "", url);
    loadHistory();
  });
}

updateRangeButtons();
loadHistory();
