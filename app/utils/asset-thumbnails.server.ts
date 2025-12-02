import path from "node:path";
import { promises as fs } from "node:fs";

const ROOT_DIR = process.cwd();
const PUBLIC_DIR = path.join(ROOT_DIR, "public");
const THUMB_ROOT = path.join(PUBLIC_DIR, "asset-thumbnails");
const ACCEPTED_TYPES: Record<string, string> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/jpg": "jpg",
  "image/webp": "webp",
};
const EXTENSION_ORDER = ["png", "jpg", "jpeg", "webp"] as const;
const MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024; // 2MB

const sanitizeSlug = (value: string): string => {
  return value
    .replace(/\.json$/iu, "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/giu, "-")
    .replace(/^-+|-+$/g, "");
};

async function ensureDir(dirPath: string) {
  await fs.mkdir(dirPath, { recursive: true });
}

async function removeExistingVariants(dirPath: string, assetSlug: string) {
  await Promise.all(
    EXTENSION_ORDER.map(async (ext) => {
      const candidate = path.join(dirPath, `${assetSlug}.${ext}`);
      try {
        await fs.unlink(candidate);
      } catch (error) {
        // ignore missing files
      }
    })
  );
}

function validateUpload(file: File) {
  if (!(file && typeof file.arrayBuffer === "function")) {
    throw new Error("Invalid file upload");
  }
  const extension = ACCEPTED_TYPES[file.type];
  if (!extension) {
    throw new Error("Unsupported file type. Use PNG, JPG, or WEBP.");
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    throw new Error("Thumbnail must be 2MB or smaller");
  }
  return extension;
}

export async function saveAssetThumbnail(
  garmentId: string,
  assetKey: string,
  file: File
): Promise<{ url: string }> {
  if (!garmentId || !assetKey) {
    throw new Error("Missing garment or asset reference");
  }
  const extension = validateUpload(file);
  const garmentSlug = sanitizeSlug(garmentId);
  const assetSlug = sanitizeSlug(assetKey);
  const garmentDir = path.join(THUMB_ROOT, garmentSlug);
  await ensureDir(garmentDir);
  await removeExistingVariants(garmentDir, assetSlug);
  const buffer = Buffer.from(await file.arrayBuffer());
  const filename = `${assetSlug}.${extension}`;
  await fs.writeFile(path.join(garmentDir, filename), buffer);
  return {
    url: `/asset-thumbnails/${garmentSlug}/${filename}`,
  };
}

export async function getAssetThumbnailUrl(
  garmentId: string,
  assetKey: string
): Promise<string | null> {
  if (!garmentId || !assetKey) return null;
  const garmentSlug = sanitizeSlug(garmentId);
  const assetSlug = sanitizeSlug(assetKey);
  const garmentDir = path.join(THUMB_ROOT, garmentSlug);
  for (const ext of EXTENSION_ORDER) {
    const candidate = path.join(garmentDir, `${assetSlug}.${ext}`);
    try {
      await fs.access(candidate);
      return `/asset-thumbnails/${garmentSlug}/${assetSlug}.${ext}`;
    } catch (error) {
      continue;
    }
  }
  return null;
}
