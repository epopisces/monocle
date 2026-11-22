import { Plugin } from "obsidian";

/**
 * Bootstrap entry for Monocle for Obsidian. The panel, companion connection and commands
 * arrive in IMM-46; bundling to `main.js` for installation into a vault is added there too.
 */
export default class MonoclePlugin extends Plugin {
  override async onload(): Promise<void> {}
}
