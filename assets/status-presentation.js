const $ = (id) => document.getElementById(id);

const IMPACT_STATUSES = ["outage", "degraded", "maintenance"];

function serviceStateFromElement(element) {
  return ["operational", "maintenance", "degraded", "outage", "unknown"]
    .find((status) => element.classList.contains(status)) || "unknown";
}

function serviceNameFromElement(element) {
  return element.closest(".service-row")?.querySelector(".service-identity strong")?.textContent?.trim() || "サービス";
}

function updateUnknownPresentation() {
  const stateElements = [...document.querySelectorAll(".service-state")];
  if (!stateElements.length) return;

  const services = stateElements.map((element) => ({
    name: serviceNameFromElement(element),
    status: serviceStateFromElement(element),
  }));
  const knownImpact = services.find((service) => IMPACT_STATUSES.includes(service.status));
  if (knownImpact) return;

  const unknownServices = services.filter((service) => service.status === "unknown");
  if (!unknownServices.length) return;

  document.body.dataset.overallStatus = "unknown";

  if (unknownServices.length === services.length) {
    $("overallEyebrow").textContent = "STATUS CHECK IN PROGRESS";
    $("overallTitle").textContent = "サービスの状態を確認しています";
    $("overallMessage").textContent = "監視対象は取得できていますが、最新の稼働データを待っています。";
    return;
  }

  const names = unknownServices.slice(0, 2).map((service) => service.name).join("、");
  const suffix = unknownServices.length > 2 ? `ほか${unknownServices.length - 2}件` : "";
  $("overallEyebrow").textContent = "PARTIAL STATUS AVAILABLE";
  $("overallTitle").textContent = "一部サービスの状態を確認中です";
  $("overallMessage").textContent = `${names}${suffix}の最新状態を確認中です。取得済みのサービスに利用者影響は確認されていません。`;
}

const serviceGroups = $("serviceGroups");
if (serviceGroups) {
  const observer = new MutationObserver(updateUnknownPresentation);
  observer.observe(serviceGroups, { childList: true, subtree: true });
  updateUnknownPresentation();
}
