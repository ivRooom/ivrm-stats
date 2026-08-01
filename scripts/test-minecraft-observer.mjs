import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync(
  new URL("../assets/minecraft-servers.js", import.meta.url),
  "utf8",
);

let observerCallback = null;
let descriptionValue = "未起動";
let descriptionWrites = 0;
let modeValue = "サーバー情報を取得中です";
let modeWrites = 0;

const description = {
  get textContent() {
    return descriptionValue;
  },
  set textContent(value) {
    descriptionWrites += 1;
    descriptionValue = value;
  },
};

const mode = {
  get textContent() {
    return modeValue;
  },
  set textContent(value) {
    modeWrites += 1;
    modeValue = value;
  },
};

const row = {
  matches(selector) {
    return selector === ".service-row";
  },
  querySelector(selector) {
    if (selector === ".service-identity strong") {
      return { textContent: "Minecraft Network" };
    }
    if (selector === ".service-identity p") {
      return description;
    }
    return null;
  },
};

const runtimeContainer = { innerHTML: "" };
const serviceGroups = {};
const refreshButton = { addEventListener() {} };

const runtimePayload = {
  generatedAt: new Date().toISOString(),
  servers: [
    {
      id: "mc-main",
      name: "生活鯖",
      role: "main",
      connection: "mc.ivrm.jp",
      runtimeStatus: "running",
      startability: "started",
      reason: "Minecraftサーバーは起動済みです",
      version: "26.1.2",
      requiredMemoryMb: 4096,
    },
  ],
};

const statusPayload = {
  services: [
    {
      id: "minecraft-network",
      meta: {
        type: "minecraft",
        probeStatus: "reachable",
        serverVersion: "26.1.2",
        latencyMs: 1,
      },
    },
  ],
};

const context = {
  console,
  Date,
  Object,
  Array,
  Number,
  String,
  Promise,
  document: {
    querySelector(selector) {
      if (selector === "#minecraftServerList") return runtimeContainer;
      if (selector === "#minecraftMode") return mode;
      if (selector === "#serviceGroups") return serviceGroups;
      if (selector === "#refreshButton") return refreshButton;
      return null;
    },
    querySelectorAll(selector) {
      return selector === ".service-row" ? [row] : [];
    },
  },
  fetch: async (url) => ({
    ok: true,
    async json() {
      return String(url).startsWith("/api/minecraft-runtime.json")
        ? runtimePayload
        : statusPayload;
    },
  }),
  MutationObserver: class {
    constructor(callback) {
      observerCallback = callback;
    }
    observe() {}
  },
  window: {
    setInterval() {},
    setTimeout() {},
  },
};

vm.runInNewContext(source, context, { filename: "minecraft-servers.js" });
for (let index = 0; index < 5; index += 1) {
  await new Promise((resolve) => setImmediate(resolve));
}

assert.equal(typeof observerCallback, "function");
assert.equal(descriptionValue, "生活鯖（mc-main） · Minecraft 26.1.2");
assert.equal(descriptionWrites, 1, "initial copy should be written exactly once");
assert.equal(modeWrites, 1, "initial mode should be written exactly once");

observerCallback([
  {
    addedNodes: [
      {
        nodeType: 1,
        matches: () => false,
        querySelector: (selector) => selector === ".service-row" ? row : null,
      },
    ],
  },
]);
observerCallback([{ addedNodes: [{ nodeType: 3 }] }]);

assert.equal(
  descriptionWrites,
  1,
  "observer callbacks must not rewrite identical text and schedule another mutation",
);
assert.equal(modeWrites, 1, "observer callbacks must not rewrite identical mode text");

console.log("Minecraft MutationObserver regression test passed.");
