import { posix, win32 } from "node:path";

/**
 * Default machine-local directory for companion state (conversations). Deliberately outside any vault and outside
 * roaming/synced profile folders, because conversation data must not leave this machine (D05).
 */
export function defaultDataDir(
  platform: NodeJS.Platform,
  env: Readonly<Record<string, string | undefined>>,
  home: string,
): string {
  if (platform === "win32") return win32.join(env.LOCALAPPDATA || win32.join(home, "AppData", "Local"), "Monocle");
  if (platform === "darwin") return posix.join(home, "Library", "Application Support", "Monocle");
  return posix.join(env.XDG_STATE_HOME || posix.join(home, ".local", "state"), "monocle");
}
