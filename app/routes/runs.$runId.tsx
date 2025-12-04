import { json, redirect } from "@remix-run/node";
import type { ActionFunctionArgs, LoaderFunctionArgs } from "@remix-run/node";
import { Form, Link, useLoaderData, useNavigation, useParams, useRevalidator } from "@remix-run/react";
import {
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
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import {
  IconArrowLeft,
  IconArticle,
  IconClipboardList,
  IconPlayerPause,
  IconPlayerPlay,
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
    { getRunDetail, getRunStateEntry, setAllowedWorkersMetadata, deleteRun },
    { buildJobPreview, inferRenderDateFolder },
  ] = await Promise.all([
    import("../utils/run-store.server"),
    import("../utils/job-previews.server"),
  ]);
  const detail = await getRunDetail(runId);
  if (!detail) {
    throw new Response("Run not found", { status: 404 });
  }
  const runState = await getRunStateEntry(runId);
  const allowedWorkers =
    (Array.isArray(detail.summary.allowedWorkers) && detail.summary.allowedWorkers) ||
    (Array.isArray((detail.metadata as any)?.allowed_workers) && (detail.metadata as any)?.allowed_workers) ||
    [];
  const renderDateFolder = inferRenderDateFolder(detail.summary);

  const jobsWithPreview = await Promise.all(
    detail.jobs.map(async (job) => {
      const remoteAssetUrl =
        buildAssetPublicUrl(job.result?.gallery ?? null) ??
        buildAssetPublicUrl(job.result?.uploaded ?? null) ??
        null;
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
    paused: Boolean(runState?.paused),
    allowedWorkers,
  });
}

export async function action({ request, params }: ActionFunctionArgs) {
  const runId = params.runId;
  if (!runId) {
    throw new Response("Run ID required", { status: 400 });
  }
  const formData = await request.formData();
  const intent = formData.get("intent");

  if (intent === "toggle-pause") {
    const desired = formData.get("paused") === "true";
    const { setRunPaused } = await import("../utils/run-store.server");
    await setRunPaused(runId, desired);
    return redirect(`/runs/${runId}`);
  }

  if (intent === "update-allowed-workers") {
    const raw = formData.get("workers");
    const { setAllowedWorkersMetadata } = await import("../utils/run-store.server");
    const list =
      typeof raw === "string"
        ? raw
            .split(/[\n,]/)
            .map((v) => v.trim())
            .filter(Boolean)
        : [];
    await setAllowedWorkersMetadata(runId, Array.from(new Set(list)));
    return redirect(`/runs/${runId}`);
  }

  if (intent === "delete-run") {
    const confirm = formData.get("confirm");
    const expected = `delete ${runId}`;
    if (typeof confirm !== "string" || confirm.trim().toLowerCase() !== expected.toLowerCase()) {
      return json(
        { success: false, error: `Type '${expected}' to confirm deletion.` },
        { status: 400 }
      );
    }
    const { deleteRun } = await import("../utils/run-store.server");
    await deleteRun(runId);
    return redirect("/runs");
  }

  return json({ success: false, error: "Unknown intent" }, { status: 400 });
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
  const navigation = useNavigation();
  const [allowedWorkersValue, setAllowedWorkersValue] = useState(
    data.allowedWorkers?.join(", ") ?? ""
  );
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

  useEffect(() => {
    setAllowedWorkersValue(data.allowedWorkers?.join(", ") ?? "");
  }, [data.allowedWorkers]);

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
          <Group gap="sm">
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
        </Group>

        <Card withBorder radius="lg" padding="lg">
          <Stack gap="md">
            <Group justify="space-between" align="center">
              <Text fw={600}>Run controls</Text>
              <Badge color={data.paused ? "red" : "green"} variant="light">
                {data.paused ? "Paused" : "Active"}
              </Badge>
            </Group>
            <Group wrap="wrap" gap="sm">
              <Form method="post" replace>
                <input type="hidden" name="intent" value="toggle-pause" />
                <input type="hidden" name="paused" value={String(!data.paused)} />
                <Button
                  type="submit"
                  color={data.paused ? "green" : "yellow"}
                  leftSection={data.paused ? <IconPlayerPlay size={14} /> : <IconPlayerPause size={14} />}
                  loading={navigation.state === "submitting"}
                >
                  {data.paused ? "Resume run" : "Pause run"}
                </Button>
              </Form>
            </Group>
            <Divider />
            <Stack gap="xs">
              <Text fw={600}>Allowed workers</Text>
              <Text size="sm" c="dimmed">
                Limit this run to specific worker IDs (comma or newline separated). Leave blank to allow all workers.
              </Text>
              <Form method="post" replace>
                <input type="hidden" name="intent" value="update-allowed-workers" />
                <Textarea
                  name="workers"
                  minRows={2}
                  value={allowedWorkersValue}
                  onChange={(event) => setAllowedWorkersValue(event.currentTarget.value)}
                  placeholder="worker-1, worker-2"
                />
                <Button type="submit" mt="sm" variant="light">
                  Save worker restrictions
                </Button>
              </Form>
            </Stack>
            <Divider />
            <Stack gap="xs">
              <Text fw={600} c="red">
                Delete run
              </Text>
              <Text size="sm" c="dimmed">
                Type <Code>delete {data.summary.runId}</Code> to confirm permanent deletion (including S3 objects).
              </Text>
              <Form method="post" replace>
                <input type="hidden" name="intent" value="delete-run" />
                <TextInput
                  name="confirm"
                  placeholder={`delete ${data.summary.runId}`}
                  required
                />
                <Button type="submit" color="red" variant="light" mt="sm">
                  Delete run
                </Button>
              </Form>
            </Stack>
          </Stack>
        </Card>

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
