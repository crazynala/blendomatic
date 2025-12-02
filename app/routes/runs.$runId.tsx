import { json } from "@remix-run/node";
import type { ActionFunctionArgs, LoaderFunctionArgs } from "@remix-run/node";
import {
  Link,
  useFetcher,
  useLoaderData,
  useParams,
  useRevalidator,
} from "@remix-run/react";
import {
  Alert,
  Anchor,
  Badge,
  Box,
  Button,
  Card,
  Center,
  Code,
  Container,
  Divider,
  Group,
  Progress,
  ScrollArea,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import {
  IconArrowLeft,
  IconArticle,
  IconClipboardList,
} from "@tabler/icons-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ChangeEvent,
  type ReactNode,
} from "react";
import { WorkspaceNav } from "../components/workspace-nav";
import type { RunJobRecord } from "../utils/run-store.server";
import { WorkspaceNav } from "../components/workspace-nav";

type AssetLibraryEntry = {
  assetKey: string;
  label: string;
  thumbnailUrl: string | null;
};

export async function loader({ params }: LoaderFunctionArgs) {
  const runId = params.runId;
  if (!runId) {
    throw new Response("Run ID required", { status: 400 });
  }
  const [
    { getRunDetail },
    { buildJobPreview, inferRenderDateFolder },
    { getAssetThumbnailUrl },
  ] = await Promise.all([
    import("../utils/run-store.server"),
    import("../utils/job-previews.server"),
    import("../utils/asset-thumbnails.server"),
  ]);
  const detail = await getRunDetail(runId);
  if (!detail) {
    throw new Response("Run not found", { status: 404 });
  }
  const renderDateFolder = inferRenderDateFolder(detail.summary);
  const garmentId = detail.summary.garment ?? null;
  const assetLabelMap = new Map<string, string>();
  for (const job of detail.jobs) {
    const assetKey = resolveAssetKey(job);
    if (assetKey && !assetLabelMap.has(assetKey)) {
      assetLabelMap.set(assetKey, job.config?.asset ?? assetKey);
    }
  }

  const assetLibrary: AssetLibraryEntry[] = await Promise.all(
    Array.from(assetLabelMap.entries()).map(async ([assetKey, label]) => ({
      assetKey,
      label,
      thumbnailUrl:
        garmentId && assetKey
          ? await getAssetThumbnailUrl(garmentId, assetKey)
          : null,
    }))
  );
  const assetThumbnailMap = new Map(
    assetLibrary.map((entry) => [entry.assetKey, entry.thumbnailUrl])
  );

  const jobsWithPreview = await Promise.all(
    detail.jobs.map(async (job) => {
      const assetKey = resolveAssetKey(job);
      return {
        ...job,
        preview: await buildJobPreview(job, detail.summary, renderDateFolder),
        assetKey,
        assetThumbnailUrl: assetKey
          ? assetThumbnailMap.get(assetKey) ?? null
          : null,
      };
    })
  );
  return json({
    ...detail,
    jobs: jobsWithPreview,
    renderDateFolder,
    assetLibrary,
  });
}

export async function action({ request }: ActionFunctionArgs) {
  const formData = await request.formData();
  const intent = formData.get("intent");
  if (intent !== "upload-asset-thumbnail") {
    return json({ success: false, error: "Unknown intent" }, { status: 400 });
  }
  const garmentId = formData.get("garmentId");
  const assetKey = formData.get("assetKey");
  const file = formData.get("file");

  if (typeof garmentId !== "string" || !garmentId) {
    return json({ success: false, error: "Missing garment" }, { status: 400 });
  }
  if (typeof assetKey !== "string" || !assetKey) {
    return json({ success: false, error: "Missing asset" }, { status: 400 });
  }
  if (!(file instanceof File)) {
    return json(
      { success: false, error: "Select an image file" },
      { status: 400 }
    );
  }

  try {
    const { saveAssetThumbnail } = await import(
      "../utils/asset-thumbnails.server"
    );
    const result = await saveAssetThumbnail(garmentId, assetKey, file);
    return json({ success: true, url: result.url });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Upload failed";
    return json({ success: false, error: message }, { status: 400 });
  }
}

type LoaderData = Awaited<ReturnType<typeof loader>>;
type JobWithPreview = LoaderData["jobs"][number];

type JobFilter =
  | "all"
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

const jobFilters: { label: string; value: JobFilter }[] = [
  { label: "All", value: "all" },
  { label: "Pending", value: "pending" },
  { label: "Running", value: "running" },
  { label: "Completed", value: "completed" },
  { label: "Failed", value: "failed" },
  { label: "Cancelled", value: "cancelled" },
];

const statusColor: Record<string, string> = {
  running: "blue",
  pending: "gray",
  completed: "green",
  attention: "red",
  failed: "red",
  cancelled: "yellow",
};

export default function RunDetailRoute() {
  const data = useLoaderData<LoaderData>();
  const params = useParams();
  const revalidator = useRevalidator();
  const [jobFilter, setJobFilter] = useState<JobFilter>("all");
  const garmentId = data.summary.garment ?? "";

  useEffect(() => {
    const interval = setInterval(() => {
      revalidator.revalidate();
    }, 5000);
    return () => clearInterval(interval);
  }, [revalidator]);

  useEffect(() => {
    setJobFilter("all");
  }, [params.runId]);

  const filteredJobs = useMemo(() => {
    return data.jobs.filter((job) => {
      const status = job.status?.toLowerCase();
      if (jobFilter === "all") return true;
      if (jobFilter === "failed")
        return ["failed", "error", "errored"].includes(status || "");
      if (jobFilter === "completed")
        return ["completed", "succeeded", "done", "success"].includes(
          status || ""
        );
      if (jobFilter === "running")
        return status === "running" || status === "in_progress";
      if (jobFilter === "cancelled")
        return ["cancelled", "canceled", "aborted"].includes(status || "");
      return status === "pending" || status === "queued";
    });
  }, [data.jobs, jobFilter]);

  return (
    <Container size="xl" py="xl">
      <Stack gap="xl">
        <WorkspaceNav />
        <Group justify="space-between" align="flex-end">
          <Stack gap={4}>
            <Group gap="xs">
              <Anchor component={Link} to="/runs" size="sm" c="grape">
                <Group gap={4}>
                  <IconArrowLeft size={14} />
                  Back to runs
                </Group>
              </Anchor>
            </Group>
            <Title order={2}>Run {data.summary.runId}</Title>
            <Text c="dimmed">
              {data.summary.note || "No operator note recorded."}
            </Text>
          </Stack>
          <Badge
            size="lg"
            color={
              statusColor[data.summary.status?.toLowerCase() ?? "pending"] ??
              "gray"
            }
          >
            {data.summary.status}
          </Badge>
        </Group>

        <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }}>
          <StatCard label="Progress" value={`${data.summary.progressPercent}%`}>
            <Progress
              value={data.summary.progressPercent}
              color="grape"
              radius="xl"
              mt="xs"
            />
          </StatCard>
          <StatCard
            label="Completed"
            value={`${data.summary.completedJobs}/${data.summary.totalJobs}`}
          />
          <StatCard label="Running" value={String(data.summary.runningJobs)} />
          <StatCard
            label="Failed"
            value={String(data.summary.failedJobs)}
            color="red"
          />
        </SimpleGrid>

        {data.assetLibrary.length > 0 && garmentId && (
          <Card withBorder padding="lg" radius="lg">
            <Stack gap="md">
              <Group justify="space-between" align="center">
                <Stack gap={0}>
                  <Text fw={600}>Asset Thumbnails</Text>
                  <Text size="sm" c="dimmed">
                    Upload lightweight previews once per asset to speed up job
                    triage below.
                  </Text>
                </Stack>
                <Text size="sm" c="dimmed">
                  Garment: {garmentId.replace(/\.json$/iu, "")}
                </Text>
              </Group>
              <Divider />
              <AssetThumbnailManager
                assets={data.assetLibrary}
                garmentId={garmentId}
                onUploaded={() => revalidator.revalidate()}
              />
            </Stack>
          </Card>
        )}

        <Card withBorder radius="lg" padding="lg">
          <Stack gap="md">
            <Group justify="space-between">
              <Group gap="xs">
                <IconClipboardList size={18} />
                <Text fw={600}>Metadata</Text>
              </Group>
              <Text size="sm" c="dimmed">
                Last touch {formatTimestamp(data.summary.lastActivity) ?? "—"}
              </Text>
            </Group>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
              <MetaField label="Mode" value={data.summary.mode ?? "—"} />
              <MetaField label="Garment" value={data.summary.garment ?? "—"} />
              <MetaField
                label="Created"
                value={formatTimestamp(data.summary.createdAt) ?? "—"}
              />
              <MetaField
                label="Render Folder"
                value={data.renderDateFolder ?? "—"}
              />
              <MetaField
                label="Operator"
                value={data.summary.createdBy ?? "—"}
              />
            </SimpleGrid>
          </Stack>
        </Card>

        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
          <Card withBorder padding="lg" radius="lg">
            <Group gap="xs" mb="sm">
              <IconArticle size={18} />
              <Text fw={600}>Notes</Text>
            </Group>
            <ScrollArea h={200} offsetScrollbars>
              <Code block style={{ whiteSpace: "pre-wrap" }}>
                {data.notes?.trim() || "(no notes provided)"}
              </Code>
            </ScrollArea>
          </Card>
          <Card withBorder padding="lg" radius="lg">
            <Group gap="xs" mb="sm">
              <IconClipboardList size={18} />
              <Text fw={600}>Plan</Text>
            </Group>
            <ScrollArea h={200} offsetScrollbars>
              <Stack gap="sm">
                {data.plan.length === 0 ? (
                  <Text c="dimmed">No plan items recorded.</Text>
                ) : (
                  data.plan.map((item, index) => (
                    <Code key={index} block>
                      {JSON.stringify(item, null, 2)}
                    </Code>
                  ))
                )}
              </Stack>
            </ScrollArea>
          </Card>
        </SimpleGrid>

        <Card withBorder radius="lg" padding="lg">
          <Stack gap="md">
            <Group justify="space-between" align="flex-start">
              <Stack gap={2}>
                <Text fw={600}>Jobs</Text>
                <Text size="sm" c="dimmed">
                  {filteredJobs.length} of {data.jobs.length} visible
                </Text>
              </Stack>
              <SegmentedControl
                value={jobFilter}
                data={jobFilters}
                onChange={(value) => setJobFilter(value as JobFilter)}
              />
            </Group>
            {!filteredJobs.length ? (
              <Text c="dimmed">No jobs match the selected filter.</Text>
            ) : (
              <Stack gap="sm">
                {filteredJobs.map((job) => (
                  <JobRow key={job.jobId} job={job} />
                ))}
              </Stack>
            )}
          </Stack>
        </Card>
      </Stack>
    </Container>
  );
}

function formatTimestamp(value?: string | null) {
  if (!value) return null;
  try {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value ?? null;
    return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    })}`;
  } catch (error) {
    return value ?? null;
  }
}

function StatCard({
  label,
  value,
  children,
  color,
}: {
  label: string;
  value: string;
  children?: ReactNode;
  color?: string;
}) {
  return (
    <Card withBorder padding="lg" radius="lg">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text fw={700} fz="xl" c={color}>
        {value}
      </Text>
      {children}
    </Card>
  );
}

function MetaField({ label, value }: { label: string; value: string }) {
  return (
    <Stack gap={4}>
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text fw={600}>{value}</Text>
    </Stack>
  );
}

function JobRow({ job }: { job: JobWithPreview }) {
  const statusKey = job.status?.toLowerCase() ?? "pending";
  const badgeColor = statusColor[statusKey] ?? "gray";
  const fabricLabel = formatFabricLabel(job.config?.fabric);
  const assetLabel = formatAssetLabel(
    job.config?.asset ?? job.config?.asset_suffix
  );
  const viewLabel = job.config?.view ?? job.config?.view_output_prefix ?? "—";
  const thumbnail = job.assetThumbnailUrl ?? job.preview?.url ?? null;

  return (
    <Card withBorder padding="md" radius="lg">
      <Group align="flex-start" gap="md">
        <Box style={{ width: 120, flexShrink: 0 }}>
          {thumbnail ? (
            <img
              src={thumbnail}
              alt={`${fabricLabel} ${assetLabel}`}
              style={{
                width: "100%",
                height: 120,
                objectFit: "cover",
                borderRadius: "var(--mantine-radius-md)",
                background: "var(--mantine-color-dark-6)",
              }}
            />
          ) : (
            <Center
              style={{
                width: "100%",
                height: 120,
                borderRadius: "var(--mantine-radius-md)",
                background: "var(--mantine-color-dark-6)",
                color: "var(--mantine-color-dimmed)",
                fontSize: "0.8rem",
                textAlign: "center",
                padding: "var(--mantine-spacing-sm)",
              }}
            >
              No thumbnail
            </Center>
          )}
        </Box>
        <Stack gap="sm" style={{ flex: 1 }}>
          <Group justify="space-between" align="flex-start">
            <Stack gap={0}>
              <Text fw={600}>{fabricLabel}</Text>
              <Text size="sm" c="dimmed">
                {assetLabel} • {viewLabel}
              </Text>
            </Stack>
            <Stack gap={2} align="flex-end">
              <Badge color={badgeColor}>{job.status ?? "pending"}</Badge>
              <Text size="xs" c="dimmed">
                #{job.sequence ?? "—"}
              </Text>
            </Stack>
          </Group>
          <Group gap="lg" align="flex-start" wrap="wrap">
            <Stack gap={0}>
              <Text size="xs" c="dimmed">
                Worker
              </Text>
              <Text fw={500}>{job.worker ?? "unassigned"}</Text>
            </Stack>
            <Stack gap={0}>
              <Text size="xs" c="dimmed">
                Timing
              </Text>
              <Text size="sm">
                {formatTimestamp(job.startedAt) ?? "—"} →{" "}
                {formatTimestamp(job.finishedAt) ?? "—"}
              </Text>
            </Stack>
            <Stack gap={0}>
              <Text size="xs" c="dimmed">
                Job ID
              </Text>
              <Text size="sm" c="dimmed">
                {job.jobId}
              </Text>
            </Stack>
          </Group>
        </Stack>
      </Group>
    </Card>
  );
}

type AssetThumbnailManagerProps = {
  assets: AssetLibraryEntry[];
  garmentId: string;
  onUploaded: () => void;
};

function AssetThumbnailManager({
  assets,
  garmentId,
  onUploaded,
}: AssetThumbnailManagerProps) {
  const fetcher = useFetcher<typeof action>();
  const handleFileChange = useCallback(
    (assetKey: string, event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;
      const formData = new FormData();
      formData.append("intent", "upload-asset-thumbnail");
      formData.append("garmentId", garmentId);
      formData.append("assetKey", assetKey);
      formData.append("file", file);
      fetcher.submit(formData, {
        method: "post",
        encType: "multipart/form-data",
      });
      event.target.value = "";
    },
    [fetcher, garmentId]
  );

  useEffect(() => {
    if (fetcher.data?.success) {
      onUploaded();
    }
  }, [fetcher.data, onUploaded]);

  const uploadError =
    fetcher.data && !fetcher.data.success
      ? fetcher.data.error || "Upload failed"
      : null;

  return (
    <Stack gap="sm">
      {assets.map((asset) => (
        <Card key={asset.assetKey} withBorder padding="sm" radius="md">
          <Group align="center" gap="md">
            <Box style={{ width: 72, height: 72 }}>
              {asset.thumbnailUrl ? (
                <img
                  src={asset.thumbnailUrl}
                  alt={asset.label}
                  style={{
                    width: "100%",
                    height: "100%",
                    objectFit: "cover",
                    borderRadius: "var(--mantine-radius-sm)",
                    background: "var(--mantine-color-dark-6)",
                  }}
                />
              ) : (
                <Center
                  style={{
                    width: "100%",
                    height: "100%",
                    borderRadius: "var(--mantine-radius-sm)",
                    background: "var(--mantine-color-dark-6)",
                    color: "var(--mantine-color-dimmed)",
                    fontSize: "0.75rem",
                  }}
                >
                  None
                </Center>
              )}
            </Box>
            <Stack gap={2} style={{ flex: 1 }}>
              <Text fw={600}>{asset.label}</Text>
              <Text size="xs" c="dimmed">
                {asset.assetKey}
              </Text>
              {asset.thumbnailUrl && (
                <Anchor
                  href={asset.thumbnailUrl}
                  target="_blank"
                  rel="noreferrer"
                  size="xs"
                >
                  Open thumbnail
                </Anchor>
              )}
            </Stack>
            <Button
              variant="light"
              size="xs"
              component="label"
              disabled={fetcher.state !== "idle"}
            >
              Upload
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                hidden
                onChange={(event) => handleFileChange(asset.assetKey, event)}
              />
            </Button>
          </Group>
        </Card>
      ))}
      {uploadError && (
        <Alert color="red" title="Upload failed">
          {uploadError}
        </Alert>
      )}
    </Stack>
  );
}

function formatFabricLabel(value?: string | null) {
  if (!value) return "—";
  return value
    .replace(/\.json$/iu, "")
    .replace(/[_-]+/gu, " ")
    .split(/\s+/u)
    .filter(Boolean)
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

function formatAssetLabel(value?: string | null) {
  if (!value) return "—";
  return value
    .replace(/[_-]+/gu, " ")
    .split(/\s+/u)
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

function resolveAssetKey(job: RunJobRecord): string | null {
  const suffix = job.config?.asset_suffix;
  if (suffix) {
    return slugifyKey(suffix);
  }
  const assetName = job.config?.asset;
  if (!assetName) return null;
  return slugifyKey(assetName);
}

function slugifyKey(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/gu, "_")
    .replace(/^_+|_+$/g, "");
}
