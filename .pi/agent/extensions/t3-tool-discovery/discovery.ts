import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export const T3_PREFIX = "mcp__t3-code__";
export const DISCOVERY_TOOL = "t3_tools";
const ENTRY_TYPE = "t3-tool-discovery";
export const CORE_TOOLS = new Set([
  "orchestrator_capabilities",
  "delegate_task",
  "task_status",
  "task_cancel",
].map((name) => T3_PREFIX + name));

type ToolInfo = { name: string; description: string };
export type DiscoveryRequest = { query?: string; names?: string[]; limit?: number };
type Schema = Parameters<ExtensionAPI["registerTool"]>[0]["parameters"];

function qualifiedName(name: string): string {
  if (name.startsWith("mcp__t3_code__")) return T3_PREFIX + name.slice("mcp__t3_code__".length);
  return name.startsWith(T3_PREFIX) ? name : T3_PREFIX + name;
}

/** Search only live T3 registrations; every query term must match. */
export function findTools(tools: ToolInfo[], query: string, limit = 5): ToolInfo[] {
  const terms = [...new Set(query.toLowerCase().match(/[a-z0-9]+/g) ?? [])];
  if (terms.length === 0) return [];
  return tools.filter((tool) => tool.name.startsWith(T3_PREFIX)).map((tool) => {
    const name = tool.name.slice(T3_PREFIX.length).toLowerCase();
    const description = tool.description.toLowerCase();
    const scores = terms.map((term) => name.includes(term) ? 10 : description.includes(term) ? 1 : 0);
    return { tool, score: scores.every((score) => score > 0) ? scores.reduce<number>((sum, score) => sum + score, 0) : 0 };
  }).filter(({ score }) => score > 0)
    .sort((a, b) => b.score - a.score || a.tool.name.localeCompare(b.tool.name))
    .slice(0, limit).map(({ tool }) => tool);
}

function restoredNames(entries: readonly unknown[]): Set<string> {
  let names: string[] = [];
  for (const entry of entries) {
    if (typeof entry !== "object" || entry === null) continue;
    const record = entry as { type?: string; customType?: string; data?: { names?: unknown } };
    if (record.type !== "custom" || record.customType !== ENTRY_TYPE) continue;
    const value = record.data?.names;
    if (Array.isArray(value) && value.every((name) => typeof name === "string" && name.startsWith(T3_PREFIX))) names = value;
  }
  return new Set(names);
}

/** Uses activation only: never re-registers a T3 tool or wraps its execution. */
export function installDiscovery(pi: ExtensionAPI, parameters: Schema): void {
  let loaded = new Set<string>();
  const narrow = () => {
    const registered = new Set(pi.getAllTools().map((tool) => tool.name));
    const current = pi.getActiveTools();
    const next = current.filter((name) => !name.startsWith(T3_PREFIX) || CORE_TOOLS.has(name) || loaded.has(name));
    for (const name of loaded) if (registered.has(name) && !next.includes(name)) next.push(name);
    if (next.length !== current.length || next.some((name, index) => name !== current[index])) pi.setActiveTools(next);
  };
  const restore = (_event: unknown, ctx: { sessionManager: { getBranch(): readonly unknown[] } }) => {
    loaded = restoredNames(ctx.sessionManager.getBranch());
    narrow();
  };
  pi.on("session_start", restore);
  // Also covers a late bridge retry and restoring an earlier /tree branch.
  pi.on("before_agent_start", restore);

  pi.registerTool({
    name: DISCOVERY_TOOL,
    label: "Discover T3 tools",
    description: "Find and activate T3 Code tools before calling them directly. Use names for exact tool names (bare or MCP-prefixed), or query to search live names and descriptions. Loads up to limit matches (default 5); executes nothing. Loaded tools retain their original schemas and permission checks. Use for browser previews, threads, projects, worktrees, PRs, schedules, secrets, devices, attachments, and HTML rendering when their tools are not declared.",
    promptSnippet: "Find and activate optional T3 tools on demand",
    promptGuidelines: ["If a T3 tool is not declared, load it with t3_tools before calling it. Missing declarations do not mean T3 is unavailable; do not use the shell fallback while t3_tools can load the tool."],
    parameters,
    executionMode: "sequential",
    async execute(_id, params) {
      const request = params as DiscoveryRequest;
      const tools = pi.getAllTools().filter((tool) => tool.name.startsWith(T3_PREFIX));
      const requested = [...new Set((request.names ?? []).map(qualifiedName))];
      const unknown = requested.filter((name) => !tools.some((tool) => tool.name === name));
      if (unknown.length > 0 || (!request.query?.trim() && requested.length === 0)) {
        return {
          content: [{ type: "text", text: unknown.length > 0 ? `Unknown T3 tools: ${unknown.join(", ")}. Search with query to discover available names.` : "Supply a non-empty query or at least one tool name." }],
          details: { loaded: [] },
          isError: true,
        };
      }
      const matches = requested.length > 0
        ? tools.filter((tool) => requested.includes(tool.name))
        : findTools(tools, request.query ?? "", request.limit ?? 5);
      const previous = new Set(loaded);
      for (const tool of matches) loaded.add(tool.name);
      narrow();
      const active = new Set(pi.getActiveTools());
      const blocked = matches.filter((tool) => !active.has(tool.name));
      for (const tool of blocked) loaded.delete(tool.name);
      const enabled = matches.filter((tool) => active.has(tool.name));
      if (enabled.some((tool) => !previous.has(tool.name))) pi.appendEntry(ENTRY_TYPE, { names: [...loaded] });
      const result = enabled.map((tool) => ({ name: tool.name, description: tool.description.split("\n")[0].slice(0, 400) }));
      return {
        content: [{ type: "text", text: blocked.length > 0
          ? JSON.stringify({ loaded: result, unavailable: blocked.map((tool) => tool.name), reason: "Activation was refused by the current tool policy." })
          : result.length > 0 ? JSON.stringify({ loaded: result, next: "Call these tools directly; their full schemas are now declared." }) : "No matching T3 tools. Try fewer terms or an exact name. If T3 has not connected, retry after connection." }],
        details: { loaded: result.map((tool) => tool.name) },
        ...(blocked.length > 0 ? { isError: true } : {}),
      };
    },
  });
}
