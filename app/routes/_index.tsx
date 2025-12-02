import { json } from "@remix-run/node";
import type { LoaderFunctionArgs } from "@remix-run/node";
import { useLoaderData, useNavigate, useSearchParams } from "@remix-run/react";
import {
  Alert,
  Badge,
  Box,
  Card,
  Container,
  Divider,
  Group,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { describeRenders, type LayerEntry } from "../utils/gallery.server";
import { listRunSummaries } from "../utils/run-store.server";
import { WorkspaceNav } from "../components/workspace-nav";

type ConfigState = Record<string, string>;

const canvasStyles: Record<"outer" | "inner" | "layer", CSSProperties> = {
  outer: {
    borderRadius: "var(--mantine-radius-lg)",
    background: "var(--mantine-color-dark-6)",
    padding: "var(--mantine-spacing-sm)",
  },
  inner: {
    position: "relative",
    width: "100%",
    paddingBottom: "135%",
  },
  layer: {
    position: "absolute",
    inset: 0,
    width: "100%",
    height: "100%",
    objectFit: "contain",
  },
};

const runStatusColor: Record<string, string> = {
  running: "blue",
  pending: "gray",
  completed: "green",
  attention: "red",
};

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const requestedRun = url.searchParams.get("run");
  const runs = await listRunSummaries(200);
  const selectedRun =
    runs.find((entry) => entry.runId === requestedRun) ?? runs[0] ?? null;
  const renderFolder = selectedRun
    ? deriveRenderFolder(selectedRun.createdAt ?? selectedRun.lastActivity)
    : null;
  const galleryData = await describeRenders(
    selectedRun?.mode ?? null,
    renderFolder
  );
  return json({
    runs,
    selectedRunId: selectedRun?.runId ?? null,
    renderFolder,
    gallery: galleryData.gallery,
    configOptions: galleryData.configOptions,
  });
}

type LoaderData = Awaited<ReturnType<typeof loader>>;

const createInitialConfig = (
  options: LoaderData["configOptions"]
): ConfigState => {
  return Object.fromEntries(
    Object.entries(options).map(([key, config]) => [
      key,
      config.defaultValue ?? config.values[0]?.value ?? "",
    ])
  );
};

const deriveRenderFolder = (timestamp?: string | null) => {
  if (!timestamp) return null;
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString().slice(0, 10);
};

const formatRunTimestamp = (value?: string | null) => {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  })}`;
};

export default function GalleryRoute() {
  const { runs, selectedRunId, renderFolder, gallery, configOptions } =
    useLoaderData<typeof loader>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [config, setConfig] = useState<ConfigState>(() =>
    createInitialConfig(configOptions)
  );

  useEffect(() => {
    setConfig(createInitialConfig(configOptions));
  }, [configOptions]);

  const categoryKeys = useMemo(
    () => Object.keys(configOptions),
    [configOptions]
  );

  const runOptions = useMemo(
    () =>
      runs.map((run) => ({
        value: run.runId,
        label: `${run.runId} • ${run.mode ?? "–"} • ${
          formatRunTimestamp(run.createdAt) ?? "unknown"
        }`,
      })),
    [runs]
  );

  const selectedRun = useMemo(
    () => runs.find((run) => run.runId === selectedRunId) ?? null,
    [runs, selectedRunId]
  );

  const flattenedFabrics = useMemo(() => {
    return gallery.flatMap((entry) =>
      entry.fabrics.map((fabric) => ({
        id: `${entry.id}:${fabric.key}`,
        garmentName: entry.garmentName,
        viewLabel: entry.viewLabel,
        fabric,
      }))
    );
  }, [gallery]);

  const handleRunChange = (value: string | null) => {
    const params = new URLSearchParams(searchParams);
    if (value) {
      params.set("run", value);
    } else {
      params.delete("run");
    }
    const query = params.toString();
    navigate(query ? `/?${query}` : "/");
  };

  const computeVisibleLayers = (layers: LayerEntry[]): LayerEntry[] => {
    if (!Array.isArray(layers) || layers.length === 0) {
      return [];
    }
    const grouped = layers.reduce<Record<string, LayerEntry[]>>(
      (acc, layer) => {
        const key = layer.category ?? "base";
        if (!acc[key]) acc[key] = [];
        acc[key].push(layer);
        return acc;
      },
      {}
    );

    const visible: LayerEntry[] = [];

    for (const layer of layers) {
      if (!layer.category) {
        visible.push(layer);
        continue;
      }
      const selectedValue = layer.category ? config[layer.category] : undefined;
      if (!selectedValue || layer.optionValue === selectedValue) {
        visible.push(layer);
      }
    }

    for (const category of categoryKeys) {
      if (visible.some((layer) => layer.category === category)) continue;
      if (grouped[category] && grouped[category].length > 0) {
        visible.push(grouped[category][0]);
      }
    }

    if (!visible.length && grouped.base && grouped.base.length > 0) {
      visible.push(...grouped.base);
    }

    return visible.sort(
      (a, b) => a.order - b.order || a.label.localeCompare(b.label)
    );
  };

  return (
    <Container size="xl" py="xl">
      <Stack gap="xl">
        <WorkspaceNav />
        <Stack gap="xs">
          <Title order={2}>Render Explorer</Title>
          <Text c="dimmed">
            Browse completed renders, compare fabrics, and adjust the global
            configuration controls to see how each garment responds.
          </Text>
        </Stack>

        <Card withBorder radius="lg" padding="lg">
          <Stack gap="md">
            <Stack gap="sm">
              <Select
                label="Run"
                placeholder="Select a run"
                data={runOptions}
                value={selectedRunId}
                onChange={handleRunChange}
                searchable
                allowDeselect={false}
                nothingFound="No runs"
                disabled={!runOptions.length}
              />
              {selectedRun ? (
                <Group justify="space-between" align="flex-start">
                  <Stack gap={4}>
                    <Text fw={600}>Run {selectedRun.runId}</Text>
                    <Text size="sm" c="dimmed">
                      Mode {selectedRun.mode ?? "—"} • Folder{" "}
                      {renderFolder ?? "—"}
                    </Text>
                    <Text size="sm" c="dimmed">
                      {selectedRun.note?.trim() || "No operator note"}
                    </Text>
                    <Text size="sm">
                      {selectedRun.completedJobs}/{selectedRun.totalJobs}{" "}
                      completed
                    </Text>
                  </Stack>
                  <Badge
                    color={
                      runStatusColor[
                        selectedRun.status?.toLowerCase() ?? "pending"
                      ] ?? "gray"
                    }
                  >
                    {selectedRun.status ?? "pending"}
                  </Badge>
                </Group>
              ) : (
                <Text c="dimmed">No runs available yet.</Text>
              )}
            </Stack>

            <Divider label="Configuration" labelPosition="center" />

            <SimpleGrid cols={{ base: 1, sm: 3 }}>
              {categoryKeys.map((key) => {
                const option = configOptions[key];
                return (
                  <Stack gap={"xs"} key={key}>
                    <Text fw={600}>{option.label}</Text>
                    <SegmentedControl
                      value={config[key]}
                      onChange={(value) =>
                        setConfig((prev) => ({ ...prev, [key]: value }))
                      }
                      fullWidth
                      data={option.values.map((value) => ({
                        label: value.label,
                        value: value.value,
                      }))}
                    />
                  </Stack>
                );
              })}
            </SimpleGrid>
          </Stack>
        </Card>

        {!flattenedFabrics.length ? (
          <Alert title="No renders found" color="yellow" variant="filled">
            We couldn&apos;t find any PNG outputs for this run. Try a different
            run once additional renders are available.
          </Alert>
        ) : (
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="lg">
            {flattenedFabrics.map((card) => {
              const layers = computeVisibleLayers(card.fabric.layers);
              return (
                <Card key={card.id} withBorder padding="lg" radius="lg">
                  <Stack gap="sm">
                    <Group justify="space-between">
                      <div>
                        <Text fw={600}>{card.garmentName}</Text>
                        <Text size="sm" c="dimmed">
                          {card.fabric.label}
                        </Text>
                      </div>
                      <Badge variant="light">{card.viewLabel}</Badge>
                    </Group>

                    <Box style={canvasStyles.outer}>
                      <Box style={canvasStyles.inner}>
                        {layers.length ? (
                          layers.map((layer) => (
                            <img
                              key={`${card.id}-${layer.suffix}`}
                              src={layer.url}
                              alt={`${card.fabric.label} ${layer.label}`}
                              style={canvasStyles.layer}
                            />
                          ))
                        ) : (
                          <Box
                            style={{
                              position: "absolute",
                              inset: 0,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                            }}
                          >
                            <Text size="sm" c="dimmed">
                              No layers available
                            </Text>
                          </Box>
                        )}
                      </Box>
                    </Box>
                  </Stack>
                </Card>
              );
            })}
          </SimpleGrid>
        )}
      </Stack>
    </Container>
  );
}
