import path from "node:path";
import os from "node:os";
import { promises as fs } from "node:fs";
import { randomBytes } from "node:crypto";
import { exec as execCallback } from "node:child_process";
import { promisify } from "node:util";
import {
  S3Client,
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

export type RunSelection = {
  note?: string;
  mode?: string;
  garmentId?: string;
  fabrics?: string[];
  assets?: string[];
  views?: string[];
  saveDebugFiles?: boolean;
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

function resolveSelection<T>(input: T[], fallback: T[]): T[] {
  if (!input || input.length === 0) return fallback;
  return input;
}

function buildPlan(
  garment: GarmentOption,
  selection: Required<RunSelection>
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

async function allocateRunId(width = 4): Promise<string> {
  await ensureRunsDir();
  let current = 0;
  try {
    const raw = await fs.readFile(COUNTER_PATH, "utf-8");
    current = Number(raw.trim()) || 0;
  } catch (error: any) {
    if (error?.code === "ENOENT") {
      current = await scanHighestRunId();
    } else {
      throw error;
    }
  }
  const nextValue = current + 1;
  await fs.writeFile(COUNTER_PATH, String(nextValue), "utf-8");
  return String(nextValue).padStart(width, "0");
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
  garmentId: string,
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

  const garmentPath = path.join(GARMENTS_DIR, garmentId);
  const garmentArtifact = await readArtifact(
    garmentPath,
    `configs/garments/${garmentId}`
  );
  if (garmentArtifact) {
    artifacts.push(garmentArtifact);
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
  const mode = selection.mode?.trim();
  if (!mode) {
    throw new Error("Mode is required");
  }
  const garmentId = selection.garmentId?.trim();
  if (!garmentId) {
    throw new Error("Garment is required");
  }
  const garment = options.garments.find((item) => item.id === garmentId);
  if (!garment) {
    throw new Error("Selected garment is not available");
  }
  if (!garment.assets.length) {
    throw new Error("Selected garment does not define any assets");
  }

  const fabrics = uniqueList(
    resolveSelection(
      selection.fabrics ?? [],
      options.fabrics.map((f) => f.id)
    )
  );
  if (!fabrics.length) {
    throw new Error("Select at least one fabric");
  }
  fabrics.forEach((fabric) => {
    if (!options.fabrics.some((entry) => entry.id === fabric)) {
      throw new Error(`Fabric '${fabric}' is not available`);
    }
  });

  const assets = uniqueList(
    resolveSelection(
      selection.assets ?? [],
      garment.assets.map((asset) => asset.name)
    )
  );
  if (!assets.length) {
    throw new Error("Select at least one asset");
  }

  const views = uniqueList(
    resolveSelection(
      selection.views ?? [],
      garment.views.map((view) => view.code)
    )
  );
  if (!views.length) {
    throw new Error("Select at least one view");
  }

  const normalizedSelection: Required<RunSelection> = {
    mode,
    garmentId,
    fabrics,
    assets,
    views,
    note: selection.note ?? "",
    saveDebugFiles: Boolean(selection.saveDebugFiles),
  };

  const plan = buildPlan(garment, normalizedSelection);
  if (!plan.length) {
    throw new Error("No render combinations were generated");
  }

  const runId = await allocateRunId();
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

  const metadata = {
    run_id: runId,
    created_at: createdAt,
    created_by: createdBy,
    host: hostname,
    git_commit: gitCommit,
    note: normalizedSelection.note?.trim() || "",
    mode,
    garment: garmentId,
    fabrics: [...fabrics].sort(),
    assets: [...assets].sort(),
    views: [...views].sort(),
    total_jobs: plan.length,
    status: "pending",
  };

  const jobs = buildJobRecords(runId, plan);

  const notesBody = normalizedSelection.note?.trim()
    ? normalizedSelection.note.trim()
    : "(no notes provided)";

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

  const configArtifacts = await collectConfigArtifacts(garmentId, fabrics);
  files.push(...configArtifacts);

  await writeArtifactsToRunDir(runPath, files);

  await uploadArtifacts(runId, files);

  return { runId, totalJobs: plan.length };
}
