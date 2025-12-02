import { json } from "@remix-run/node";
import type { LoaderFunctionArgs } from "@remix-run/node";
import { useLoaderData, useRevalidator } from "@remix-run/react";
import {
  Badge,
  Card,
  Container,
  Group,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { useEffect } from "react";
import { WorkspaceNav } from "../components/workspace-nav";

const HEALTH_THRESHOLDS = {
  healthy: 30,
  stale: 120,
};

function classifyFreshness(
  ageSeconds: number | null
): "healthy" | "stale" | "offline" | "unknown" {
  if (ageSeconds === null) return "unknown";
  if (ageSeconds < HEALTH_THRESHOLDS.healthy) return "healthy";
  if (ageSeconds < HEALTH_THRESHOLDS.stale) return "stale";
  return "offline";
}

function formatAge(ageSeconds: number | null): string {
  if (ageSeconds === null) return "unknown";
  if (ageSeconds < 60) return `${Math.max(0, Math.round(ageSeconds))}s ago`;
  const minutes = ageSeconds / 60;
  if (minutes < 60) return `${Math.round(minutes)}m ago`;
  const hours = minutes / 60;
  return `${hours.toFixed(1)}h ago`;
}

const badgeColorMap: Record<ReturnType<typeof classifyFreshness>, string> = {
  healthy: "green",
  stale: "yellow",
  offline: "red",
  unknown: "gray",
};

type WorkerSummary = {
  workerId: string;
  hostname?: string;
  mode?: string;
  status: string;
  activeJobId?: string;
  ageSeconds: number | null;
  freshness: ReturnType<typeof classifyFreshness>;
};

export async function loader({}: LoaderFunctionArgs) {
  const { listWorkerHeartbeats } = await import("../utils/worker-store.server");
  const workers = await listWorkerHeartbeats();
  const now = Date.now();
  const summaries: WorkerSummary[] = workers.map((worker) => {
    const lastSeen = worker.lastSeen ? Date.parse(worker.lastSeen) : NaN;
    const ageSeconds = Number.isFinite(lastSeen)
      ? Math.max(0, (now - lastSeen) / 1000)
      : null;
    const freshness = classifyFreshness(ageSeconds);
    return {
      workerId: worker.workerId,
      hostname: worker.hostname,
      mode: worker.mode,
      status: worker.status,
      activeJobId: worker.activeJobId,
      ageSeconds,
      freshness,
    };
  });

  summaries.sort((a, b) => (a.workerId ?? "").localeCompare(b.workerId ?? ""));

  return json({
    workers: summaries,
    generatedAt: new Date().toISOString(),
  });
}

export default function MeshRoute() {
  const { workers, generatedAt } = useLoaderData<typeof loader>();
  const revalidator = useRevalidator();

  useEffect(() => {
    const interval = setInterval(() => {
      revalidator.revalidate();
    }, 5000);
    return () => clearInterval(interval);
  }, [revalidator]);

  return (
    <Container size="xl" py="xl">
      <Stack gap="lg">
        <WorkspaceNav />
        <Group justify="space-between" align="flex-end">
          <Stack gap={4}>
            <Title order={2}>Mesh Overview</Title>
            <Text c="dimmed">
              Live view of all worker nodes broadcasting heartbeats. Data
              refreshed {new Date(generatedAt).toLocaleTimeString()}.
            </Text>
          </Stack>
        </Group>

        <Card withBorder radius="lg" padding="lg">
          {workers.length === 0 ? (
            <Text>No workers have reported in yet.</Text>
          ) : (
            <Table highlightOnHover withColumnBorders>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Worker</Table.Th>
                  <Table.Th>Mode</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Active Job</Table.Th>
                  <Table.Th>Last Seen</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {workers.map((worker) => (
                  <Table.Tr key={worker.workerId}>
                    <Table.Td>
                      <Stack gap={2}>
                        <Text fw={600}>{worker.workerId}</Text>
                        <Text size="sm" c="dimmed">
                          {worker.hostname ?? "—"}
                        </Text>
                      </Stack>
                    </Table.Td>
                    <Table.Td>
                      <Badge color="blue" variant="light">
                        {worker.mode ?? "node"}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Badge color={badgeColorMap[worker.freshness]}>
                        {worker.status}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text>{worker.activeJobId ?? "—"}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs">
                        <Text>{formatAge(worker.ageSeconds)}</Text>
                        <Badge
                          color={badgeColorMap[worker.freshness]}
                          variant="outline"
                        >
                          {worker.freshness}
                        </Badge>
                      </Group>
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
