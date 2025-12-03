import { json } from "@remix-run/node";
import type { LoaderFunctionArgs } from "@remix-run/node";
import { Link, useLoaderData, useSearchParams } from "@remix-run/react";
import {
  Anchor,
  Badge,
  Box,
  Button,
  Card,
  Container,
  Group,
  Modal,
  SegmentedControl,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { IconArrowLeft, IconArrowsMaximize } from "@tabler/icons-react";
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { WorkspaceNav } from "../components/workspace-nav";
import { describeRenders, type LayerEntry } from "../utils/gallery.server";
import { listRunSummaries, getRunDetail } from "../utils/run-store.server";

type ConfigState = Record<string, string>;

const imageSizeOptions = [
  { label: "400px", value: "400" },
  { label: "800px", value: "800" },
  { label: "1200px", value: "1200" },
];

type LoaderData = Awaited<ReturnType<typeof loader>>;

const buildCanvasStyles = (dimension: number): Record<"outer" | "inner" | "layer", CSSProperties> => ({
  outer: {
    borderRadius: "var(--mantine-radius-lg)",
    background: "var(--mantine-color-dark-6)",
    padding: "var(--mantine-spacing-sm)",
    width: dimension,
    height: dimension,
  },
  inner: {
    position: "relative",
    width: "100%",
    height: "100%",
  },
  layer: {
    position: "absolute",
    inset: 0,
    width: "100%",
    height: "100%",
    objectFit: "contain",
  },
});

const deriveRenderFolder = (timestamp?: string | null) => {
  if (!timestamp) return null;
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString().slice(0, 10);
};

const createInitialConfig = (options: LoaderData["configOptions"]): ConfigState => {
  return Object.fromEntries(
    Object.entries(options).map(([key, config]) => [
      key,
      config.defaultValue ?? config.values[0]?.value ?? "",
    ])
  );
};

export async function loader({ request, params }: LoaderFunctionArgs) {
  const itemId = params.itemId;
  if (!itemId) {
    throw new Response("Item id is required", { status: 400 });
  }

  const url = new URL(request.url);
  const requestedRun = url.searchParams.get("run");

  const runs = await listRunSummaries(200);
  const selectedRun =
    runs.find((entry) => entry.runId === requestedRun) ?? runs[0] ?? null;

  if (!selectedRun) {
    throw new Response("No runs available", { status: 404 });
  }

  const renderFolder = deriveRenderFolder(selectedRun.createdAt ?? selectedRun.lastActivity);
  const runDetail = await getRunDetail(selectedRun.runId);
  const galleryData = await describeRenders(
    selectedRun.mode ?? null,
    renderFolder,
    runDetail?.jobs ?? []
  );

  let target = null as null | {
    entry: (typeof galleryData.gallery)[number];
    fabric: (typeof galleryData.gallery)[number]["fabrics"][number];
  };

  for (const entry of galleryData.gallery) {
    for (const fabric of entry.fabrics) {
      const cardId = `${entry.id}-${fabric.key}`;
      if (cardId === itemId) {
        target = { entry, fabric };
        break;
      }
    }
    if (target) break;
  }

  if (!target) {
    throw new Response("Gallery item not found", { status: 404 });
  }

  return json({
    runs,
    selectedRunId: selectedRun.runId,
    renderFolder,
    entry: target.entry,
    fabric: target.fabric,
    configOptions: galleryData.configOptions,
  });
}

export default function GalleryDetailRoute() {
  const { entry, fabric, configOptions, selectedRunId } = useLoaderData<LoaderData>();
  const [searchParams] = useSearchParams();
  const [config, setConfig] = useState<ConfigState>(() =>
    createInitialConfig(configOptions)
  );
  const [imageSize, setImageSize] = useState(imageSizeOptions[1].value);
  const [activeAsset, setActiveAsset] = useState<LayerEntry | null>(null);

  useEffect(() => {
    setConfig(createInitialConfig(configOptions));
  }, [configOptions]);

  const imageDimension = Number(imageSize);
  const canvasStyles = useMemo(
    () => buildCanvasStyles(imageDimension),
    [imageDimension]
  );

  const categoryKeys = useMemo(
    () => Object.keys(configOptions),
    [configOptions]
  );

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

  const visibleLayers = computeVisibleLayers(fabric.layers);

  const backHref = useMemo(() => {
    const params = new URLSearchParams(searchParams);
    const runParam = params.get("run") ?? selectedRunId;
    const query = runParam ? `?run=${runParam}` : "";
    return `/${query}`;
  }, [searchParams, selectedRunId]);

  return (
    <Container size="xl" py="xl">
      <Stack gap="xl">
        <WorkspaceNav />
        <Group justify="space-between" align="flex-end">
          <Stack gap={4}>
            <Anchor component={Link} to={backHref} c="grape" size="sm">
              <Group gap={4}>
                <IconArrowLeft size={14} />
                Back to gallery
              </Group>
            </Anchor>
            <Title order={2}>
              {entry.garmentName} • {fabric.label} • {entry.viewLabel}
            </Title>
            <Text c="dimmed">
              Adjust configuration controls to preview alternate layer combinations.
            </Text>
          </Stack>
          <Badge variant="light">Run {selectedRunId}</Badge>
        </Group>

        <Group align="flex-start" wrap="wrap" gap="xl">
          <Stack gap="md" style={{ flex: "1 1 520px" }}>
            <Card withBorder radius="lg" padding="lg">
              <Stack gap="md">
                <Group justify="space-between">
                  <Text fw={600}>Composite</Text>
                  <SegmentedControl
                    value={imageSize}
                    onChange={(value) => setImageSize(value)}
                    data={imageSizeOptions}
                    color="grape"
                    aria-label="Image size"
                    size="sm"
                  />
                </Group>
                <Box style={canvasStyles.outer}>
                  <Box style={canvasStyles.inner}>
                    {visibleLayers.length ? (
                      visibleLayers.map((layer) => (
                        <img
                          key={`${layer.suffix}-${layer.label}`}
                          src={layer.url}
                          alt={layer.label}
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
          </Stack>

          <Card withBorder radius="lg" padding="lg" style={{ width: 320 }}>
            <Stack gap="md">
              <Group gap={6}>
                <IconArrowsMaximize size={16} />
                <Text fw={600}>Configuration</Text>
              </Group>
              {Object.entries(configOptions).map(([key, option]) => (
                <Stack gap={4} key={key}>
                  <Text size="sm" c="dimmed">
                    {option.label}
                  </Text>
                  <SegmentedControl
                    value={config[key]}
                    onChange={(value) => setConfig((prev) => ({ ...prev, [key]: value }))}
                    fullWidth
                    data={option.values.map((value) => ({
                      label: value.label,
                      value: value.value,
                    }))}
                  />
                </Stack>
              ))}
            </Stack>
          </Card>
        </Group>

        <Card withBorder radius="lg" padding="lg">
          <Stack gap="md">
            <Text fw={600}>Assets</Text>
            <Group align="stretch" gap="md">
              {fabric.layers.map((layer) => (
                <Card
                  key={`${layer.suffix}-${layer.label}`}
                  withBorder
                  padding="sm"
                  radius="md"
                  style={{ width: 180 }}
                >
                  <Stack gap="xs">
                    <Box
                      component="button"
                      type="button"
                      style={{
                        padding: 0,
                        border: "none",
                        background: "transparent",
                        cursor: "pointer",
                      }}
                      onClick={() => setActiveAsset(layer)}
                    >
                      <img
                        src={layer.url}
                        alt={layer.label}
                        style={{
                          width: "100%",
                          height: 120,
                          objectFit: "cover",
                          borderRadius: "var(--mantine-radius-md)",
                          background: "var(--mantine-color-dark-6)",
                        }}
                      />
                    </Box>
                    <Stack gap={2}>
                      <Text fw={600} size="sm">
                        {layer.label}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {layer.category ? `${layer.category}${layer.optionValue ? `: ${layer.optionValue}` : ""}` : "Base layer"}
                      </Text>
                    </Stack>
                  </Stack>
                </Card>
              ))}
            </Group>
          </Stack>
        </Card>
      </Stack>

      <Modal
        opened={Boolean(activeAsset)}
        onClose={() => setActiveAsset(null)}
        title={activeAsset?.label ?? "Asset"}
        size="lg"
        centered
      >
        {activeAsset ? (
          <Stack gap="sm">
            <img
              src={activeAsset.url}
              alt={activeAsset.label}
              style={{ width: "100%", height: "auto", borderRadius: "var(--mantine-radius-md)" }}
            />
            <Text size="sm" c="dimmed">
              {activeAsset.category
                ? `${activeAsset.category}${activeAsset.optionValue ? ` · ${activeAsset.optionValue}` : ""}`
                : "Base layer"}
            </Text>
          </Stack>
        ) : null}
      </Modal>
    </Container>
  );
}
