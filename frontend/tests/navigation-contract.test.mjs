import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const packageJson = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const appVue = readFileSync(new URL("../src/App.vue", import.meta.url), "utf8");

assert.ok(packageJson.dependencies["vue-router"], "frontend must depend on vue-router");
assert.match(appVue, /RouterView/, "App.vue must render RouterView");

const routerSource = readFileSync(new URL("../src/router/index.ts", import.meta.url), "utf8");
for (const path of [
  "/upload",
  "/overview",
  "/tree",
  "/diagnosis/structure",
  "/diagnosis/content",
  "/suggestions",
  "/versions"
]) {
  assert.ok(routerSource.includes(path), `router must include ${path}`);
}
