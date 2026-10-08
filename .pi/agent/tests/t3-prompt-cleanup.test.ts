import assert from "node:assert/strict";
import test from "node:test";
import t3PromptCleanup, { cleanPromptOptions, stripT3PromptDuplicates } from "../extensions/t3-prompt-cleanup/index.ts";

const name = "mcp__t3-code__t3_environment_read";
const generic = `Use ${name} from the t3-code MCP server when the user asks for T3 orchestration that this tool covers.`;
const tools = `<tools>\n- read: Read files\n- ${name}: Full tool description\n- mcp__other__read: Another MCP tool\n</tools>`;
const rules = `<rules>\n- Use read to examine files\n- ${generic}\n- Never expose secrets\n</rules>`;
const prompt = `Preamble\n\n${tools}\n\n${rules}\n\n## T3 Code orchestration\nKeep permission checks and delegation policy.\n`;
const expected = prompt.replace(`- ${name}: Full tool description\n`, "").replace(`- ${generic}\n`, "");

function options() {
  return {
    toolSnippets: { read: "Read files", [name]: "Full tool description", mcp__other__read: "Another MCP tool" },
    toolGuidelines: { read: ["Use read to examine files"], [name]: [generic], mcp__other__read: ["Other routing rule"] },
    selectedTools: ["read", name, "mcp__other__read"],
    promptGuidelines: ["Never expose secrets"],
    sections: { policy: "Keep permission checks" },
  };
}

test("removes T3 snippets and generic guidelines without changing selected tools or policy", () => {
  const input = options();
  const selected = input.selectedTools;
  const policy = input.sections;
  cleanPromptOptions(input);
  assert.deepEqual(input.toolSnippets, { read: "Read files", mcp__other__read: "Another MCP tool" });
  assert.deepEqual(input.toolGuidelines, { read: ["Use read to examine files"], mcp__other__read: ["Other routing rule"] });
  assert.equal(input.selectedTools, selected);
  assert.equal(input.sections, policy);
  assert.deepEqual(input.promptGuidelines, ["Never expose secrets"]);
});

test("preserves meaningful T3 guidelines and does not match other servers", () => {
  const input = options();
  input.toolGuidelines[name].push("Never ask for secrets in chat");
  input.toolGuidelines.mcp__other__read.push(generic);
  cleanPromptOptions(input);
  assert.deepEqual(input.toolGuidelines[name], ["Never ask for secrets in chat"]);
  assert.deepEqual(input.toolGuidelines.mcp__other__read, ["Other routing rule", generic]);
});

test("cleans an existing forced prompt and leaves other prompt fields intact", () => {
  const input = { ...options(), forceSystemPrompt: prompt };
  cleanPromptOptions(input);
  assert.equal(input.forceSystemPrompt, expected);
});

test("removes only the duplicate lines in the generated tools and rules sections", () => {
  assert.equal(stripT3PromptDuplicates(prompt), expected);
});

test("does not match a tool name or routing text without the exact T3 prefix and rule", () => {
  const unrelated = `<tools>\n- mcp__other__read: Full description\n- read: Mention ${name}\n</tools>\n<rules>\n- ${generic} Additional instruction.\n- Never expose secrets\n</rules>`;
  assert.equal(stripT3PromptDuplicates(unrelated), unrelated);
});

test("preserves the same text outside generated sections and in later project examples", () => {
  const outside = `\n<project_context>\nUser example:\n${tools}\n${rules}\n</project_context>\n- ${generic}\n`;
  assert.equal(stripT3PromptDuplicates(prompt + outside), expected + outside);
});

test("preserves CRLF line endings", () => {
  assert.equal(stripT3PromptDuplicates(prompt.replace(/\n/g, "\r\n")), expected.replace(/\n/g, "\r\n"));
});

test("cleanup is idempotent and unchanged input is preserved", () => {
  assert.equal(stripT3PromptDuplicates(expected), expected);
  assert.equal(stripT3PromptDuplicates("ordinary system prompt"), "ordinary system prompt");
  const input = options();
  cleanPromptOptions(input);
  const after = structuredClone(input);
  cleanPromptOptions(input);
  assert.deepEqual(input, after);
});

type PromptOptions = ReturnType<typeof options> & { forceSystemPrompt?: string };
type Message = {
  role: string;
  content: string;
  sections?: Record<string, string | null>;
  toolsAdded?: unknown[];
  toolsRemoved?: string[];
};
type Hooks = {
  before_agent_start: (event: { systemPromptOptions: PromptOptions }) => unknown;
  context_with_system: (event: { messages: Message[] }) => { messages: Message[] } | undefined;
};

function harness() {
  const hooks: Partial<Hooks> = {};
  t3PromptCleanup({
    on(event: keyof Hooks, handler: Hooks[keyof Hooks]) {
      Object.assign(hooks, { [event]: handler });
    },
  } as unknown as Parameters<typeof t3PromptCleanup>[0]);
  assert.ok(hooks.before_agent_start);
  assert.ok(hooks.context_with_system);
  return hooks as Hooks;
}

test("registers only prompt hooks, with no new tools or permission hooks", () => {
  assert.deepEqual(Object.keys(harness()).sort(), ["before_agent_start", "context_with_system"]);
});

test("final hook cleans a prompt forced by a later extension", () => {
  const hooks = harness();
  const input = options();
  hooks.before_agent_start({ systemPromptOptions: input });
  const system: Message = { role: "system", content: prompt };
  const result = hooks.context_with_system({ messages: [system] });
  assert.equal(result?.messages[0].content, expected);
  assert.equal(system.content, prompt);
});

test("structured transcript cleanup preserves tool declarations, removals, and other sections", () => {
  const hooks = harness();
  const declarations = [{ name, description: "Full tool description", parameters: { type: "object" } }];
  const removals = ["old_tool"];
  const system: Message = {
    role: "system",
    content: "",
    sections: { tools, rules, project_context: tools, custom: null },
    toolsAdded: declarations,
    toolsRemoved: removals,
  };
  const before = structuredClone(system);
  const result = hooks.context_with_system({ messages: [system] });
  const cleaned = result?.messages[0];
  assert.ok(cleaned);
  assert.equal(cleaned.toolsAdded, declarations);
  assert.equal(cleaned.toolsRemoved, removals);
  assert.equal(cleaned.sections?.tools, stripT3PromptDuplicates(tools));
  assert.equal(cleaned.sections?.rules, stripT3PromptDuplicates(rules));
  assert.equal(cleaned.sections?.project_context, tools);
  assert.equal(cleaned.sections?.custom, null);
  assert.deepEqual(system, before);
});

test("leaves user, assistant, tool-result messages and clean system messages unchanged", () => {
  const hooks = harness();
  const clean: Message = { role: "system", content: "ordinary system prompt" };
  const others = ["user", "assistant", "toolResult"].map((role) => ({ role, content: prompt }));
  assert.equal(hooks.context_with_system({ messages: [clean, ...others] }), undefined);
  const dirty: Message = { role: "system", content: prompt };
  const result = hooks.context_with_system({ messages: [dirty, clean, ...others] });
  assert.ok(result);
  assert.equal(result.messages[1], clean);
  others.forEach((message, index) => assert.equal(result.messages[index + 2], message));
});
