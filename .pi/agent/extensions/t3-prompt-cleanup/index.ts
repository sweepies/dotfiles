import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const T3_PREFIX = "mcp__t3-code__";
const T3_SNIPPET = /^- mcp__t3-code__[A-Za-z0-9_.-]+: /;
const T3_GENERIC_RULE = /^- Use mcp__t3-code__[A-Za-z0-9_.-]+ from the t3-code MCP server when the user asks for T3 orchestration that this tool covers\.$/;

function genericGuideline(name: string): string {
  return `Use ${name} from the t3-code MCP server when the user asks for T3 orchestration that this tool covers.`;
}

/** Remove only T3's duplicate catalog lines and exact, generic routing rules. */
export function stripT3PromptDuplicates(prompt: string): string {
  const seen = new Set<string>();
  return prompt.replace(/^<(tools|rules)>\r?\n([\s\S]*?)\r?\n<\/\1>/gm, (section, tag: string, body: string) => {
    // Pi's generated sections precede project context. Leave later examples alone.
    if (seen.has(tag)) return section;
    seen.add(tag);
    const redundant = tag === "tools" ? T3_SNIPPET : T3_GENERIC_RULE;
    const lines = body.split(/\r?\n/);
    const kept = lines.filter((line) => !redundant.test(line));
    if (kept.length === lines.length) return section;
    const newline = section.startsWith(`<${tag}>\r\n`) ? "\r\n" : "\n";
    return `<${tag}>${newline}${kept.join(newline)}${newline}</${tag}>`;
  });
}

type PromptOptions = {
  toolSnippets: Record<string, string>;
  toolGuidelines: Record<string, string[]>;
  forceSystemPrompt?: string;
};

export function cleanPromptOptions(options: PromptOptions): void {
  for (const name of Object.keys(options.toolSnippets)) {
    if (name.startsWith(T3_PREFIX)) delete options.toolSnippets[name];
  }
  for (const [name, guidelines] of Object.entries(options.toolGuidelines)) {
    if (!name.startsWith(T3_PREFIX)) continue;
    const kept = guidelines.filter((rule) => rule !== genericGuideline(name));
    if (kept.length === guidelines.length) continue;
    if (kept.length === 0) delete options.toolGuidelines[name];
    else options.toolGuidelines[name] = kept;
  }
  if (options.forceSystemPrompt !== undefined) {
    options.forceSystemPrompt = stripT3PromptDuplicates(options.forceSystemPrompt);
  }
}

export default function t3PromptCleanup(pi: ExtensionAPI): void {
  pi.on("before_agent_start", (event) => {
    cleanPromptOptions(event.systemPromptOptions);
  });

  // A later extension may force an already-rendered prompt. This final hook
  // handles either ordering without touching tool declarations or execution.
  pi.on("context_with_system", (event) => {
    let changed = false;
    const messages = event.messages.map((message) => {
      if (message.role !== "system") return message;
      const content = stripT3PromptDuplicates(message.content);
      let sections = message.sections;
      let sectionsChanged = false;
      if (sections) {
        const cleaned = { ...sections };
        for (const tag of ["tools", "rules"]) {
          const section = cleaned[tag];
          if (typeof section !== "string") continue;
          cleaned[tag] = stripT3PromptDuplicates(section);
          sectionsChanged ||= cleaned[tag] !== section;
        }
        if (sectionsChanged) sections = cleaned;
      }
      if (content === message.content && !sectionsChanged) return message;
      changed = true;
      if (sectionsChanged) return { ...message, content, sections };
      return { ...message, content };
    });
    if (changed) return { messages };
  });
}
