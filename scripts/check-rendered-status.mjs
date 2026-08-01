import { spawn } from "node:child_process";
import { access, mkdir, mkdtemp, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const targetUrl = process.argv[2] || "https://status.ivrm.jp/";
const outputDir = process.env.OUTPUT_DIR || "/tmp/ivrm-status-browser";
await mkdir(outputDir, { recursive: true });

async function findBrowser() {
  const candidates = [
    process.env.CHROME_PATH,
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      await access(candidate);
      return candidate;
    } catch {
      // Try the next browser path.
    }
  }
  throw new Error("Chrome/Chromium was not found");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithRetry(url, attempts = 50) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(2000) });
      if (response.ok) return response;
      lastError = new Error(`HTTP ${response.status} from ${url}`);
    } catch (error) {
      lastError = error;
    }
    await sleep(200);
  }
  throw lastError || new Error(`Unable to fetch ${url}`);
}

const browserPath = await findBrowser();
const profileDir = await mkdtemp(path.join(os.tmpdir(), "ivrm-status-chrome-"));
const port = 9200 + Math.floor(Math.random() * 500);
const chromeLog = [];

const chrome = spawn(
  browserPath,
  [
    "--headless=new",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--disable-default-apps",
    "--disable-extensions",
    "--disable-sync",
    "--no-first-run",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    "about:blank",
  ],
  { stdio: ["ignore", "ignore", "pipe"] },
);
chrome.stderr.setEncoding("utf8");
chrome.stderr.on("data", (chunk) => chromeLog.push(chunk));

let socket;
const pending = new Map();
let commandId = 0;
const events = {
  console: [],
  exceptions: [],
  logEntries: [],
  loadingFailed: [],
  responses: [],
};

function send(method, params = {}, timeoutMs = 10000) {
  commandId += 1;
  const id = commandId;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`CDP command timed out: ${method}`));
    }, timeoutMs);
    pending.set(id, { resolve, reject, timer, method });
    socket.send(JSON.stringify({ id, method, params }));
  });
}

function serializeRemoteObject(value) {
  if (!value) return null;
  if (Object.hasOwn(value, "value")) return value.value;
  return value.description || value.type || null;
}

try {
  const sourceResponse = await fetch(`${targetUrl}?source_check=${Date.now()}`, {
    signal: AbortSignal.timeout(20000),
  });
  const sourceHtml = await sourceResponse.text();
  await writeFile(path.join(outputDir, "source.html"), sourceHtml, "utf8");
  await writeFile(
    path.join(outputDir, "headers.json"),
    JSON.stringify(Object.fromEntries(sourceResponse.headers.entries()), null, 2),
    "utf8",
  );

  const apiResponse = await fetch(`${targetUrl.replace(/\/$/, "")}/api/status.json?api_check=${Date.now()}`, {
    signal: AbortSignal.timeout(20000),
    headers: { Accept: "application/json" },
  });
  const apiText = await apiResponse.text();
  await writeFile(path.join(outputDir, "status.json"), apiText, "utf8");
  const apiData = JSON.parse(apiText);
  if (!Array.isArray(apiData.services)) throw new Error("Status API did not return services");

  const versionResponse = await fetchWithRetry(`http://127.0.0.1:${port}/json/version`);
  const version = await versionResponse.json();
  const targetsResponse = await fetchWithRetry(`http://127.0.0.1:${port}/json/list`);
  const targets = await targetsResponse.json();
  const pageTarget = targets.find((target) => target.type === "page");
  if (!pageTarget?.webSocketDebuggerUrl) throw new Error("Chrome page target was not found");

  socket = new WebSocket(pageTarget.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("CDP WebSocket connection timed out")), 10000);
    socket.addEventListener("open", () => {
      clearTimeout(timer);
      resolve();
    }, { once: true });
    socket.addEventListener("error", () => {
      clearTimeout(timer);
      reject(new Error("CDP WebSocket connection failed"));
    }, { once: true });
  });

  socket.addEventListener("message", (event) => {
    const message = JSON.parse(String(event.data));
    if (message.id && pending.has(message.id)) {
      const item = pending.get(message.id);
      pending.delete(message.id);
      clearTimeout(item.timer);
      if (message.error) item.reject(new Error(`${item.method}: ${message.error.message}`));
      else item.resolve(message.result);
      return;
    }
    if (message.method === "Runtime.consoleAPICalled") {
      events.console.push({
        type: message.params.type,
        args: message.params.args.map(serializeRemoteObject),
      });
    } else if (message.method === "Runtime.exceptionThrown") {
      events.exceptions.push(message.params.exceptionDetails);
    } else if (message.method === "Log.entryAdded") {
      events.logEntries.push(message.params.entry);
    } else if (message.method === "Network.loadingFailed") {
      events.loadingFailed.push(message.params);
    } else if (message.method === "Network.responseReceived") {
      const response = message.params.response;
      if (response.url.includes("status.ivrm.jp")) {
        events.responses.push({
          url: response.url,
          status: response.status,
          mimeType: response.mimeType,
          protocol: response.protocol,
          fromDiskCache: response.fromDiskCache,
          fromServiceWorker: response.fromServiceWorker,
        });
      }
    }
  });

  await Promise.all([
    send("Page.enable"),
    send("Runtime.enable"),
    send("Log.enable"),
    send("Network.enable"),
  ]);

  const navigationUrl = `${targetUrl}?browser_check=${Date.now()}`;
  await send("Page.navigate", { url: navigationUrl });
  await sleep(15000);

  const evaluated = await send("Runtime.evaluate", {
    expression: `(() => {
      const text = (id) => document.getElementById(id)?.textContent?.trim() ?? null;
      return {
        url: location.href,
        title: document.title,
        readyState: document.readyState,
        visibilityState: document.visibilityState,
        overallTitle: text("overallTitle"),
        overallEyebrow: text("overallEyebrow"),
        overallMessage: text("overallMessage"),
        serviceCount: text("serviceCount"),
        operationalCount: text("operationalCount"),
        activeIncidentCount: text("activeIncidentCount"),
        freshnessText: text("freshnessText"),
        serviceGroups: text("serviceGroups"),
        inlineRendered: Boolean(window.__ivrmInlineStatusRendered),
        bodyDataset: { ...document.body.dataset },
        scripts: Array.from(document.scripts).map((script) => ({ src: script.src, type: script.type, inline: !script.src })),
        resources: performance.getEntriesByType("resource").map((entry) => ({
          name: entry.name,
          duration: Math.round(entry.duration),
          transferSize: entry.transferSize,
          initiatorType: entry.initiatorType,
        })),
      };
    })()`,
    returnByValue: true,
  });
  const pageState = evaluated.result.value;

  const screenshot = await send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  await writeFile(path.join(outputDir, "mobile.png"), Buffer.from(screenshot.data, "base64"));
  await writeFile(path.join(outputDir, "page-state.json"), JSON.stringify(pageState, null, 2), "utf8");
  await writeFile(path.join(outputDir, "browser-events.json"), JSON.stringify(events, null, 2), "utf8");

  console.log(JSON.stringify({
    browser: version.Browser,
    apiServices: apiData.services.length,
    apiOverallStatus: apiData.overall_status,
    pageState,
    exceptions: events.exceptions.length,
    loadingFailed: events.loadingFailed.length,
  }, null, 2));

  if (!/^\d+$/.test(pageState.serviceCount || "")) {
    throw new Error(`Rendered serviceCount is not numeric: ${JSON.stringify(pageState.serviceCount)}`);
  }
  if (!pageState.overallTitle || pageState.overallTitle === "サービス状況を確認しています") {
    throw new Error(`Rendered page did not leave loading state: ${JSON.stringify(pageState.overallTitle)}`);
  }
  if (events.exceptions.length > 0) {
    throw new Error(`Browser reported ${events.exceptions.length} uncaught JavaScript exception(s)`);
  }

  console.log("Rendered UI check passed");
} finally {
  await writeFile(path.join(outputDir, "chrome.log"), chromeLog.join(""), "utf8");
  if (socket?.readyState === WebSocket.OPEN) socket.close();
  chrome.kill("SIGTERM");
  await Promise.race([
    new Promise((resolve) => chrome.once("exit", resolve)),
    sleep(3000),
  ]);
  if (!chrome.killed) chrome.kill("SIGKILL");
}
