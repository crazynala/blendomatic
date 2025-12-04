import path from "node:path";
import { promises as fs } from "node:fs";
import type { Dirent } from "node:fs";
import {
  CONFIG_OPTIONS,
  categorizeSuffix,
  LAYER_PRIORITY,
  type ConfigOptions,
} from "./config-options";
import type { RunJobRecord } from "./run-store.server";
import { buildAssetPublicUrl } from "./asset-urls.server";

type AssetMeta = {
  suffix: string;
  name: string;
  category: string | null;
  optionValue: string | null;
  order: number;
};

type ViewMeta = {
  garmentId: string;
  garmentName: string;
  viewCode: string;
  viewLabel: string;
  assetMeta: AssetMeta[];
};

type LayerEntry = {
  suffix: string;
  label: string;
  category: string | null;
  optionValue: string | null;
  order: number;
  url: string;
};

type FabricEntry = {
  key: string;
  label: string;
  layers: LayerEntry[];
};

type GalleryEntry = {
  id: string;
  garmentId: string;
  garmentName: string;
  viewCode: string;
  viewLabel: string;
  fabrics: FabricEntry[];
};

type DescribeRendersResult = {
  gallery: GalleryEntry[];
  configOptions: ConfigOptions;
};

type GarmentAssetDefinition = {
  name?: string;
  suffix?: string;
};

type GarmentViewDefinition = {
  code?: string;
  label?: string;
  output_prefix?: string;
};

type GarmentFile = {
  name?: string;
  assets?: GarmentAssetDefinition[];
  views?: GarmentViewDefinition[];
  default_view?: string;
  output_prefix?: string;
};

type FabricMeta = {
  label: string;
};

const ROOT_DIR = process.cwd();
const GARMENTS_DIR = path.join(ROOT_DIR, "garments");
const FABRICS_DIR = path.join(ROOT_DIR, "fabrics");

const layerPriorityLookup = new Map<string, number>(
  LAYER_PRIORITY.map((key, index) => [key, index])
);
const LAYER_FALLBACK_ORDER = LAYER_PRIORITY.length;

const sanitizeName = (value: unknown, fallback: string): string => {
  if (!value) return fallback;
  const trimmed = String(value).trim();
  if (!trimmed) return fallback;
  return trimmed;
};

const slugify = (value: unknown, fallback = "asset"): string => {
  return (
    String(value ?? "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "") || fallback
  );
};

async function safeReadDir(dirPath: string): Promise<Dirent[]> {
  try {
    return await fs.readdir(dirPath, { withFileTypes: true });
  } catch (error) {
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
    return null;
  }
}

function getLayerOrder(category: string | null): number {
  const key = category ?? "base";
  return layerPriorityLookup.get(key) ?? LAYER_FALLBACK_ORDER;
}

async function loadGarmentViewIndex(): Promise<Map<string, ViewMeta>> {
  const entries = await safeReadDir(GARMENTS_DIR);
  const viewMap = new Map<string, ViewMeta>();
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.toLowerCase().endsWith(".json"))
      continue;
    const filePath = path.join(GARMENTS_DIR, entry.name);
    const garmentData = await safeParseJson<GarmentFile>(filePath);
    if (!garmentData) continue;
    const garmentId = entry.name.replace(/\.json$/i, "");
    const garmentName = sanitizeName(garmentData.name, garmentId);

    const assets: GarmentAssetDefinition[] = Array.isArray(garmentData.assets)
      ? garmentData.assets
      : [];
    const assetMeta: AssetMeta[] = assets.map((asset, index) => {
      const suffix = asset.suffix || slugify(asset.name, `asset_${index}`);
      const categoryInfo = categorizeSuffix(suffix);
      const category = categoryInfo?.category ?? null;
      const optionValue = categoryInfo?.optionValue ?? null;
      return {
        suffix,
        name: sanitizeName(asset.name, suffix),
        category,
        optionValue,
        order: getLayerOrder(category),
      };
    });

    const views: GarmentViewDefinition[] =
      Array.isArray(garmentData.views) && garmentData.views.length > 0
        ? garmentData.views
        : [
            {
              code: garmentData.default_view || "default",
              output_prefix: garmentData.output_prefix || garmentId,
            },
          ];

    for (const view of views) {
      const prefix =
        view.output_prefix ||
        [garmentData.output_prefix, view.code].filter(Boolean).join("_") ||
        garmentId;
      viewMap.set(prefix, {
        garmentId,
        garmentName,
        viewCode: view.code || "default",
        viewLabel: sanitizeName(
          view.label ?? view.code,
          view.code || "default"
        ),
        assetMeta,
      });
    }
  }
  return viewMap;
}

async function loadFabricIndex(): Promise<Map<string, FabricMeta>> {
  const entries = await safeReadDir(FABRICS_DIR);
  const fabricMap = new Map<string, FabricMeta>();
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.toLowerCase().endsWith(".json"))
      continue;
    const slug = entry.name.replace(/\.json$/i, "");
    const filePath = path.join(FABRICS_DIR, entry.name);
    const data = await safeParseJson<{ name?: string }>(filePath);
    fabricMap.set(slug, {
      label: sanitizeName(data?.name, slug),
    });
  }
  return fabricMap;
}

type BuildGalleryArgs = {
  jobs: RunJobRecord[];
  garmentViews: Map<string, ViewMeta>;
  fabrics: Map<string, FabricMeta>;
  mode?: string | null;
};

type InternalGalleryEntry = {
  id: string;
  garmentId: string;
  garmentName: string;
  viewCode: string;
  viewLabel: string;
  fabrics: Map<string, FabricEntry>;
};

const stripJsonExtension = (value?: string | null): string | null => {
  if (!value) return null;
  return value.replace(/\.json$/iu, "");
};

const normalizeFabricSlug = (value?: string | null): string | null => {
  const stripped = stripJsonExtension(value);
  if (!stripped) return null;
  return slugify(stripped, "fabric");
};

const normalizeAssetSuffix = (value?: string | null): string => {
  const trimmed = String(value ?? "").trim();
  return trimmed || "asset";
};

const resolveAssetMeta = (
  viewMeta: ViewMeta,
  suffix: string,
  fallbackLabel: string
): AssetMeta => {
  const match = viewMeta.assetMeta.find((entry) => entry.suffix === suffix);
  if (match) {
    return match;
  }
  const categoryInfo = categorizeSuffix(suffix);
  return {
    suffix,
    name: sanitizeName(fallbackLabel, suffix),
    category: categoryInfo?.category ?? null,
    optionValue: categoryInfo?.optionValue ?? null,
    order: getLayerOrder(categoryInfo?.category ?? null),
  };
};

async function buildGallery({
  jobs,
  garmentViews,
  fabrics,
  mode,
}: BuildGalleryArgs): Promise<GalleryEntry[]> {
  if (!jobs || jobs.length === 0) {
    return [];
  }

  const galleryMap = new Map<string, InternalGalleryEntry>();

  for (const job of jobs) {
    if (mode && job.config?.mode && job.config.mode !== mode) {
      continue;
    }
    const assetLocation =
      buildAssetPublicUrl((job.result as any)?.gallery ?? null) ??
      buildAssetPublicUrl(job.result?.uploaded ?? null);
    if (!assetLocation) {
      continue;
    }
    const viewPrefix = job.config?.view_output_prefix;
    if (!viewPrefix) continue;
    const viewMeta = garmentViews.get(viewPrefix);
    if (!viewMeta) continue;

    const fabricSlug =
      normalizeFabricSlug(job.config?.fabric) ??
      normalizeFabricSlug(job.config?.fabric_slug);
    if (!fabricSlug) continue;
    const fabricMeta = fabrics.get(fabricSlug) ?? { label: fabricSlug };

    const assetSuffix = normalizeAssetSuffix(
      job.config?.asset_suffix ?? job.config?.asset
    );
    const assetMeta = resolveAssetMeta(
      viewMeta,
      assetSuffix,
      job.config?.asset ?? assetSuffix
    );

    const entryKey = `${viewMeta.garmentId}:${viewMeta.viewCode}`;
    let entry = galleryMap.get(entryKey);
    if (!entry) {
      entry = {
        id: entryKey,
        garmentId: viewMeta.garmentId,
        garmentName: viewMeta.garmentName,
        viewCode: viewMeta.viewCode,
        viewLabel: viewMeta.viewLabel,
        fabrics: new Map(),
      };
      galleryMap.set(entryKey, entry);
    }

    let fabricEntry = entry.fabrics.get(fabricSlug);
    if (!fabricEntry) {
      fabricEntry = {
        key: fabricSlug,
        label: fabricMeta.label ?? fabricSlug,
        layers: [],
      };
      entry.fabrics.set(fabricSlug, fabricEntry);
    }

    fabricEntry.layers.push({
      suffix: assetMeta.suffix,
      label: assetMeta.name,
      category: assetMeta.category,
      optionValue: assetMeta.optionValue,
      order: assetMeta.order,
      url: assetLocation,
    });
  }

  return Array.from(galleryMap.values())
    .map((entry) => {
      const fabricsArr = Array.from(entry.fabrics.values())
        .map((fabric) => ({
          ...fabric,
          layers: fabric.layers.sort(
            (a, b) => a.order - b.order || a.label.localeCompare(b.label)
          ),
        }))
        .sort((a, b) => a.label.localeCompare(b.label));
      return {
        id: entry.id,
        garmentId: entry.garmentId,
        garmentName: entry.garmentName,
        viewCode: entry.viewCode,
        viewLabel: entry.viewLabel,
        fabrics: fabricsArr,
      } satisfies GalleryEntry;
    })
    .sort((a, b) => {
      const garmentCompare = a.garmentName.localeCompare(b.garmentName);
      if (garmentCompare !== 0) return garmentCompare;
      return a.viewLabel.localeCompare(b.viewLabel);
    });
}

export async function describeRenders(
  mode?: string | null,
  _date?: string | null,
  jobs: RunJobRecord[] = []
): Promise<DescribeRendersResult> {
  const garmentViews = await loadGarmentViewIndex();
  const fabrics = await loadFabricIndex();
  const gallery = await buildGallery({
    jobs,
    garmentViews,
    fabrics,
    mode: mode ?? null,
  });

  return {
    gallery,
    configOptions: CONFIG_OPTIONS,
  };
}

export type { DescribeRendersResult, GalleryEntry, FabricEntry, LayerEntry };
