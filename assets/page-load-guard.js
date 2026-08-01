(() => {
  const FAILURE_DELAY_MS = 12_000;
  let settled = false;

  function text(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
  }

  function showFailure(reason = "frontend_timeout") {
    if (settled) return;
    settled = true;
    document.body.dataset.overallStatus = "unknown";
    text("overallEyebrow", "STATUS DISPLAY ERROR");
    text("overallTitle", "ステータスを表示できません");
    text(
      "overallMessage",
      "APIは応答していますが、画面の表示処理を完了できませんでした。再読み込みしてください。",
    );
    text("lastUpdated", "--:--");
    text("nextRefresh", "再読込待ち");
    text("serviceCount", "--");
    text("operationalCount", "--");
    text("activeIncidentCount", "--");
    text("freshnessText", "表示エラー");

    const serviceGroups = document.getElementById("serviceGroups");
    if (serviceGroups) {
      serviceGroups.innerHTML = `<div class="empty-state"><div><strong>画面の読み込みに失敗しました</strong><p>ページを再読み込みしてください。診断コード: ${reason}</p></div></div>`;
    }

    const refreshButton = document.getElementById("refreshButton");
    refreshButton?.classList.remove("loading");
    if (refreshButton) refreshButton.disabled = false;
  }

  function markSettled() {
    const serviceCount = document.getElementById("serviceCount")?.textContent?.trim();
    if (serviceCount && serviceCount !== "--") settled = true;
  }

  window.addEventListener("error", (event) => {
    const source = String(event.filename || "");
    if (source.includes("/assets/")) showFailure("javascript_error");
  });

  window.addEventListener("unhandledrejection", () => {
    window.setTimeout(markSettled, 0);
  });

  const serviceCount = document.getElementById("serviceCount");
  if (serviceCount) {
    new MutationObserver(markSettled).observe(serviceCount, {
      childList: true,
      characterData: true,
      subtree: true,
    });
  }

  window.setTimeout(() => {
    markSettled();
    if (!settled) showFailure("frontend_timeout");
  }, FAILURE_DELAY_MS);
})();
