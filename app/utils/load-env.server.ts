import path from "node:path";
import { config } from "dotenv";

let envLoaded = false;

export function ensureServerEnv() {
  if (envLoaded) return;
  const envPath = path.resolve(process.cwd(), ".env");
  const result = config({ path: envPath });
  if (
    result.error &&
    (result.error as NodeJS.ErrnoException).code !== "ENOENT"
  ) {
    console.warn(`[env] Failed to load ${envPath}:`, result.error);
  }
  envLoaded = true;
}

ensureServerEnv();
