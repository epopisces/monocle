#!/usr/bin/env node
// Stand-in for the Obsidian Curator `create-obsidian-note` script (not installed on the implementing host; see
// IMM-52). Speaks the external renderer contract: a JSON NoteDraft on stdin, `{"content": "<markdown>"}` on stdout,
// a non-zero exit with a message on stderr on failure.
//   --mode=ok     render a capture note (default)
//   --mode=fail   exit 3 as if the template were missing
//   --mode=no-id  render a note that ignores the assigned ID
import { readFileSync } from "node:fs";

const mode = (process.argv.find((a) => a.startsWith("--mode=")) ?? "--mode=ok").slice("--mode=".length);
const draft = JSON.parse(readFileSync(0, "utf8"));

if (mode === "fail") {
  process.stderr.write(`fake-curator: template ${draft.template} is not installed\n`);
  process.exit(3);
}
const fields = Object.entries(draft.fields).map(([k, v]) => `${k}: ${v}`);
const frontmatter = [
  ...(mode === "no-id" ? [] : [`${draft.idField}: ${draft.id}`]),
  `type: ${draft.template}`,
  `title: ${draft.title}`,
  ...fields,
  `created: ${draft.now}`,
];
process.stdout.write(JSON.stringify({ content: ["---", ...frontmatter, "---", `# ${draft.title}`, ""].join("\n") }));
