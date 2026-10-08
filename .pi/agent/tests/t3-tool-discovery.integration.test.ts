import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, rm, symlink } from "node:fs/promises";
import { createServer } from "node:http";
import { homedir, tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { CORE_TOOLS, T3_PREFIX } from "../extensions/t3-tool-discovery/discovery.ts";

// Tests the installed Pi CLI and T3's unchanged, generated bridge. No LLM/network credentials needed.
const bridge = process.env.T3_PI_BRIDGE_PATH ?? join(homedir(), ".t3/caches/pi-t3-mcp-extension.ts");
const discovery = fileURLToPath(new URL("../extensions/t3-tool-discovery/index.ts", import.meta.url));
const cleanup = fileURLToPath(new URL("../extensions/t3-prompt-cleanup/index.ts", import.meta.url));
const probe = fileURLToPath(new URL("./fixtures/t3-tool-discovery-probe.ts", import.meta.url));
const names = [
  ...[...CORE_TOOLS].map((name) => name.slice(T3_PREFIX.length)),
  "t3_environment_read", "preview_status",
  ...Array.from({ length: 74 }, (_, i) => `fixture_tool_${i}`),
];
const tools = names.map((name) => ({
  name, description: `Original description for ${name}.\nPreserve the original permission and execution semantics.`,
  inputSchema: { type: "object", properties: {}, additionalProperties: false },
}));

async function runProbe(endpoint: string, directory: string, reverse: boolean, denied: boolean, excluded: boolean) {
  // Mirror mise deployment, rather than only loading the physical source file.
  const deployed = join(directory, "t3-tool-discovery");
  await symlink(dirname(discovery), deployed, "dir");
  const extensions = reverse ? [deployed, cleanup, bridge, probe] : [bridge, cleanup, deployed, probe];
  const child = spawn(process.env.PI_DISCOVERY_CLI ?? "pi", [
    "--offline", "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files", "--no-mcp", "--no-session",
    ...(excluded ? ["--exclude-tools", T3_PREFIX + "t3_environment_read"] : []),
    ...extensions.flatMap((path) => ["-e", path]),
    "--provider", "t3-discovery-probe", "--model", "probe", "--print", "Run deterministic T3 discovery probe",
  ], {
    cwd: directory,
    env: {
      ...process.env, PI_CODING_AGENT_DIR: directory, PI_OFFLINE: "1", PI_TELEMETRY: "0",
      T3_MCP_URL: endpoint, T3_MCP_BEARER_TOKEN: "test-only", T3_PI_RUNTIME_MODE: "full-access",
      T3_DISCOVERY_EXPECT_DENIED: denied ? "1" : "0", T3_DISCOVERY_EXPECT_EXCLUDED: excluded ? "1" : "0",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = ""; let stderr = "";
  child.stdout.on("data", (data) => { stdout += data; });
  child.stderr.on("data", (data) => { stderr += data; });
  const timeout = setTimeout(() => child.kill("SIGKILL"), 25000);
  try {
    const code = await new Promise<number | null>((resolve, reject) => { child.on("error", reject); child.on("close", resolve); });
    assert.equal(code, 0, stderr);
    return JSON.parse(stdout.trim());
  } finally { clearTimeout(timeout); }
}

for (const [label, reverse, denied, excluded] of [
  ["bridge loaded first", false, false, false],
  ["discovery loaded first", true, false, false],
  ["original bridge still blocks unapproved calls", false, true, false],
  ["CLI tool exclusions are respected", false, false, true],
] as const) {
  test(`real Pi: ${label}`, { skip: !existsSync(bridge) && "T3 bridge not installed; set T3_PI_BRIDGE_PATH", timeout: 30000 }, async () => {
    const directory = await mkdtemp(join(tmpdir(), "t3-discovery-test-"));
    const calls: unknown[] = [];
    const server = createServer(async (request, response) => {
      try {
        let text = ""; for await (const chunk of request) text += chunk;
        const rpc = JSON.parse(text);
        if (rpc.id === undefined) { response.writeHead(202); response.end(); return; }
        let result: unknown;
        switch (rpc.method) {
          case "initialize": result = { protocolVersion: "2025-06-18", capabilities: { tools: {} }, serverInfo: { name: "test", version: "1" } }; break;
          case "tools/list": result = { tools }; break;
          case "tools/call": calls.push(rpc.params); result = { content: [{ type: "text", text: "fixture-success" }] }; break;
          default: throw new Error(`Unexpected MCP request: ${rpc.method}`);
        }
        response.writeHead(200, { "content-type": "application/json" }); response.end(JSON.stringify({ jsonrpc: "2.0", id: rpc.id, result }));
      } catch (error) { response.writeHead(500); response.end(String(error)); }
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    try {
      const address = server.address(); assert.ok(address && typeof address !== "string");
      const result = await runProbe(`http://127.0.0.1:${address.port}/mcp`, directory, reverse, denied, excluded);
      assert.equal(result.registered, excluded ? 79 : 80); assert.equal(result.initiallyDeclared, 4); assert.equal(result.afterLoading, excluded ? 4 : 5);
      assert.equal(result.schemasUnchanged, true); assert.ok(result.initialWithDiscoveryChars < result.baselineChars);
      assert.equal(result.execution, excluded ? "tool-policy-blocked" : denied ? "permission-blocked" : "success");
      assert.deepEqual(calls, denied || excluded ? [] : [{ name: "t3_environment_read", arguments: {} }]);
    } finally {
      await new Promise<void>((resolve) => server.close(() => resolve()));
      await rm(directory, { recursive: true, force: true });
    }
  });
}
