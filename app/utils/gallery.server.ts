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

type SuffixMatch = {
  suffix: string;
  fabricSlug: string;
  assetMeta: AssetMeta;
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

function isVisibleDir(dirent: Dirent): boolean {
  return dirent.isDirectory() && !dirent.name.startsWith(".");
}

function isPng(dirent: Dirent): boolean {
  return dirent.isFile() && dirent.name.toLowerCase().endsWith(".png");
}

function getLayerOrder(category: string | null): number {
  const key = category ?? "base";
  return layerPriorityLookup.get(key) ?? LAYER_FALLBACK_ORDER;
}

function fallbackFromRemainder(remainder: string): SuffixMatch | null {
  const lastDash = remainder.lastIndexOf("-");
  if (lastDash === -1) {
    return null;
  }
  const fabricSlug = remainder.slice(0, lastDash);
  const suffix = remainder.slice(lastDash + 1) || "base";
  if (!fabricSlug) return null;
  return {
    suffix,
    fabricSlug,
    assetMeta: {
      suffix,
      name: suffix,
      category: null,
      optionValue: null,
      order: getLayerOrder(null),
    },
  };
}

function findMatchingSuffix(
  remainder: string,
  assetMeta: AssetMeta[]
): SuffixMatch | null {
  if (!assetMeta || assetMeta.length === 0) {
    return fallbackFromRemainder(remainder);
  }
  const sorted = [...assetMeta].sort(
    (a, b) => b.suffix.length - a.suffix.length
  );
  for (const meta of sorted) {
    const token = `-${meta.suffix}`;
    if (remainder.endsWith(token)) {
      const fabricSlug = remainder.slice(0, remainder.length - token.length);
      if (fabricSlug) {
        return {
          suffix: meta.suffix,
          fabricSlug,
          assetMeta: meta,
        };
      }
    }
  }
  return fallbackFromRemainder(remainder);
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
  mode: string | null;
  date: string | null;
  garmentViews: Map<string, ViewMeta>;
  fabrics: Map<string, FabricMeta>;
};

type InternalGalleryEntry = {
  id: string;
  garmentId: string;
  garmentName: string;
  viewCode: string;
  viewLabel: string;
  fabrics: Map<string, FabricEntry>;
};

async function buildGallery({
  mode,
  date,
  garmentViews,
  fabrics,
}: BuildGalleryArgs): Promise<GalleryEntry[]> {
  if (!mode || !date) {
    return [];
  }
  const runDir = path.join(RENDERS_DIR, mode, date);
  const viewEntries = await safeReadDir(runDir);
  if (viewEntries.length === 0) {
    return [];
  }

  const galleryMap = new Map<string, InternalGalleryEntry>();

  for (const viewEntry of viewEntries) {
    if (!isVisibleDir(viewEntry)) continue;
    const viewName = viewEntry.name;
    const viewMeta = garmentViews.get(viewName);
    if (!viewMeta) continue;

    const viewPath = path.join(runDir, viewName);
    const fileEntries = await safeReadDir(viewPath);
    const pngFiles = fileEntries.filter(isPng);

    for (const png of pngFiles) {
      const fileName = png.name;
      const baseName = fileName.replace(/\.png$/i, "");
      const prefix = `${viewName}-`;
      if (!baseName.startsWith(prefix)) continue;
      const remainder = baseName.slice(prefix.length);
      const match = findMatchingSuffix(remainder, viewMeta.assetMeta);
      if (!match) continue;
      const { suffix, fabricSlug, assetMeta } = match;
      const fabricMeta = fabrics.get(fabricSlug) ?? { label: fabricSlug };

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

      const relativePath = path.posix.join(mode, date, viewName, fileName);
      fabricEntry.layers.push({
        suffix,
        label: assetMeta.name,
        category: assetMeta.category,
        optionValue: assetMeta.optionValue,
        order: assetMeta.order,
        url: `/renders/${relativePath}`,
      });
    }
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
  date?: string | null
): Promise<DescribeRendersResult> {
  const garmentViews = await loadGarmentViewIndex();
  const fabrics = await loadFabricIndex();
  const gallery = await buildGallery({
    mode: mode ?? null,
    date: date ?? null,
    garmentViews,
    fabrics,
  });

  return {
    gallery,
    configOptions: CONFIG_OPTIONS,
  };
}

export type { DescribeRendersResult, GalleryEntry, FabricEntry, LayerEntry };
