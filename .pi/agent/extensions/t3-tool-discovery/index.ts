import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { installDiscovery } from "./discovery.ts";

export default function t3ToolDiscovery(pi: ExtensionAPI): void {
  installDiscovery(pi, Type.Object({
    query: Type.Optional(Type.String({ minLength: 1, maxLength: 300, description: "Search terms matching T3 tool names and descriptions" })),
    names: Type.Optional(Type.Array(Type.String({ minLength: 1 }), { minItems: 1, maxItems: 16, description: "Exact bare or MCP-prefixed tool names; takes precedence over query" })),
    limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 10, description: "Maximum query matches to activate (default 5)" })),
  }));
}
