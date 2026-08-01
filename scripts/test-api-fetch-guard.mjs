import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source = fs
  .readFileSync(new URL("../assets/api-fetch-guard.js", import.meta.url), "utf8")
  .replace("const API_TIMEOUT_MS = 10_000;", "const API_TIMEOUT_MS = 25;");

const window = {
  location: {
    href: "https://status.ivrm.jp/",
    origin: "https://status.ivrm.jp",
  },
  setTimeout,
  clearTimeout,
  fetch: () => new Promise(() => {}),
};

const context = {
  window,
  URL,
  Request,
  AbortController,
  DOMException,
  Error,
  Promise,
};

vm.createContext(context);
vm.runInContext(source, context);

const startedAt = Date.now();
await assert.rejects(
  window.fetch("/api/status.json"),
  (error) => error?.name === "TimeoutError",
);
const elapsed = Date.now() - startedAt;
assert(elapsed >= 20, `timeout resolved too early: ${elapsed}ms`);
assert(elapsed < 500, `timeout did not settle promptly: ${elapsed}ms`);

console.log(`API fetch guard timeout test passed in ${elapsed}ms.`);
