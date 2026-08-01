import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(
  new URL("../assets/page-load-guard.js", import.meta.url),
  "utf8",
);

assert.match(source, /frontend_timeout/);
assert.match(source, /javascript_error/);
assert.match(source, /FAILURE_DELAY_MS\s*=\s*12_000/);
assert.match(source, /classList\.remove\("loading"\)/);

console.log("Page load guard validation passed.");
