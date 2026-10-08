import assert from "node:assert/strict";
import test from "node:test";
import { CORE_TOOLS, DISCOVERY_TOOL, findTools, installDiscovery, T3_PREFIX } from "../extensions/t3-tool-discovery/discovery.ts";

type Tool = { name: string; description: string; parameters?: unknown; execute?: unknown };
const optional = T3_PREFIX + "t3_environment_read";
const browser = T3_PREFIX + "preview_snapshot";
const tools: Tool[] = [
  { name: "read", description: "Read files" },
  { name: "compress", description: "Compress context" },
  { name: "mcp__other__read", description: "Read environment browser snapshot" },
  ...[...CORE_TOOLS].map((name) => ({ name, description: "Core orchestration" })),
  { name: optional, description: "Read server environment preferences", parameters: { type: "object" }, execute: Symbol("original") },
  { name: browser, description: "Capture a browser screenshot\nFull meaningful guidance" },
];
type Hook = (event: unknown, ctx: { sessionManager: { getBranch(): unknown[] } }) => void;
type Definition = { name: string; execute(id: string, params: unknown): Promise<{ content: { text: string }[]; details: { loaded: string[] }; isError?: boolean }> };

function harness(initial = tools) {
  const registered = [...initial];
  let active = initial.map((tool) => tool.name);
  let branch: unknown[] = [];
  const blocked = new Set<string>();
  const hooks = new Map<string, Hook>();
  const changes: string[][] = [];
  let definition: Definition;
  installDiscovery({
    on(event: string, handler: Hook) { hooks.set(event, handler); },
    getAllTools() { return registered; },
    getActiveTools() { return [...active]; },
    setActiveTools(names: string[]) { active = names.filter((name) => !blocked.has(name)); changes.push([...active]); },
    appendEntry(customType: string, data: unknown) { branch.push({ type: "custom", customType, data }); },
    registerTool(tool: Definition) { definition = tool; registered.push({ name: tool.name, description: "Discovery" }); active.push(tool.name); },
  } as unknown as Parameters<typeof installDiscovery>[0], {} as Parameters<typeof installDiscovery>[1]);
  const run = (event = "session_start") => hooks.get(event)?.({}, { sessionManager: { getBranch: () => branch } });
  return {
    run, hooks, registered, changes, blocked,
    active: () => active,
    branch: () => branch,
    setBranch(entries: unknown[]) { branch = entries; },
    setActive(names: string[]) { active = names; },
    load: (params: unknown) => definition.execute("test", params),
  };
}

test("startup keeps four T3 core tools and all other active tools, plus discovery", () => {
  const h = harness(); h.run();
  assert.deepEqual(h.active(), ["read", "compress", "mcp__other__read", ...CORE_TOOLS, DISCOVERY_TOOL]);
});

test("never re-registers or changes original T3 schemas and execution", () => {
  const before = tools.map((tool) => ({ ...tool }));
  const h = harness(); h.run();
  assert.deepEqual(h.registered.slice(0, -1), before);
  tools.forEach((tool, index) => assert.equal(h.registered[index], tool));
  assert.deepEqual([...h.hooks.keys()], ["session_start", "before_agent_start"]);
});

test("exact bare and normalized names activate original definitions", async () => {
  const h = harness(); h.run();
  const result = await h.load({ names: ["t3_environment_read", "mcp__t3_code__preview_snapshot"] });
  assert.deepEqual(result.details.loaded, [optional, browser]);
  assert.ok(h.active().includes(optional)); assert.ok(h.active().includes(browser));
  assert.equal(h.registered.find((tool) => tool.name === optional)?.execute, tools.find((tool) => tool.name === optional)?.execute);
});

test("query discovers and activates only matching T3 tools", async () => {
  const h = harness(); h.run();
  const result = await h.load({ query: "browser screenshot" });
  assert.deepEqual(result.details.loaded, [browser]);
  assert.ok(!h.active().includes(optional));
  assert.ok(!result.content[0].text.includes("Full meaningful guidance"));
});

test("ranks name matches first, requires all terms, and honors limits", () => {
  const candidates = [
    { name: T3_PREFIX + "snapshot", description: "Browser capture" },
    { name: T3_PREFIX + "other", description: "Browser snapshot" },
    { name: T3_PREFIX + "mismatch", description: "Browser only" },
  ];
  assert.deepEqual(findTools(candidates, "browser snapshot", 1).map((tool) => tool.name), [T3_PREFIX + "snapshot"]);
  assert.equal(findTools(candidates, "missing").length, 0);
  assert.equal(findTools(candidates, "***").length, 0);
});

test("no match, empty requests, and unknown names never activate anything", async () => {
  const h = harness(); h.run(); const before = [...h.active()];
  assert.deepEqual((await h.load({ query: "zzzz" })).details.loaded, []);
  assert.equal((await h.load({})).isError, true);
  assert.equal((await h.load({ names: ["t3_environment_read", "does_not_exist"] })).isError, true);
  assert.deepEqual(h.active(), before); assert.deepEqual(h.branch(), []);
});

test("loads accumulate without duplicating activation or session entries", async () => {
  const h = harness(); h.run();
  await h.load({ names: [optional, optional] });
  const changeCount = h.changes.length;
  await h.load({ names: [optional] });
  assert.equal(h.changes.length, changeCount); assert.equal(h.branch().length, 1);
  await h.load({ names: [browser] });
  assert.ok(h.active().includes(optional)); assert.ok(h.active().includes(browser));
  assert.equal(h.branch().length, 2);
});

test("persisted branch state restores loaded tools after reload", async () => {
  const h = harness(); h.run(); await h.load({ names: [optional] });
  const resumed = harness(); resumed.setBranch(h.branch()); resumed.run();
  assert.ok(resumed.active().includes(optional)); assert.ok(!resumed.active().includes(browser));
});

test("returning to an earlier branch unloads tools learned only on abandoned branches", async () => {
  const h = harness(); h.run(); await h.load({ names: [optional] });
  const earlier = [...h.branch()]; await h.load({ names: [browser] });
  h.setBranch(earlier); h.run("before_agent_start");
  assert.ok(h.active().includes(optional)); assert.ok(!h.active().includes(browser));
  h.setBranch([]); h.run("before_agent_start"); assert.ok(!h.active().includes(optional));
});

test("ignores unrelated and malformed session entries", () => {
  const h = harness(); h.setBranch([
    null, { type: "custom", customType: "other", data: { names: [optional] } },
    { type: "custom", customType: "t3-tool-discovery", data: { names: ["read"] } },
    { type: "custom", customType: "t3-tool-discovery", data: { names: [false] } },
  ]); h.run(); assert.ok(!h.active().includes(optional));
});

test("standalone Pi with no T3 registrations is unchanged", () => {
  const h = harness(tools.filter((tool) => !tool.name.startsWith(T3_PREFIX))); h.run();
  assert.equal(h.changes.length, 0);
});

test("does not activate inactive unrelated or core tools", () => {
  const h = harness(); h.setActive(["read", optional, DISCOVERY_TOOL]); h.run();
  assert.deepEqual(h.active(), ["read", DISCOVERY_TOOL]);
});

test("before-agent hook narrows a bridge that connected late, and is idempotent", () => {
  const h = harness(); h.setActive(["read", DISCOVERY_TOOL]); h.run();
  h.setActive(h.registered.map((tool) => tool.name)); h.run("before_agent_start");
  assert.ok(!h.active().includes(optional));
  const count = h.changes.length; h.run("before_agent_start"); assert.equal(h.changes.length, count);
});

test("refused activations are reported and never persisted as loaded", async () => {
  const h = harness(); h.run(); h.blocked.add(optional);
  const result = await h.load({ names: [optional] });
  assert.equal(result.isError, true); assert.deepEqual(result.details.loaded, []);
  assert.match(result.content[0].text, /current tool policy/);
  assert.ok(!h.active().includes(optional)); assert.deepEqual(h.branch(), []);
});

test("stale persisted names do not activate unregistered tools", () => {
  const h = harness(); h.setBranch([{ type: "custom", customType: "t3-tool-discovery", data: { names: [T3_PREFIX + "gone"] } }]); h.run();
  assert.ok(!h.active().includes(T3_PREFIX + "gone"));
});
