import path from "node:path";
import { promises as fs } from "node:fs";
import type { RunJobRecord, RunSummary } from "./run-store.server";

const RENDERS_DIR = path.join(process.cwd(), "renders");

export type JobPreview = {
  url: string | null;
  exists: boolean;
  relativePath: string | null;
  fileName: string | null;
};

const fileExists = async (filePath: string): Promise<boolean> => {
  try {
    await fs.access(filePath);
    return true;
  } catch (error) {
    return false;
  }
};

const toSlug = (value?: string | null): string | null => {
  if (!value) return null;
  return value
    .replace(/\.json$/iu, "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/gu, "_")
    .replace(/^_+|_+$/g, "");
};

export function inferRenderDateFolder(summary: RunSummary): string | null {
  const source = summary.createdAt ?? summary.lastActivity;
  if (!source) return null;
  const date = new Date(source);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toISOString().slice(0, 10);
}

export async function buildJobPreview(
  job: RunJobRecord,
  summary: RunSummary,
  dateFolder?: string | null
): Promise<JobPreview> {
  const mode = job.config?.mode ?? summary.mode ?? null;
  const folder = dateFolder ?? inferRenderDateFolder(summary);
  const viewPrefix = job.config?.view_output_prefix ?? null;
  const fabricSlug = toSlug(job.config?.fabric ?? job.config?.fabric_slug);
  const assetSuffix = job.config?.asset_suffix ?? toSlug(job.config?.asset);

  if (!mode || !folder || !viewPrefix || !fabricSlug || !assetSuffix) {
    return { url: null, exists: false, relativePath: null, fileName: null };
  }

  const fileName = `${viewPrefix}-${fabricSlug}-${assetSuffix}.png`;
  const relativePath = path.posix.join(mode, folder, viewPrefix, fileName);
  const absolutePath = path.join(RENDERS_DIR, relativePath);
  const exists = await fileExists(absolutePath);

  return {
    url: exists ? `/renders/${relativePath}` : null,
    exists,
    relativePath: exists ? relativePath : null,
    fileName,
  };
}
