import {
  ListObjectsV2Command,
  GetObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { ensureServerEnv } from "./load-env.server";

ensureServerEnv();

export type WorkerHeartbeat = {
  workerId: string;
  status: string;
  lastSeen?: string;
  hostname?: string;
  mode?: string;
  activeJobId?: string;
  info?: Record<string, unknown>;
};

const STORE_ENV =
  process.env.BLENDOMATIC_WORKER_STORE || process.env.BLENDOMATIC_S3_STORE;

if (!STORE_ENV) {
  throw new Error(
    "BLENDOMATIC_WORKER_STORE (or BLENDOMATIC_S3_STORE) is required. Set it in your .env as s3://bucket/prefix."
  );
}

if (!STORE_ENV.startsWith("s3://")) {
  throw new Error("BLENDOMATIC_WORKER_STORE must be an s3://bucket/prefix URI");
}

function parseStoreUri(uri: string) {
  const withoutScheme = uri.replace(/^s3:\/\//u, "").replace(/\/+$/u, "");
  const [bucket, ...rest] = withoutScheme.split("/");
  return {
    bucket,
    prefix: rest.join("/").replace(/\/+$/u, ""),
  };
}

const { bucket, prefix } = parseStoreUri(STORE_ENV);
const s3 = new S3Client({
  region:
    process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || "us-east-1",
});

const WORKERS_SUBDIR = prefix ? `${prefix}/workers` : "workers";

async function streamToString(body: unknown): Promise<string> {
  if (!body) return "";
  if (typeof (body as any).transformToString === "function") {
    return (body as any).transformToString();
  }
  const chunks: Uint8Array[] = [];
  return await new Promise((resolve, reject) => {
    (body as NodeJS.ReadableStream)
      .on("data", (chunk) => chunks.push(Buffer.from(chunk)))
      .once("end", () => resolve(Buffer.concat(chunks).toString("utf-8")))
      .once("error", reject);
  });
}

export async function listWorkerHeartbeats(): Promise<WorkerHeartbeat[]> {
  const workers: WorkerHeartbeat[] = [];
  let continuationToken: string | undefined;
  const prefixWithSlash = WORKERS_SUBDIR.replace(/\/+$/u, "") + "/";

  do {
    const listCmd = new ListObjectsV2Command({
      Bucket: bucket,
      Prefix: prefixWithSlash,
      ContinuationToken: continuationToken,
    });
    const page = await s3.send(listCmd);
    const keys = page.Contents?.map((obj) => obj.Key).filter(Boolean) as
      | string[]
      | undefined;
    if (keys && keys.length) {
      const pageResults = await Promise.all(
        keys.map(async (key) => {
          try {
            const getCmd = new GetObjectCommand({ Bucket: bucket, Key: key });
            const result = await s3.send(getCmd);
            const payload = await streamToString(result.Body);
            const record = JSON.parse(payload);
            return {
              workerId:
                record.worker_id ??
                record.workerId ??
                key.split("/").pop() ??
                "unknown",
              status: record.status ?? "unknown",
              lastSeen: record.last_seen || record.lastSeen,
              hostname: record.hostname,
              mode: record.mode,
              activeJobId: record.active_job_id ?? record.activeJobId,
              info: record.info ?? {},
            } satisfies WorkerHeartbeat;
          } catch (error) {
            console.error(`Failed to read worker record ${key}:`, error);
            return null;
          }
        })
      );
      for (const record of pageResults) {
        if (record) workers.push(record);
      }
    }
    continuationToken = page.NextContinuationToken;
  } while (continuationToken);

  return workers;
}
