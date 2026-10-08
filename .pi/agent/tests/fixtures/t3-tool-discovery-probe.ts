// Deterministic provider: validates Pi's real declarations and execution without an LLM call.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { createAssistantMessageEventStream, getCurrentSystemPrompt, getCurrentTools } from "@earendil-works/pi-ai";

const prefix = "mcp__t3-code__";
const target = prefix + "t3_environment_read";
const hash = (value: unknown) => createHash("sha256").update(JSON.stringify(value)).digest("hex");

export default function probe(pi: ExtensionAPI): void {
  let step = 0;
  let originalHash = "";
  let baselineChars = 0;
  let initialChars = 0;
  let initialWithDiscoveryChars = 0;
  let count = 0;
  pi.registerProvider("t3-discovery-probe", {
    api: "t3-discovery-probe",
    baseUrl: "http://127.0.0.1",
    apiKey: "test-only",
    models: [{ id: "probe", name: "Local deterministic probe", reasoning: false, input: ["text"], cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, contextWindow: 200000, maxTokens: 1024 }],
    streamSimple(model, context) {
      const stream = createAssistantMessageEventStream();
      const message = {
        role: "assistant" as const, api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: [] as ({ type: "toolCall"; id: string; name: string; arguments: Record<string, string[]> } | { type: "text"; text: string })[],
        stopReason: "stop" as "stop" | "toolUse",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
        errorMessage: undefined as string | undefined,
      };
      queueMicrotask(() => {
        try {
          const declared = getCurrentTools(context.messages);
          const registered = pi.getAllTools().filter((tool) => tool.name.startsWith(prefix));
          const records = registered.map((tool) => ({ name: tool.name, description: tool.description, parameters: tool.parameters }));
          const declaredT3 = declared.filter((tool) => tool.name.startsWith(prefix));
          assert.ok(getCurrentSystemPrompt(context.messages).includes("## T3 Code orchestration"));
          assert.ok(declared.some((tool) => tool.name === "read"));
          assert.ok(declared.some((tool) => tool.name === "t3_tools"));
          const call = (name: string, args: Record<string, string[]>) => {
            message.content.push({ type: "toolCall", id: `probe-${step}`, name, arguments: args });
            message.stopReason = "toolUse";
          };
          const finish = (execution: string) => message.content.push({ type: "text", text: JSON.stringify({ registered: count, initiallyDeclared: 4, afterLoading: declaredT3.length, schemasUnchanged: true, baselineChars, initialChars, initialWithDiscoveryChars, execution }) });
          if (step === 0) {
            count = registered.length;
            assert.ok(count >= 6);
            originalHash = hash(records);
            baselineChars = JSON.stringify(records).length;
            initialChars = JSON.stringify(declaredT3).length;
            initialWithDiscoveryChars = JSON.stringify(declared.filter((tool) => tool.name.startsWith(prefix) || tool.name === "t3_tools")).length;
            assert.equal(declaredT3.length, 4);
            assert.ok(!declared.some((tool) => tool.name === target));
            call("t3_tools", { names: ["t3_environment_read"] });
          } else if (step === 1 && process.env.T3_DISCOVERY_EXPECT_EXCLUDED === "1") {
            assert.equal(hash(records), originalHash);
            assert.equal(declaredT3.length, 4);
            const result = context.messages.at(-1);
            assert.ok(result?.role === "toolResult");
            assert.equal(result.toolName, "t3_tools"); assert.equal(result.isError, true);
            finish("tool-policy-blocked");
          } else if (step === 1) {
            assert.equal(hash(records), originalHash);
            assert.equal(declaredT3.length, 5);
            const loaded = declared.find((tool) => tool.name === target);
            const original = registered.find((tool) => tool.name === target);
            assert.ok(loaded); assert.ok(original);
            assert.equal(loaded.description, original.description);
            assert.equal(hash(loaded.parameters), hash(original.parameters));
            if (process.env.T3_DISCOVERY_EXPECT_DENIED === "1") process.env.T3_PI_RUNTIME_MODE = "approval-required";
            call(target, {});
          } else {
            assert.equal(step, 2);
            assert.equal(hash(records), originalHash);
            const result = context.messages.at(-1);
            assert.equal(result?.role, "toolResult");
            if (result?.role === "toolResult") {
              assert.equal(result.toolName, target);
              assert.equal(result.isError, process.env.T3_DISCOVERY_EXPECT_DENIED === "1");
            }
            finish(process.env.T3_DISCOVERY_EXPECT_DENIED === "1" ? "permission-blocked" : "success");
          }
          step++;
          stream.push({ type: "start", partial: message });
          const first = message.content[0];
          if (first.type === "toolCall") {
            stream.push({ type: "toolcall_end", contentIndex: 0, toolCall: first, partial: message });
          } else {
            stream.push({ type: "text_end", contentIndex: 0, content: first.text, partial: message });
          }
          stream.push({ type: "done", reason: message.stopReason, message });
        } catch (error) {
          stream.push({ type: "error", reason: "error", error: {
            ...message, stopReason: "error", errorMessage: error instanceof Error ? error.stack : String(error),
          } });
        }
        stream.end();
      });
      return stream;
    },
  });
}
