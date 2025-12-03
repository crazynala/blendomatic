import { ensureServerEnv } from "./load-env.server";

ensureServerEnv();

const storeUri =
  process.env.BLENDOMATIC_RUN_STORE ?? process.env.BLENDOMATIC_S3_STORE ?? null;
const defaultRegion =
  process.env.AWS_REGION ?? process.env.AWS_DEFAULT_REGION ?? "us-east-1";

type ParsedS3Uri = {
  bucket: string;
  key: string;
};

const encodeKey = (key: string) =>
  key
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");

const parseS3Uri = (uri: string): ParsedS3Uri | null => {
  if (!uri.toLowerCase().startsWith("s3://")) {
    return null;
  }
  const withoutScheme = uri.slice(5);
  const firstSlash = withoutScheme.indexOf("/");
  if (firstSlash === -1) {
    return { bucket: withoutScheme, key: "" };
  }
  return {
    bucket: withoutScheme.slice(0, firstSlash),
    key: withoutScheme.slice(firstSlash + 1),
  };
};

export function buildAssetPublicUrl(
  location?: string | null,
  region: string = defaultRegion
): string | null {
  if (!location) return null;
  if (/^https?:\/\//iu.test(location)) {
    return location;
  }
  if (!location.toLowerCase().startsWith("s3://")) {
    // Fall back to Remix static routes (for local dev with /renders/*)
    if (location.startsWith("/")) return location;
    if (location.startsWith("renders/")) return `/${location}`;
    return null;
  }
  const parsed = parseS3Uri(location);
  if (!parsed) return null;
  const host =
    region && region !== "us-east-1"
      ? `${parsed.bucket}.s3.${region}.amazonaws.com`
      : `${parsed.bucket}.s3.amazonaws.com`;
  const encodedKey = encodeKey(parsed.key);
  return encodedKey ? `https://${host}/${encodedKey}` : `https://${host}`;
}

export function getRunStorePublicBase(): string | null {
  if (!storeUri || !storeUri.toLowerCase().startsWith("s3://")) {
    return null;
  }
  const parsed = parseS3Uri(storeUri);
  if (!parsed) return null;
  const host =
    defaultRegion && defaultRegion !== "us-east-1"
      ? `${parsed.bucket}.s3.${defaultRegion}.amazonaws.com`
      : `${parsed.bucket}.s3.amazonaws.com`;
  const basePath = parsed.key ? `${encodeKey(parsed.key)}/runs/outputs` : "";
  return basePath ? `https://${host}/${basePath}` : `https://${host}`;
}
