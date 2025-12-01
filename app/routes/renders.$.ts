import path from "node:path";
import { stat } from "node:fs/promises";
import { createReadStream } from "node:fs";

const RENDERS_DIR = path.join(process.cwd(), "renders");

function sanitizeSplat(value) {
  if (!value) return null;
  const normalized = path.normalize(value).replace(/^([/\\])+/, "");
  if (normalized.includes("..")) {
    return null;
  }
  return normalized;
}

function getContentType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".png") return "image/png";
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".webp") return "image/webp";
  return "application/octet-stream";
}

export async function loader({ params }) {
  const splat = sanitizeSplat(params["*"]);
  if (!splat) {
    throw new Response("Not found", { status: 404 });
  }
  const absolutePath = path.join(RENDERS_DIR, splat);
  if (!absolutePath.startsWith(RENDERS_DIR)) {
    throw new Response("Not found", { status: 404 });
  }
  try {
    const fileStat = await stat(absolutePath);
    if (!fileStat.isFile()) {
      throw new Response("Not found", { status: 404 });
    }
  } catch (error) {
    throw new Response("Not found", { status: 404 });
  }

  const stream = createReadStream(absolutePath);
  return new Response(stream, {
    headers: {
      "Content-Type": getContentType(absolutePath),
      "Cache-Control": "public, max-age=3600",
    },
  });
}
