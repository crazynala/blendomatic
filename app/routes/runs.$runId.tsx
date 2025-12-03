import { json } from "@remix-run/node";
import type { LoaderFunctionArgs } from "@remix-run/node";
import { Link, useLoaderData, useParams, useRevalidator } from "@remix-run/react";
import {
  Anchor,
  Badge,
  Box,
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
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { WorkspaceNav } from "../components/workspace-nav";
import { buildAssetPublicUrl } from "../utils/asset-urls.server";

export async function loader({ params }: LoaderFunctionArgs) {
  const runId = params.runId;
  if (!runId) {
    throw new Response("Run ID required", { status: 400 });
  }
  const [
    { getRunDetail },
    { buildJobPreview, inferRenderDateFolder },
  ] = await Promise.all([
    import("../utils/run-store.server"),
    import("../utils/job-previews.server"),
  ]);
  const detail = await getRunDetail(runId);
  if (!detail) {
    throw new Response("Run not found", { status: 404 });
  }
  const renderDateFolder = inferRenderDateFolder(detail.summary);

  const jobsWithPreview = await Promise.all(
    detail.jobs.map(async (job) => {
      const remoteAssetUrl =
        buildAssetPublicUrl(job.result?.uploaded ?? null) ?? null;
      const remoteThumbnailUrl =
        buildAssetPublicUrl(job.result?.thumbnail ?? null) ??
        remoteAssetUrl ??
        null;
      return {
        ...job,
        preview: await buildJobPreview(job, detail.summary, renderDateFolder),
        remoteAssetUrl: remoteAssetUrl ?? null,
        remoteThumbnailUrl:
          remoteThumbnailUrl ??
          (job.preview?.url ?? null),
      };
    })
  );
  return json({
    ...detail,
    jobs: jobsWithPreview,
    renderDateFolder,
  });
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
  const thumbnail =
    job.remoteThumbnailUrl ?? job.remoteAssetUrl ?? job.preview?.url ?? null;

  return (
    <Card withBorder padding="md" radius="lg">
      <Group align="flex-start" gap="md">
        <Stack gap={4} style={{ width: 120, flexShrink: 0 }}>
          <Box>
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
          {job.remoteAssetUrl && (
            <Anchor
              href={job.remoteAssetUrl}
              target="_blank"
              rel="noreferrer"
              size="xs"
            >
              Open render
            </Anchor>
          )}
        </Stack>
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
