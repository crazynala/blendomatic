import { json } from "@remix-run/node";
import type { LoaderFunctionArgs } from "@remix-run/node";
import {
  Link,
  useLoaderData,
  useRevalidator,
  useSearchParams,
} from "@remix-run/react";
import {
  Badge,
  Button,
  Card,
  Container,
  Group,
  Progress,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import {
  IconAlertTriangle,
  IconPlus,
} from "@tabler/icons-react";
import { useEffect, useMemo } from "react";
import {
  loadRunFormOptions,
} from "../utils/run-planner.server";
import { listRunSummaries } from "../utils/run-store.server";
import { WorkspaceNav } from "../components/workspace-nav";

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const filter = url.searchParams.get("filter") ?? "all";
  const summaries = await listRunSummaries(200);
  const runOptions = await loadRunFormOptions();
  const canCreateRuns =
    runOptions.modes.length > 0 &&
    runOptions.garments.length > 0 &&
    runOptions.fabrics.length > 0;
  return json({ summaries, filter, canCreateRuns });
}

type LoaderData = {
  summaries: Awaited<ReturnType<typeof listRunSummaries>>;
  filter: string;
  canCreateRuns: boolean;
};

type FilterKey = "all" | "active" | "attention" | "completed" | "pending";

const filterOptions: { label: string; value: FilterKey }[] = [
  { label: "All", value: "all" },
  { label: "Active", value: "active" },
  { label: "Attention", value: "attention" },
  { label: "Completed", value: "completed" },
  { label: "Queued", value: "pending" },
];

const statusColor: Record<string, string> = {
  running: "blue",
  pending: "gray",
  completed: "green",
  attention: "red",
  queued: "gray",
};

function categorizeRuns(summaries: LoaderData["summaries"]) {
  let active = 0;
  let attention = 0;
  let completed = 0;
  let queued = 0;
  for (const run of summaries) {
    const status = run.status?.toLowerCase();
    if (status === "completed") {
      completed += 1;
    } else if (status === "attention") {
      attention += 1;
    } else if (status === "running") {
      active += 1;
    } else {
      queued += 1;
    }
  }
  return { total: summaries.length, active, attention, completed, queued };
}

export default function RunsIndexRoute() {
  const { summaries, filter, canCreateRuns } = useLoaderData<LoaderData>();
  const [searchParams, setSearchParams] = useSearchParams();
  const revalidator = useRevalidator();

  useEffect(() => {
    const interval = setInterval(() => {
      revalidator.revalidate();
    }, 7000);
    return () => clearInterval(interval);
  }, [revalidator]);

  const stats = useMemo(() => categorizeRuns(summaries), [summaries]);

  const filteredRuns = useMemo(() => {
    return summaries.filter((run) => {
      const status = run.status?.toLowerCase();
      switch (filter as FilterKey) {
        case "active":
          return status === "running";
        case "attention":
          return status === "attention" || run.failedJobs > 0;
        case "completed":
          return status === "completed";
        case "pending":
          return status === "pending" || status === "queued";
        default:
          return true;
      }
    });
  }, [summaries, filter]);

  const handleFilterChange = (value: string) => {
    const selected = (value as FilterKey) ?? "all";
    const next = new URLSearchParams(searchParams);
    if (selected === "all") {
      next.delete("filter");
    } else {
      next.set("filter", selected);
    }
    setSearchParams(next);
  };

  const creationDisabled = !canCreateRuns;

  return (
    <Container size="xl" py="xl">
      <Stack gap="xl">
        <WorkspaceNav />
        <Group justify="space-between" align="flex-start">
          <Stack gap={4}>
            <Title order={2}>Run Control</Title>
            <Text c="dimmed">
              Monitor every render run, drill into problem jobs, and spin up new
              plans once nodes are ready.
            </Text>
          </Stack>
          <Button
            component={Link}
            to="/runs/new"
            variant="filled"
            color="grape"
            leftSection={<IconPlus size={16} />}
            disabled={creationDisabled}
          >
            New Run
          </Button>
        </Group>

        <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }}>
          <Card withBorder padding="lg" radius="lg">
            <Text size="sm" c="dimmed">
              Total Runs
            </Text>
            <Text fw={700} fz="xl">
              {stats.total}
            </Text>
          </Card>
          <Card withBorder padding="lg" radius="lg">
            <Text size="sm" c="dimmed">
              Active
            </Text>
            <Text fw={700} fz="xl" c="blue">
              {stats.active}
            </Text>
          </Card>
          <Card withBorder padding="lg" radius="lg">
            <Text size="sm" c="dimmed">
              Attention Needed
            </Text>
            <Group gap="xs">
              <Text fw={700} fz="xl" c="red">
                {stats.attention}
              </Text>
              {stats.attention > 0 && (
                <IconAlertTriangle
                  size={20}
                  color="var(--mantine-color-red-5)"
                />
              )}
            </Group>
          </Card>
          <Card withBorder padding="lg" radius="lg">
            <Text size="sm" c="dimmed">
              Completed
            </Text>
            <Text fw={700} fz="xl" c="green">
              {stats.completed}
            </Text>
          </Card>
        </SimpleGrid>

        <Card withBorder radius="lg" padding="lg">
          <Group justify="space-between" align="center" mb="md">
            <Stack gap={2}>
              <Text fw={600}>Run Queue</Text>
              <Text size="sm" c="dimmed">
                Filter by state to focus on active or blocked runs. Data
                refreshes automatically.
              </Text>
            </Stack>
            <SegmentedControl
              value={(filter as FilterKey) ?? "all"}
              data={filterOptions}
              onChange={handleFilterChange}
            />
          </Group>

          {!filteredRuns.length ? (
            <Text c="dimmed">No runs match the selected filter.</Text>
          ) : (
            <Table highlightOnHover withColumnBorders>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>ID</Table.Th>
                  <Table.Th>Mode</Table.Th>
                  <Table.Th>Jobs</Table.Th>
                  <Table.Th>Progress</Table.Th>
                  <Table.Th>Last Activity</Table.Th>
                  <Table.Th>Status</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {filteredRuns.map((run) => (
                  <Table.Tr key={run.runId}>
                    <Table.Td>
                      <Button
                        component={Link}
                        to={`/runs/${run.runId}`}
                        variant="subtle"
                        color="grape"
                        size="compact-sm"
                      >
                        {run.runId}
                      </Button>
                      <Text size="xs" c="dimmed">
                        {run.note || "(no note)"}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Stack gap={2}>
                        <Text fw={600}>{run.mode ?? "—"}</Text>
                        <Text size="xs" c="dimmed">
                          {run.garment ?? "All garments"}
                        </Text>
                      </Stack>
                    </Table.Td>
                    <Table.Td>
                      <Text>
                        {run.completedJobs}/{run.totalJobs}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {run.runningJobs} running / {run.pendingJobs} queued
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Stack gap={4}>
                        <Progress
                          value={run.progressPercent}
                          color="grape"
                          size="lg"
                          radius="xl"
                        />
                        <Text size="xs" c="dimmed">
                          {run.progressPercent}% complete
                        </Text>
                      </Stack>
                    </Table.Td>
                    <Table.Td>
                      <Text>{formatTimestamp(run.lastActivity) || "—"}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge
                        color={
                          statusColor[run.status?.toLowerCase() ?? "pending"] ??
                          "gray"
                        }
                      >
                        {run.status}
                      </Badge>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Card>
      </Stack>
    </Container>
  );
}

function formatTimestamp(value?: string) {
  if (!value) return null;
  try {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    })}`;
  } catch (error) {
    return value;
  }
}
