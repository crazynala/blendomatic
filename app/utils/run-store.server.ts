import path from "node:path";
import { promises as fs } from "node:fs";
import {
  ListObjectsV2Command,
  GetObjectCommand,
  PutObjectCommand,
  DeleteObjectsCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { ensureServerEnv } from "./load-env.server";

ensureServerEnv();

export type RunJobConfig = {
  mode?: string;
  garment?: string;
  fabric?: string;
  asset?: string;
  view?: string;
  view_output_prefix?: string;
  asset_suffix?: string;
  [key: string]: unknown;
};

export type RunJobResult = {
  output_path?: string | null;
  uploaded?: string | null;
  thumbnail?: string | null;
  [key: string]: unknown;
} | null;

export type RunJobRecord = {
  jobId: string;
  sequence?: number;
  status: string;
  worker?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  updatedAt?: string | null;
  config?: RunJobConfig;
  result?: RunJobResult;
};

export type RunSummary = {
  runId: string;
  status: string;
  createdAt?: string;
  createdBy?: string;
  note?: string;
  mode?: string;
  garment?: string;
  allowedWorkers?: string[];
  totalJobs: number;
  completedJobs: number;
  failedJobs: number;
  runningJobs: number;
  pendingJobs: number;
  cancelledJobs: number;
  progressPercent: number;
  lastActivity?: string;
};

export type RunDetail = {
  summary: RunSummary;
  jobs: RunJobRecord[];
  plan: Record<string, unknown>[];
  notes?: string | null;
  metadata: Record<string, unknown> | null;
};

type RunMetadata = {
  run_id: string;
  created_at?: string;
  created_by?: string;
  status?: string;
  note?: string;
  mode?: string;
  garment?: string;
  total_jobs?: number;
  allowed_workers?: string[];
};

type JobFileRecord = {
  job_id: string;
  sequence?: number;
  status: string;
  worker?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  updated_at?: string | null;
  config?: RunJobConfig;
  result?: RunJobResult;
};

const RUNS_ROOT =
  process.env.BLENDOMATIC_RUNS_DIR ?? path.join(process.cwd(), "runs");
const STORE_URI =
  process.env.BLENDOMATIC_RUN_STORE ?? process.env.BLENDOMATIC_S3_STORE;
const USE_S3 = Boolean(STORE_URI && STORE_URI.startsWith("s3://"));

let s3Client: S3Client | null = null;
let bucket: string | null = null;
let basePrefix = "";

if (USE_S3 && STORE_URI) {
  const parsed = parseStoreUri(STORE_URI);
  bucket = parsed.bucket;
  basePrefix = parsed.prefix;
  s3Client = new S3Client({
    region:
      process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || "us-east-1",
  });
}

const RUNS_SUBDIR = basePrefix ? `${basePrefix}/runs` : "runs";

function parseStoreUri(uri: string) {
  const withoutScheme = uri.replace(/^s3:\/\//u, "").replace(/\/+$/u, "");
  const [resolvedBucket, ...rest] = withoutScheme.split("/");
  return {
    bucket: resolvedBucket,
    prefix: rest.join("/").replace(/\/+$/u, ""),
  };
}

const STATE_PATH = path.join(RUNS_ROOT, "state.json");
const RUN_CACHE_ROOT = path.join(RUNS_ROOT, "_worker_cache");

async function safeReadDir(dirPath: string) {
  try {
    return await fs.readdir(dirPath, { withFileTypes: true });
  } catch (error) {
    console.warn(`[run-store] Failed to read dir ${dirPath}:`, error);
    return [];
  }
}

async function safeReadFile(filePath: string): Promise<string | null> {
  try {
    return await fs.readFile(filePath, "utf-8");
  } catch (error) {
    return null;
  }
}

async function safeParseJson<T>(filePath: string): Promise<T | null> {
  const raw = await safeReadFile(filePath);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch (error) {
    console.warn(`[run-store] Failed to parse ${filePath}:`, error);
    return null;
  }
}

function normalizeJob(record: JobFileRecord): RunJobRecord {
  return {
    jobId: record.job_id,
    sequence: record.sequence,
    status: record.status,
    worker: record.worker,
    startedAt: record.started_at,
    finishedAt: record.finished_at,
    updatedAt: record.updated_at,
    config: record.config ?? {},
    result: record.result ?? null,
  };
}

async function loadRunState(): Promise<{ runs: Record<string, any>; default: Record<string, any> }> {
  const fallback = { runs: {}, default: { priority: 100 } };
  try {
    const raw = await safeReadFile(STATE_PATH);
    if (!raw) return fallback;
    const data = JSON.parse(raw) as any;
    if (!data.runs) data.runs = {};
    if (!data.default) data.default = { priority: 100 };
    return data;
  } catch (error) {
    console.warn("[run-store] Failed to load state manifest:", error);
    return fallback;
  }
}

async function saveRunState(data: any) {
  try {
    await fs.mkdir(path.dirname(STATE_PATH), { recursive: true });
    await fs.writeFile(STATE_PATH, JSON.stringify(data, null, 2));
  } catch (error) {
    console.warn("[run-store] Failed to save state manifest:", error);
  }
}

export async function getRunStateEntry(runId: string): Promise<Record<string, any>> {
  const state = await loadRunState();
  return state.runs?.[runId] ?? {};
}

export async function setRunPaused(runId: string, paused: boolean): Promise<void> {
  const state = await loadRunState();
  state.runs = state.runs || {};
  state.runs[runId] = { ...(state.runs[runId] ?? {}), paused };
  await saveRunState(state);
}

export async function setAllowedWorkers(runId: string, allowed: string[]): Promise<void> {
  const state = await loadRunState();
  state.runs = state.runs || {};
  state.runs[runId] = { ...(state.runs[runId] ?? {}), allowed_workers: allowed };
  await saveRunState(state);
}

export async function removeRunStateEntry(runId: string): Promise<void> {
  const state = await loadRunState();
  if (state.runs?.[runId]) {
    delete state.runs[runId];
    await saveRunState(state);
  }
}

function computeJobStats(
  jobs: RunJobRecord[] | null,
  fallbackTotal: number
): {
  totalJobs: number;
  completedJobs: number;
  failedJobs: number;
  runningJobs: number;
  pendingJobs: number;
  cancelledJobs: number;
  progressPercent: number;
  lastActivity?: string;
} {
  const totalJobs = jobs?.length ?? fallbackTotal ?? 0;
  if (!jobs || jobs.length === 0) {
    return {
      totalJobs,
      completedJobs: 0,
      failedJobs: 0,
      runningJobs: 0,
      pendingJobs: totalJobs,
      cancelledJobs: 0,
      progressPercent: 0,
    };
  }

  let completedJobs = 0;
  let failedJobs = 0;
  let runningJobs = 0;
  let cancelledJobs = 0;
  let lastActivity: number | undefined;

  for (const job of jobs) {
    const status = (job.status ?? "").toLowerCase();
    if (["succeeded", "completed", "success", "done"].includes(status)) {
      completedJobs += 1;
    } else if (["failed", "error", "errored", "dead"].includes(status)) {
      failedJobs += 1;
    } else if (["running", "in_progress", "working"].includes(status)) {
      runningJobs += 1;
    } else if (
      ["cancelled", "canceled", "aborted", "stopped"].includes(status)
    ) {
      cancelledJobs += 1;
    }

    const candidates = [job.finishedAt, job.updatedAt, job.startedAt]
      .filter(Boolean)
      .map((value) => Date.parse(value as string))
      .filter((value) => Number.isFinite(value));
    if (candidates.length) {
      const maxValue = Math.max(...candidates);
      if (!lastActivity || maxValue > lastActivity) {
        lastActivity = maxValue;
      }
    }
  }

  const counted = completedJobs + failedJobs + runningJobs + cancelledJobs;
  const pendingJobs = Math.max(totalJobs - counted, 0);
  const progressPercent = totalJobs
    ? Math.min(100, Math.round((completedJobs / totalJobs) * 100))
    : 0;

  return {
    totalJobs,
    completedJobs,
    failedJobs,
    runningJobs,
    pendingJobs,
    cancelledJobs,
    progressPercent,
    lastActivity: lastActivity
      ? new Date(lastActivity).toISOString()
      : undefined,
  };
}

async function listLocalRunIds(): Promise<string[]> {
  const entries = await safeReadDir(RUNS_ROOT);
  return entries
    .filter((entry) => entry.isDirectory() && /^\d+$/.test(entry.name))
    .map((entry) => entry.name)
    .sort((a, b) => b.localeCompare(a));
}

async function listS3RunIds(): Promise<string[]> {
  if (!s3Client || !bucket) return [];
  const ids = new Set<string>();
  const prefix = RUNS_SUBDIR.replace(/\/+$/u, "") + "/";
  let continuationToken: string | undefined;

  do {
    const command = new ListObjectsV2Command({
      Bucket: bucket,
      Prefix: prefix,
      Delimiter: "/",
      ContinuationToken: continuationToken,
    });
    const page = await s3Client.send(command);
    page.CommonPrefixes?.forEach((entry) => {
      const value = entry.Prefix?.slice(prefix.length).replace(/\/+$/u, "");
      if (value) ids.add(value);
    });
    page.Contents?.forEach((obj) => {
      if (!obj.Key) return;
      const remainder = obj.Key.slice(prefix.length);
      const match = remainder.match(/^(\d{4,})\//u);
      if (match && match[1]) {
        ids.add(match[1]);
      }
    });
    continuationToken = page.NextContinuationToken;
  } while (continuationToken);

  return Array.from(ids).sort((a, b) => b.localeCompare(a));
}

async function streamToString(body: unknown): Promise<string> {
  if (!body) return "";
  const transformToString = (
    body as { transformToString?: () => Promise<string> }
  ).transformToString;
  if (transformToString) {
    return await transformToString.call(body);
  }
  const stream = body as NodeJS.ReadableStream;
  const chunks: Buffer[] = [];
  return await new Promise((resolve, reject) => {
    stream
      .on("data", (chunk) => chunks.push(Buffer.from(chunk)))
      .once("end", () => resolve(Buffer.concat(chunks).toString("utf-8")))
      .once("error", reject);
  });
}

async function readS3Json<T>(key: string): Promise<T | null> {
  if (!s3Client || !bucket) return null;
  try {
    const command = new GetObjectCommand({ Bucket: bucket, Key: key });
    const result = await s3Client.send(command);
    const payload = await streamToString(result.Body);
    return JSON.parse(payload) as T;
  } catch (error) {
    console.warn(`[run-store] Failed to read S3 key ${key}:`, error);
    return null;
  }
}

async function readS3Text(key: string): Promise<string | null> {
  if (!s3Client || !bucket) return null;
  try {
    const command = new GetObjectCommand({ Bucket: bucket, Key: key });
    const result = await s3Client.send(command);
    return await streamToString(result.Body);
  } catch (error) {
    return null;
  }
}

async function loadLocalRun(runId: string) {
  const runDir = path.join(RUNS_ROOT, runId);
  const metadata = await safeParseJson<RunMetadata>(
    path.join(runDir, "run.json")
  );
  const jobsRaw = await safeParseJson<JobFileRecord[]>(
    path.join(runDir, "jobs.json")
  );
  const jobs = jobsRaw?.map(normalizeJob) ?? [];
  const plan =
    (await safeParseJson<Record<string, unknown>[]>(
      path.join(runDir, "plan.json")
    )) ?? [];
  const notes = await safeReadFile(path.join(runDir, "notes.md"));
  return { metadata, jobs, plan, notes };
}

async function loadS3Run(runId: string) {
  const baseKey = `${RUNS_SUBDIR.replace(/\/+$/u, "")}/${runId}`;
  const metadata = await readS3Json<RunMetadata>(`${baseKey}/run.json`);
  const jobsRaw = await readS3Json<JobFileRecord[]>(`${baseKey}/jobs.json`);
  const jobs = jobsRaw?.map(normalizeJob) ?? [];
  const plan =
    (await readS3Json<Record<string, unknown>[]>(`${baseKey}/plan.json`)) ?? [];
  const notes = await readS3Text(`${baseKey}/notes.md`);
  return { metadata, jobs, plan, notes };
}

async function loadRunBundle(runId: string) {
  if (USE_S3 && s3Client && bucket) {
    return await loadS3Run(runId);
  }
  return await loadLocalRun(runId);
}

function buildSummary(
  runId: string,
  metadata: RunMetadata | null,
  jobs: RunJobRecord[]
): RunSummary {
  const stats = computeJobStats(jobs, metadata?.total_jobs ?? jobs.length);
  return {
    runId,
    status: metadata?.status ?? inferStatusFromJobs(stats, jobs),
    createdAt: metadata?.created_at,
    createdBy: metadata?.created_by,
    note: metadata?.note,
    mode: metadata?.mode,
    garment: metadata?.garment,
    allowedWorkers: Array.isArray(metadata?.allowed_workers)
      ? (metadata?.allowed_workers as string[])
      : undefined,
    totalJobs: stats.totalJobs,
    completedJobs: stats.completedJobs,
    failedJobs: stats.failedJobs,
    runningJobs: stats.runningJobs,
    pendingJobs: stats.pendingJobs,
    cancelledJobs: stats.cancelledJobs,
    progressPercent: stats.progressPercent,
    lastActivity: stats.lastActivity,
  };
}

function inferStatusFromJobs(
  stats: ReturnType<typeof computeJobStats>,
  jobs: RunJobRecord[]
): string {
  if (!jobs.length) return "pending";
  if (stats.failedJobs > 0) return "attention";
  if (stats.runningJobs > 0) return "running";
  if (stats.completedJobs === stats.totalJobs && stats.totalJobs > 0)
    return "completed";
  return "pending";
}

export async function listRunSummaries(limit = 50): Promise<RunSummary[]> {
  const runIds = USE_S3 ? await listS3RunIds() : await listLocalRunIds();
  const selected = runIds.slice(0, limit);
  const bundles = await Promise.all(selected.map((id) => loadRunBundle(id)));
  return bundles.map((bundle, index) => {
    const runId = selected[index];
    return buildSummary(runId, bundle.metadata, bundle.jobs);
  });
}

export async function getRunDetail(runId: string): Promise<RunDetail | null> {
  const bundle = await loadRunBundle(runId);
  if (!bundle.metadata && bundle.jobs.length === 0) {
    return null;
  }
  const summary = buildSummary(runId, bundle.metadata, bundle.jobs);
  return {
    summary,
    jobs: bundle.jobs,
    plan: bundle.plan,
    notes: bundle.notes,
    metadata: bundle.metadata as Record<string, unknown> | null,
  };
}

export async function updateRunMetadata(runId: string, updates: Record<string, unknown>): Promise<void> {
  if (USE_S3 && s3Client && bucket) {
    const baseKey = `${RUNS_SUBDIR.replace(/\/+$/u, "")}/${runId}`;
    const existing = (await readS3Json<Record<string, unknown>>(`${baseKey}/run.json`)) ?? {};
    const merged = { ...existing, ...updates };
    const payload = JSON.stringify(merged, null, 2) + "\n";
    await s3Client.send(
      new PutObjectCommand({
        Bucket: bucket,
        Key: `${baseKey}/run.json`,
        Body: payload,
        ContentType: "application/json",
      })
    );
    return;
  }

  const runDir = path.join(RUNS_ROOT, runId);
  const runPath = path.join(runDir, "run.json");
  const existing = (await safeParseJson<Record<string, unknown>>(runPath)) ?? {};
  const merged = { ...existing, ...updates };
  await fs.mkdir(runDir, { recursive: true });
  await fs.writeFile(runPath, JSON.stringify(merged, null, 2) + "\n", "utf-8");
}

export async function setAllowedWorkersMetadata(runId: string, allowed: string[]): Promise<void> {
  await updateRunMetadata(runId, { allowed_workers: allowed });
  await setAllowedWorkers(runId, allowed);
}

export async function deleteRun(runId: string): Promise<void> {
  if (USE_S3 && s3Client && bucket) {
    const prefix = `${RUNS_SUBDIR.replace(/\/+$/u, "")}/${runId}/`;
    let continuationToken: string | undefined;
    do {
      const listResult = await s3Client.send(
        new ListObjectsV2Command({
          Bucket: bucket,
          Prefix: prefix,
          ContinuationToken: continuationToken,
        })
      );
      const contents = listResult.Contents ?? [];
      if (contents.length) {
        const objects = contents.map((obj) => ({ Key: obj.Key! }));
        await s3Client.send(
          new DeleteObjectsCommand({
            Bucket: bucket,
            Delete: { Objects: objects },
          })
        );
      }
      continuationToken = listResult.NextContinuationToken;
    } while (continuationToken);
  } else {
    const runDir = path.join(RUNS_ROOT, runId);
    try {
      await fs.rm(runDir, { recursive: true, force: true });
    } catch (error) {
      console.warn(`[run-store] Failed to delete local run ${runId}:`, error);
    }
  }
  try {
    const cacheDir = path.join(RUN_CACHE_ROOT, runId);
    await fs.rm(cacheDir, { recursive: true, force: true });
  } catch (error) {
    // best effort
  }
  await removeRunStateEntry(runId);
}
