const $ = (id) => document.getElementById(id);

const IMPACT_COPY = {
  maintenance: {
    eyebrow: "SCHEDULED MAINTENANCE",
    title: "メンテナンスを実施しています",
    message: "一部サービスで予定されたメンテナンスを実施しています。",
  },
  degraded: {
    eyebrow: "PARTIAL SERVICE IMPACT",
    title: "一部サービスに影響があります",
    message: "サービスは利用できますが、一部機能で遅延や不安定な状態を確認しています。",
  },
  outage: {
    eyebrow: "SERVICE DISRUPTION",
    title: "サービス障害が発生しています",
    message: "現在、利用者影響のある障害を確認しています。復旧状況はこのページで更新します。",
  },
};

const IMPACT_PRIORITY = {
  maintenance: 1,
  degraded: 2,
  outage: 3,
};

function serviceStateFromElement(element) {
  return ["operational", "maintenance", "degraded", "outage", "unknown"]
    .find((status) => element.classList.contains(status)) || "unknown";
}

function serviceNameFromElement(element) {
  return element.closest(".service-row")?.querySelector(".service-identity strong")?.textContent?.trim() || "サービス";
}

function applyHeroCopy(status, copy) {
  document.body.dataset.overallStatus = status;
  $("overallEyebrow").textContent = copy.eyebrow;
  $("overallTitle").textContent = copy.title;
  $("overallMessage").textContent = copy.message;
}

function updateStatusPresentation() {
  const stateElements = [...document.querySelectorAll(".service-state")];
  if (!stateElements.length) return;

  const services = stateElements.map((element) => ({
    name: serviceNameFromElement(element),
    status: serviceStateFromElement(element),
  }));

  const highestImpact = services
    .filter((service) => Object.hasOwn(IMPACT_PRIORITY, service.status))
    .sort((a, b) => IMPACT_PRIORITY[b.status] - IMPACT_PRIORITY[a.status])[0];

  if (highestImpact) {
    applyHeroCopy(highestImpact.status, IMPACT_COPY[highestImpact.status]);
    return;
  }

  const unknownServices = services.filter((service) => service.status === "unknown");
  if (!unknownServices.length) return;

  if (unknownServices.length === services.length) {
    applyHeroCopy("unknown", {
      eyebrow: "STATUS CHECK IN PROGRESS",
      title: "サービスの状態を確認しています",
      message: "監視対象は取得できていますが、最新の稼働データを待っています。",
    });
    return;
  }

  const names = unknownServices.slice(0, 2).map((service) => service.name).join("、");
  const suffix = unknownServices.length > 2 ? `ほか${unknownServices.length - 2}件` : "";
  applyHeroCopy("unknown", {
    eyebrow: "PARTIAL STATUS AVAILABLE",
    title: "一部サービスの状態を確認中です",
    message: `${names}${suffix}の最新状態を確認中です。取得済みのサービスに利用者影響は確認されていません。`,
  });
}

const serviceGroups = $("serviceGroups");
if (serviceGroups) {
  const observer = new MutationObserver(updateStatusPresentation);
  observer.observe(serviceGroups, { childList: true, subtree: true });
  updateStatusPresentation();
}
