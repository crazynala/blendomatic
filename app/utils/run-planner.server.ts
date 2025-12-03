import path from "node:path";
import os from "node:os";
import { promises as fs } from "node:fs";
import { randomBytes } from "node:crypto";
import { exec as execCallback } from "node:child_process";
import { promisify } from "node:util";
import {
  S3Client,
  ListObjectsV2Command,
  GetObjectCommand,
  PutObjectCommand,
  type PutObjectCommandInput,
} from "@aws-sdk/client-s3";
import { ensureServerEnv } from "./load-env.server";

ensureServerEnv();

const ROOT_DIR = process.cwd();
const GARMENTS_DIR = path.join(ROOT_DIR, "garments");
const FABRICS_DIR = path.join(ROOT_DIR, "fabrics");
const RENDER_CONFIG_PATH = path.join(ROOT_DIR, "render_config.json");
const RUNS_DIR = path.join(ROOT_DIR, "runs");
const COUNTER_PATH = path.join(RUNS_DIR, ".counter");

const MANIFEST_HEADERS = [
  "timestamp",
  "status",
  "garment",
  "fabric",
  "asset",
  "view",
  "output",
  "worker",
  "notes",
];

const exec = promisify(execCallback);

const STORE_URI =
  process.env.BLENDOMATIC_RUN_STORE ?? process.env.BLENDOMATIC_S3_STORE;

let s3Client: S3Client | null = null;
let runsBaseKey: string | null = null;
let bucket: string | null = null;

if (STORE_URI && STORE_URI.startsWith("s3://")) {
  const { bucket: parsedBucket, prefix } = parseStoreUri(STORE_URI);
  bucket = parsedBucket;
  runsBaseKey = prefix ? `${prefix}/runs` : "runs";
  s3Client = new S3Client({
    region:
      process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || "us-east-1",
  });
}

function parseStoreUri(uri: string) {
  const withoutScheme = uri.replace(/^s3:\/\//u, "").replace(/\/+$/u, "");
  const [resolvedBucket, ...rest] = withoutScheme.split("/");
  return {
    bucket: resolvedBucket,
    prefix: rest.join("/").replace(/\/+$/u, ""),
  };
}

function slugify(value: string, fallback: string) {
  return (
    value
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "") || fallback
  );
}

async function safeReadDir(dirPath: string) {
  try {
    return await fs.readdir(dirPath, { withFileTypes: true });
  } catch (error) {
    console.warn(`[run-planner] Failed to read dir ${dirPath}:`, error);
    return [];
  }
}

async function safeReadJson<T>(filePath: string): Promise<T | null> {
  try {
    const raw = await fs.readFile(filePath, "utf-8");
    return JSON.parse(raw) as T;
  } catch (error) {
    console.warn(`[run-planner] Failed to parse ${filePath}:`, error);
    return null;
  }
}

export type GarmentView = {
  code: string;
  label: string;
  outputPrefix: string;
};

export type GarmentAsset = {
  name: string;
  suffix: string;
  renderViews: string[];
};

export type GarmentOption = {
  id: string;
  name: string;
  views: GarmentView[];
  assets: GarmentAsset[];
};

export type FabricOption = {
  id: string;
  name: string;
};

export type ModeOption = {
  value: string;
  label: string;
};

export type RunFormOptions = {
  modes: ModeOption[];
  garments: GarmentOption[];
  fabrics: FabricOption[];
};

export type RunGarmentSelection = {
  garmentId: string;
  fabrics?: string[];
  assets?: string[];
  views?: string[];
};

export type RunSelection = {
  note: string;
  mode: string;
  garments: RunGarmentSelection[];
  saveDebugFiles?: boolean;
  runNumber?: number | string | null;
};

type PlanItem = {
  mode: string;
  garment: string;
  fabric: string;
  asset: string;
  view: string;
  view_output_prefix?: string;
  asset_suffix?: string;
  save_debug_files?: boolean;
};

type JobRecord = {
  job_id: string;
  run_id: string;
  sequence: number;
  status: string;
  worker: null;
  config: PlanItem;
  created_at: string;
  updated_at: string;
  started_at: null;
  finished_at: null;
  result: null;
  version: number;
  notes: null;
};

type RunArtifact = {
  name: string;
  body: string;
  contentType: string;
};

export async function loadRunFormOptions(): Promise<RunFormOptions> {
  const [garments, fabrics, modes] = await Promise.all([
    loadGarmentOptions(),
    loadFabricOptions(),
    loadModes(),
  ]);
  return { garments, fabrics, modes };
}

async function loadModes(): Promise<ModeOption[]> {
  const data = await safeReadJson<Record<string, any>>(RENDER_CONFIG_PATH);
  if (!data) return [];
  const source =
    data && typeof data.modes === "object" && data.modes !== null
      ? (data.modes as Record<string, any>)
      : data;
  return Object.keys(source)
    .map((key) => ({ value: key, label: key }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

async function loadGarmentOptions(): Promise<GarmentOption[]> {
  const entries = await safeReadDir(GARMENTS_DIR);
  const options: GarmentOption[] = [];
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.toLowerCase().endsWith(".json")) {
      continue;
    }
    const filePath = path.join(GARMENTS_DIR, entry.name);
    const data = await safeReadJson<Record<string, any>>(filePath);
    if (!data) continue;
    const id = entry.name;
    const friendlyName =
      typeof data.name === "string" && data.name.trim() ? data.name.trim() : id;

    const views = normalizeViews(data, id);
    const assets = normalizeAssets(data);

    options.push({ id, name: friendlyName, views, assets });
  }
  return options.sort((a, b) => a.name.localeCompare(b.name));
}

function normalizeViews(
  data: Record<string, any>,
  fileName: string
): GarmentView[] {
  const fallbackCode = (data.default_view ?? "default").toString();
  const fallbackPrefix =
    typeof data.output_prefix === "string" && data.output_prefix.trim()
      ? data.output_prefix.trim()
      : fileName.replace(/\.json$/i, "");
  const rawViews = Array.isArray(data.views) ? data.views : [];
  const views: GarmentView[] = [];

  if (rawViews.length === 0) {
    return [
      {
        code: fallbackCode,
        label: data.name ?? fallbackCode,
        outputPrefix: fallbackPrefix,
      },
    ];
  }

  for (const raw of rawViews) {
    if (!raw) continue;
    const code = String(raw.code ?? raw.label ?? fallbackCode).trim();
    if (!code) continue;
    const label =
      typeof raw.label === "string" && raw.label.trim()
        ? raw.label.trim()
        : code;
    const outputPrefix =
      typeof raw.output_prefix === "string" && raw.output_prefix.trim()
        ? raw.output_prefix.trim()
        : fallbackPrefix;
    views.push({ code, label, outputPrefix });
  }

  return views.length
    ? views
    : [
        {
          code: fallbackCode,
          label: fallbackCode,
          outputPrefix: fallbackPrefix,
        },
      ];
}

function normalizeAssets(data: Record<string, any>): GarmentAsset[] {
  const rawAssets = Array.isArray(data.assets) ? data.assets : [];
  if (!rawAssets.length) return [];
  const assets: GarmentAsset[] = [];
  rawAssets.forEach((asset, index) => {
    if (!asset) return;
    const name =
      typeof asset.name === "string" && asset.name.trim()
        ? asset.name.trim()
        : `asset_${index + 1}`;
    const suffix =
      typeof asset.suffix === "string" && asset.suffix.trim()
        ? asset.suffix.trim()
        : slugify(name, `asset_${index + 1}`);
    const viewsRaw = asset.render_views ?? asset.renderViews;
    let renderViews: string[] = [];
    if (Array.isArray(viewsRaw)) {
      renderViews = viewsRaw
        .map((value) => String(value).trim())
        .filter(Boolean);
    } else if (typeof viewsRaw === "string" && viewsRaw.trim()) {
      renderViews = [viewsRaw.trim()];
    }
    assets.push({ name, suffix, renderViews });
  });
  return assets;
}

async function loadFabricOptions(): Promise<FabricOption[]> {
  const entries = await safeReadDir(FABRICS_DIR);
  const fabrics: FabricOption[] = [];
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.toLowerCase().endsWith(".json")) {
      continue;
    }
    const filePath = path.join(FABRICS_DIR, entry.name);
    const data = await safeReadJson<Record<string, any>>(filePath);
    const id = entry.name;
    const name =
      typeof data?.name === "string" && data.name.trim()
        ? data.name.trim()
        : id;
    fabrics.push({ id, name });
  }
  return fabrics.sort((a, b) => a.name.localeCompare(b.name));
}

function uniqueList(values: string[]): string[] {
  return Array.from(
    new Set(values.map((value) => value.trim()).filter(Boolean))
  );
}
function buildPlanForGarment(
  garment: GarmentOption,
  selection: {
    mode: string;
    fabrics: string[];
    assets: string[];
    views: string[];
    saveDebugFiles: boolean;
  }
): PlanItem[] {
  const viewOrder = garment.views.map((view) => view.code);
  const viewLookup = new Map(garment.views.map((view) => [view.code, view]));
  const requestedViews = selection.views.filter((code) => viewLookup.has(code));
  const effectiveViews = requestedViews.length ? requestedViews : viewOrder;
  const viewSet = new Set(effectiveViews);

  const plan: PlanItem[] = [];
  for (const fabric of selection.fabrics) {
    for (const assetName of selection.assets) {
      const asset = garment.assets.find((item) => item.name === assetName);
      if (!asset) {
        throw new Error(
          `Asset '${assetName}' is not defined on ${garment.name}`
        );
      }
      const assetViews =
        asset.renderViews && asset.renderViews.length
          ? asset.renderViews.filter((code) => viewLookup.has(code))
          : viewOrder;
      const eligibleViews = assetViews.filter((code) => viewSet.has(code));
      if (!eligibleViews.length) {
        throw new Error(
          `Asset '${assetName}' is not configured for the selected views`
        );
      }
      for (const viewCode of eligibleViews) {
        const viewMeta = viewLookup.get(viewCode);
        plan.push({
          mode: selection.mode,
          garment: garment.id,
          fabric,
          asset: assetName,
          view: viewCode,
          view_output_prefix: viewMeta?.outputPrefix,
          asset_suffix: asset.suffix,
          save_debug_files: selection.saveDebugFiles,
        });
      }
    }
  }
  return plan;
}

function buildJobRecords(runId: string, plan: PlanItem[]): JobRecord[] {
  const now = new Date().toISOString();
  return plan.map((config, index) => ({
    job_id: `${runId}-${String(index + 1).padStart(4, "0")}-${randomBytes(4)
      .toString("hex")
      .slice(0, 8)}`,
    run_id: runId,
    sequence: index + 1,
    status: "pending",
    worker: null,
    config,
    created_at: now,
    updated_at: now,
    started_at: null,
    finished_at: null,
    result: null,
    version: 1,
    notes: null,
  }));
}

async function ensureRunsDir() {
  await fs.mkdir(RUNS_DIR, { recursive: true });
}

async function scanHighestRunId(): Promise<number> {
  const entries = await safeReadDir(RUNS_DIR);
  let highest = 0;
  for (const entry of entries) {
    if (entry.isDirectory() && /^\d+$/.test(entry.name)) {
      highest = Math.max(highest, Number(entry.name));
    }
  }
  return highest;
}

async function readLocalCounter(): Promise<number | null> {
  try {
    const raw = await fs.readFile(COUNTER_PATH, "utf-8");
    return Number(raw.trim()) || 0;
  } catch (error: any) {
    if (error?.code === "ENOENT") {
      return null;
    }
    throw error;
  }
}

async function readS3Counter(): Promise<number | null> {
  if (!s3Client || !bucket || !runsBaseKey) return null;
  const key = `${runsBaseKey.replace(/\/+$/u, "")}/.counter`;
  try {
    const { Body } = await s3Client.send(
      new GetObjectCommand({ Bucket: bucket, Key: key })
    );
    if (Body && "transformToString" in Body) {
      const text = await (Body as any).transformToString();
      const parsed = Number(String(text).trim());
      return Number.isFinite(parsed) ? parsed : null;
    }
  } catch (error: any) {
    if (error?.$metadata?.httpStatusCode === 404) {
      return null;
    }
    return null;
  }
  return null;
}

async function writeS3Counter(value: number) {
  if (!s3Client || !bucket || !runsBaseKey) return;
  const key = `${runsBaseKey.replace(/\/+$/u, "")}/.counter`;
  await s3Client.send(
    new PutObjectCommand({
      Bucket: bucket,
      Key: key,
      Body: String(value),
      ContentType: "text/plain",
    })
  );
}

async function scanHighestS3RunId(): Promise<number> {
  if (!s3Client || !bucket || !runsBaseKey) return 0;
  const prefix = `${runsBaseKey.replace(/\/+$/u, "")}/`;
  let highest = 0;
  const result = await s3Client.send(
    new ListObjectsV2Command({ Bucket: bucket, Prefix: prefix })
  );
  for (const obj of result.Contents ?? []) {
    const key = obj.Key ?? "";
    const suffix = key.slice(prefix.length);
    const runId = suffix.split("/", 1)[0];
    if (/^\d+$/.test(runId)) {
      highest = Math.max(highest, Number(runId));
    }
  }
  return highest;
}

async function runExists(runId: string): Promise<boolean> {
  const localPath = path.join(RUNS_DIR, runId);
  try {
    const stat = await fs.stat(localPath);
    if (stat.isDirectory()) return true;
  } catch {
    // ignore
  }
  if (s3Client && bucket && runsBaseKey) {
    const prefix = `${runsBaseKey.replace(/\/+$/u, "")}/${runId}/`;
    const result = await s3Client.send(
      new ListObjectsV2Command({ Bucket: bucket, Prefix: prefix, MaxKeys: 1 })
    );
    if ((result.KeyCount ?? 0) > 0 || (result.Contents ?? []).length) {
      return true;
    }
  }
  return false;
}

function normalizeRunNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed =
    typeof value === "string" ? Number(value.trim()) : Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) {
    throw new Error("Run number must be a positive integer");
  }
  return parsed;
}

async function currentRunFloor(): Promise<number> {
  const candidates: number[] = [];

  const s3Counter = await readS3Counter();
  if (s3Counter !== null) candidates.push(s3Counter);
  const s3Highest = await scanHighestS3RunId();
  if (s3Highest) candidates.push(s3Highest);

  const localCounter = await readLocalCounter();
  if (localCounter !== null) candidates.push(localCounter);
  const localHighest = await scanHighestRunId();
  if (localHighest) candidates.push(localHighest);

  return candidates.length ? Math.max(...candidates) : 0;
}

async function allocateRunId(width = 4, requested?: number | null): Promise<string> {
  await ensureRunsDir();
  const floor = await currentRunFloor();

  if (requested !== null && requested !== undefined) {
    if (!Number.isInteger(requested) || requested < 1) {
      throw new Error("Run number must be a positive integer");
    }
    if (requested <= floor) {
      throw new Error(
        `Run ${String(requested).padStart(width, "0")} already exists or was used`
      );
    }
  }

  const nextValue =
    requested !== null && requested !== undefined ? requested : floor + 1;

  await fs.writeFile(COUNTER_PATH, String(nextValue), "utf-8");
  await writeS3Counter(nextValue);
  return String(nextValue).padStart(width, "0");
}

export async function getExpectedRunNumber(
  width = 4
): Promise<{ numeric: number; padded: string }> {
  await ensureRunsDir();
  const floor = await currentRunFloor();
  const nextValue = floor + 1;
  const padded = String(nextValue).padStart(width, "0");
  return { numeric: nextValue, padded };
}

async function readGitCommit(): Promise<string | null> {
  try {
    const { stdout } = await exec("git rev-parse HEAD", { cwd: ROOT_DIR });
    return stdout.trim();
  } catch {
    return null;
  }
}

async function readArtifact(
  sourcePath: string,
  targetName: string,
  contentType = "application/json"
): Promise<RunArtifact | null> {
  try {
    const body = await fs.readFile(sourcePath, "utf-8");
    return { name: targetName, body, contentType };
  } catch (error) {
    console.warn(`[run-planner] Missing config file ${sourcePath}:`, error);
    return null;
  }
}

async function collectConfigArtifacts(
  garmentIds: string[],
  fabrics: string[]
): Promise<RunArtifact[]> {
  const artifacts: RunArtifact[] = [];
  const renderConfig = await readArtifact(
    RENDER_CONFIG_PATH,
    "configs/render_config.json"
  );
  if (renderConfig) {
    artifacts.push(renderConfig);
  }

  for (const garmentId of garmentIds) {
    const garmentPath = path.join(GARMENTS_DIR, garmentId);
    const garmentArtifact = await readArtifact(
      garmentPath,
      `configs/garments/${garmentId}`
    );
    if (garmentArtifact) {
      artifacts.push(garmentArtifact);
    }
  }

  for (const fabricId of fabrics) {
    const fabricPath = path.join(FABRICS_DIR, fabricId);
    const artifact = await readArtifact(
      fabricPath,
      `configs/fabrics/${fabricId}`
    );
    if (artifact) {
      artifacts.push(artifact);
    }
  }

  return artifacts;
}

async function writeArtifactsToRunDir(runPath: string, files: RunArtifact[]) {
  await Promise.all(
    files.map(async (file) => {
      const target = path.join(runPath, file.name);
      await fs.mkdir(path.dirname(target), { recursive: true });
      await fs.writeFile(target, file.body, "utf-8");
    })
  );
}

async function uploadArtifacts(runId: string, files: RunArtifact[]) {
  if (!s3Client || !bucket || !runsBaseKey) return;
  const baseKey = `${runsBaseKey.replace(/\/+$/u, "")}/${runId}`;
  await Promise.all(
    files.map((file) => {
      const input: PutObjectCommandInput = {
        Bucket: bucket!,
        Key: `${baseKey}/${file.name}`,
        Body: file.body,
        ContentType: file.contentType,
      };
      return s3Client!.send(new PutObjectCommand(input)).catch((error) => {
        console.warn(`[run-planner] Failed to upload ${file.name}:`, error);
      });
    })
  );
}

export async function createRunFromSelection(selection: RunSelection) {
  const options = await loadRunFormOptions();
  const payload = selection as Partial<RunSelection>;
  const mode =
    typeof payload.mode === "string" ? payload.mode.trim() : "";
  if (!mode) {
    throw new Error("Mode is required");
  }
  const note =
    typeof payload.note === "string" ? payload.note.trim() : "";
  if (!note) {
    throw new Error("Operator note is required");
  }
  const garmentSelections = Array.isArray(payload.garments)
    ? payload.garments
    : [];
  if (!garmentSelections.length) {
    throw new Error("Select at least one garment");
  }

  const garmentMap = new Map(options.garments.map((item) => [item.id, item]));
  const seenGarments = new Set<string>();
  const normalizedGarments: {
    garment: GarmentOption;
    fabrics: string[];
    assets: string[];
    views: string[];
  }[] = [];

  for (const entry of garmentSelections) {
    const garmentId = entry.garmentId?.trim();
    if (!garmentId) {
      throw new Error("Garment selection is missing an id");
    }
    if (seenGarments.has(garmentId)) {
      throw new Error(`Garment '${garmentId}' was included more than once`);
    }
    seenGarments.add(garmentId);
    const garment = garmentMap.get(garmentId);
    if (!garment) {
      throw new Error(`Garment '${garmentId}' is not available`);
    }
    if (!garment.assets.length) {
      throw new Error(`Garment '${garment.name}' does not define assets`);
    }

    const fabrics = uniqueList(entry.fabrics ?? []);
    if (!fabrics.length) {
      throw new Error(
        `Select at least one fabric for garment '${garment.name}'`
      );
    }
    fabrics.forEach((fabric) => {
      if (!options.fabrics.some((item) => item.id === fabric)) {
        throw new Error(`Fabric '${fabric}' is not available`);
      }
    });

    const assets = uniqueList(entry.assets ?? []);
    if (!assets.length) {
      throw new Error(
        `Select at least one asset for garment '${garment.name}'`
      );
    }

    const views = uniqueList(entry.views ?? []);
    if (!views.length) {
      throw new Error(
        `Select at least one view for garment '${garment.name}'`
      );
    }

    normalizedGarments.push({ garment, fabrics, assets, views });
  }

  const plan: PlanItem[] = [];
  for (const selectionEntry of normalizedGarments) {
    plan.push(
      ...buildPlanForGarment(selectionEntry.garment, {
        mode,
        fabrics: selectionEntry.fabrics,
        assets: selectionEntry.assets,
        views: selectionEntry.views,
        saveDebugFiles: Boolean(payload.saveDebugFiles),
      })
    );
  }
  if (!plan.length) {
    throw new Error("No render combinations were generated");
  }

  const requestedRunNumber = normalizeRunNumber(payload.runNumber);
  if (requestedRunNumber) {
    const requestedRunId = String(requestedRunNumber).padStart(4, "0");
    if (await runExists(requestedRunId)) {
      throw new Error(`Run ${requestedRunId} already exists in the run store`);
    }
  }

  const runId = await allocateRunId(4, requestedRunNumber);
  const runPath = path.join(RUNS_DIR, runId);
  await fs.mkdir(runPath, { recursive: true });

  const createdAt = new Date().toISOString();
  const createdBy =
    process.env.BLENDOMATIC_RUN_USER ||
    process.env.USER ||
    process.env.LOGNAME ||
    "unknown";
  const hostname = os.hostname();
  const gitCommit = await readGitCommit();

  const selectedGarmentIds = normalizedGarments.map(
    (entry) => entry.garment.id
  );
  const garmentNames = normalizedGarments.map((entry) => entry.garment.name);
  const allFabrics = new Set<string>();
  const allAssets = new Set<string>();
  const allViews = new Set<string>();
  normalizedGarments.forEach((entry) => {
    entry.fabrics.forEach((fabric) => allFabrics.add(fabric));
    entry.assets.forEach((asset) => allAssets.add(asset));
    entry.views.forEach((view) => allViews.add(view));
  });
  const fabricList = [...allFabrics].sort();
  const assetList = [...allAssets].sort();
  const viewList = [...allViews].sort();

  const metadata = {
    run_id: runId,
    created_at: createdAt,
    created_by: createdBy,
    host: hostname,
    git_commit: gitCommit,
    note,
    mode,
    garment: garmentNames.join(", "),
    garments: selectedGarmentIds,
    fabrics: fabricList,
    assets: assetList,
    views: viewList,
    total_jobs: plan.length,
    status: "pending",
  };

  const jobs = buildJobRecords(runId, plan);

  const notesBody = note || "(no notes provided)";

  const files: RunArtifact[] = [
    {
      name: "run.json",
      body: `${JSON.stringify(metadata, null, 2)}\n`,
      contentType: "application/json",
    },
    {
      name: "plan.json",
      body: `${JSON.stringify(plan, null, 2)}\n`,
      contentType: "application/json",
    },
    {
      name: "jobs.json",
      body: `${JSON.stringify(jobs, null, 2)}\n`,
      contentType: "application/json",
    },
    {
      name: "notes.md",
      body: `# Run ${runId}\n\n${notesBody}\n`,
      contentType: "text/markdown",
    },
    {
      name: "manifest.csv",
      body: `${MANIFEST_HEADERS.join(",")}\n`,
      contentType: "text/csv",
    },
  ];

  const configArtifacts = await collectConfigArtifacts(
    selectedGarmentIds,
    fabricList
  );
  files.push(...configArtifacts);

  await writeArtifactsToRunDir(runPath, files);

  await uploadArtifacts(runId, files);

  return { runId, totalJobs: plan.length };
}
