import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const src = (pkg: string) => fileURLToPath(new URL(`./packages/${pkg}/src/index.ts`, import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "@monocle/contracts": src("contracts"),
      "@monocle/core": src("monocle-core"),
      "@monocle/cravat": src("cravat"),
      "@monocle/companion": src("companion"),
      "@monocle/obsidian-plugin": src("obsidian-plugin"),
    },
  },
  test: {
    include: ["packages/*/test/**/*.test.ts", "test/**/*.test.ts"],
  },
});