import { json } from "@remix-run/node";
import type { LoaderFunctionArgs } from "@remix-run/node";
import {
  Link,
  useLoaderData,
  useNavigate,
  useSearchParams,
} from "@remix-run/react";
import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Container,
  Divider,
  Group,
  Popover,
  SegmentedControl,
  Select,
  Stack,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { useLocalStorage } from "@mantine/hooks";
import { describeRenders, type LayerEntry } from "../utils/gallery.server";
import { listRunSummaries, getRunDetail } from "../utils/run-store.server";
import { WorkspaceNav } from "../components/workspace-nav";
import {
  IconAlertTriangle,
  IconAdjustments,
  IconArrowsMaximize,
  IconFilter,
  IconListCheck,
  IconStar,
  IconStarFilled,
} from "@tabler/icons-react";

type ConfigState = Record<string, string>;

type CanvasStyles = Record<"outer" | "inner" | "layer", CSSProperties>;

const buildCanvasStyles = (dimension: number): CanvasStyles => ({
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

const runStatusColor: Record<string, string> = {
  running: "blue",
  pending: "gray",
  completed: "green",
  attention: "red",
};

const imageSizeOptions = [
  { label: "400px", value: "400" },
  { label: "800px", value: "800" },
  { label: "1200px", value: "1200" },
];

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const requestedRun = url.searchParams.get("run");
  const runs = await listRunSummaries(200);
  const selectedRun =
    runs.find((entry) => entry.runId === requestedRun) ?? runs[0] ?? null;
  const renderFolder = selectedRun
    ? deriveRenderFolder(selectedRun.createdAt ?? selectedRun.lastActivity)
    : null;
  const runDetail = selectedRun ? await getRunDetail(selectedRun.runId) : null;
  const galleryData = await describeRenders(
    selectedRun?.mode ?? null,
    renderFolder,
    runDetail?.jobs ?? []
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
  const [imageSize, setImageSize] = useState(imageSizeOptions[0].value);
  const [starFilter, setStarFilter] = useState<"all" | "starred">("all");
  const [starredItems, setStarredItems] = useLocalStorage<string[]>({
    key: "gallery-starred-items",
    defaultValue: [],
  });
  const [toolbarCollapsed, setToolbarCollapsed] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setConfig(createInitialConfig(configOptions));
  }, [configOptions]);

  useEffect(() => {
    const node = scrollContainerRef.current;
    if (!node) return;
    const handleScroll = () => {
      setToolbarCollapsed(node.scrollLeft > 80);
    };
    handleScroll();
    node.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      node.removeEventListener("scroll", handleScroll);
    };
  }, []);

  const imageDimension = Number(imageSize);
  const canvasStyles = useMemo(
    () => buildCanvasStyles(imageDimension),
    [imageDimension]
  );

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

  const fabricOrderByGarment = useMemo(() => {
    const orderMap = new Map<string, string[]>();
    const labelLookup = new Map<string, Map<string, string>>();
    gallery.forEach((entry) => {
      let labels = labelLookup.get(entry.garmentId);
      if (!labels) {
        labels = new Map<string, string>();
        labelLookup.set(entry.garmentId, labels);
      }
      entry.fabrics.forEach((fabric) => {
        if (!labels!.has(fabric.key)) {
          labels!.set(fabric.key, fabric.label);
        }
      });
    });
    labelLookup.forEach((labels, garmentId) => {
      const sortedKeys = [...labels.entries()]
        .sort((a, b) => a[1].localeCompare(b[1]))
        .map(([key]) => key);
      orderMap.set(garmentId, sortedKeys);
    });
    return orderMap;
  }, [gallery]);

  const sortedRows = useMemo(() => {
    const ordered = [...gallery].sort((a, b) => {
      const garmentCompare = a.garmentName.localeCompare(b.garmentName);
      if (garmentCompare !== 0) return garmentCompare;
      return a.viewLabel.localeCompare(b.viewLabel);
    });
    return ordered.map((entry) => {
      const fabricOrder = fabricOrderByGarment.get(entry.garmentId) ?? [];
      const fabricMap = new Map(
        entry.fabrics.map((fabric) => [fabric.key, fabric])
      );
      const orderedFabrics = [
        ...fabricOrder
          .map((key) => fabricMap.get(key))
          .filter((fabric): fabric is NonNullable<typeof fabric> =>
            Boolean(fabric)
          ),
        ...entry.fabrics.filter((fabric) => !fabricOrder.includes(fabric.key)),
      ];
      return { ...entry, fabrics: orderedFabrics };
    });
  }, [gallery, fabricOrderByGarment]);

  const starredSet = useMemo(() => new Set(starredItems), [starredItems]);
  const showStarredOnly = starFilter === "starred";

  const visibleRows = useMemo(() => {
    return sortedRows
      .map((row) => {
        const fabrics = row.fabrics.filter((fabric) => {
          if (!showStarredOnly) return true;
          const cardId = `${row.id}-${fabric.key}`;
          return starredSet.has(cardId);
        });
        return { ...row, fabrics };
      })
      .filter((row) => row.fabrics.length > 0);
  }, [sortedRows, showStarredOnly, starredSet]);

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

  const handleConfigChange = (key: string, value: string) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  };

  const handleToggleStar = (itemId: string) => {
    setStarredItems((prev) =>
      prev.includes(itemId)
        ? prev.filter((id) => id !== itemId)
        : [...prev, itemId]
    );
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

  const hasGalleryContent = sortedRows.length > 0;
  const hasVisibleRows = visibleRows.length > 0;
  const toolbarOffset = toolbarCollapsed ? 120 : 360;

  return (
    <Box ref={scrollContainerRef} style={{ width: "100%", overflowX: "auto" }}>
      <Container
        fluid
        py="xl"
        style={{
          minHeight: "100vh",
          paddingBottom: "var(--mantine-spacing-xl)",
        }}
      >
        <Stack gap="xl" style={{ width: "fit-content" }}>
          <WorkspaceNav />
          <Group justify="space-between" align="flex-start" style={{ minWidth: "calc(100% - 240px)" }}>
            <Stack gap="xs">
              <Title order={2}>Render Explorer</Title>
              {selectedRun ? (
                <Stack gap={2}>
                  <Group gap="xs">
                    <Badge
                      color={
                        runStatusColor[
                          selectedRun.status?.toLowerCase() ?? "pending"
                        ] ?? "gray"
                      }
                    >
                      {selectedRun.status ?? "pending"}
                    </Badge>
                    <Text fw={600}>Run {selectedRun.runId}</Text>
                  </Group>
                  <Text size="sm" c="dimmed">
                    Mode {selectedRun.mode ?? "—"} • Folder {renderFolder ?? "—"}
                  </Text>
                  <Text size="sm" c="dimmed">
                    {selectedRun.note?.trim() || "No operator note"}
                  </Text>
                  <Text size="sm">
                    {selectedRun.completedJobs}/{selectedRun.totalJobs} completed
                  </Text>
                </Stack>
              ) : (
                <Text c="dimmed">Select a run to view gallery items.</Text>
              )}
            </Stack>
            <Select
              placeholder="Select a run"
              data={runOptions}
              value={selectedRunId}
              onChange={handleRunChange}
              searchable
              allowDeselect={false}
              nothingFoundMessage="No runs"
              disabled={!runOptions.length}
              style={{ width: 280 }}
            />
          </Group>

          <Box
            style={{
              display: "flex",
              gap: "var(--mantine-spacing-xl)",
              alignItems: "flex-start",
              width: "fit-content",
              minWidth: "100%",
              paddingLeft: toolbarOffset,
            }}
          >
            <GalleryToolbar
              runOptions={[]}
              selectedRunId={selectedRunId}
              onRunChange={() => {}}
              configOptions={configOptions}
              config={config}
              onConfigChange={handleConfigChange}
              imageSize={imageSize}
              onImageSizeChange={setImageSize}
              starFilter={starFilter}
              onStarFilterChange={setStarFilter}
              starredCount={starredItems.length}
              collapsed={toolbarCollapsed}
            />
            <Stack gap="xl" style={{ flex: 1, width: "fit-content" }}>
              {!selectedRun ? (
                <Alert title="No runs found" color="yellow" variant="filled">
                  There are no completed runs yet. Start a run to populate the
                  gallery.
                </Alert>
              ) : null}
              {!hasGalleryContent ? (
                <Alert title="No renders found" color="yellow" variant="filled">
                  We couldn&apos;t find any PNG outputs for this run. Try a
                  different run once additional renders are available.
                </Alert>
              ) : !hasVisibleRows ? (
                <Alert
                  title="No garments match"
                  color="blue"
                  variant="light"
                  icon={<IconAlertTriangle size={18} />}
                >
                  No garments match the current star filter. Toggle back to
                  "All" or star more garments.
                </Alert>
              ) : (
                visibleRows.map((row) => (
                  <Stack
                    key={`${row.id}-${row.viewCode}`}
                    gap="md"
                    style={{ width: "fit-content" }}
                  >
                    <Group justify="space-between" align="flex-start">
                      <Stack gap={0}>
                        <Text fw={700}>{row.garmentName}</Text>
                        <Text size="sm" c="dimmed">
                          View {row.viewLabel}
                        </Text>
                      </Stack>
                      <Badge variant="light">{row.viewLabel}</Badge>
                    </Group>

                    <Box
                      style={{
                        display: "flex",
                        gap: "var(--mantine-spacing-md)",
                        paddingBottom: "var(--mantine-spacing-sm)",
                        minHeight: imageDimension + 120,
                        width: "fit-content",
                      }}
                    >
                      {row.fabrics.map((fabric) => {
                        const layers = computeVisibleLayers(fabric.layers);
                        const cardId = `${row.id}-${fabric.key}`;
                        const cardStarred = starredSet.has(cardId);
                        const detailHref = `/gallery/${encodeURIComponent(
                          cardId
                        )}${selectedRunId ? `?run=${selectedRunId}` : ""}`;
                        return (
                          <Stack
                            key={cardId}
                            gap={6}
                            align="flex-start"
                            style={{ minWidth: imageDimension }}
                          >
                            <Text size="sm" c="dimmed" fw={600}>
                              {fabric.label}
                            </Text>
                            <Card
                              component={Link}
                              to={detailHref}
                              withBorder={false}
                              padding={0}
                              radius="md"
                              style={{
                                position: "relative",
                                background: "transparent",
                                border: "none",
                                boxShadow: "none",
                                cursor: "pointer",
                                width: "100%",
                              }}
                            >
                              <Tooltip
                                label={
                                  cardStarred ? "Unstar item" : "Star item"
                                }
                                withArrow
                              >
                                <ActionIcon
                                  size="sm"
                                  variant="subtle"
                                  color={cardStarred ? "yellow" : "gray"}
                                  aria-label={
                                    cardStarred ? "Unstar item" : "Star item"
                                  }
                                  style={{
                                    position: "absolute",
                                    top: 6,
                                    right: 6,
                                    opacity: cardStarred ? 0.9 : 0.4,
                                    background: "transparent",
                                    boxShadow: "none",
                                  }}
                                  onClick={(event) => {
                                    event.preventDefault();
                                    event.stopPropagation();
                                    handleToggleStar(cardId);
                                  }}
                                >
                                  {cardStarred ? (
                                    <IconStarFilled size={14} />
                                  ) : (
                                    <IconStar size={14} />
                                  )}
                                </ActionIcon>
                              </Tooltip>
                              <Box style={canvasStyles.outer}>
                                <Box style={canvasStyles.inner}>
                                  {layers.length ? (
                                    layers.map((layer) => (
                                      <img
                                        key={`${cardId}-${layer.suffix}`}
                                        src={layer.url}
                                        alt={`${fabric.label} ${layer.label}`}
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
                            </Card>
                          </Stack>
                        );
                      })}
                    </Box>
                  </Stack>
                ))
              )}
            </Stack>
          </Box>
        </Stack>
      </Container>
    </Box>
  );
}

type GalleryToolbarProps = {
  runOptions: { value: string; label: string }[];
  selectedRunId: string | null;
  onRunChange: (value: string | null) => void;
  configOptions: LoaderData["configOptions"];
  config: ConfigState;
  onConfigChange: (key: string, value: string) => void;
  imageSize: string;
  onImageSizeChange: (value: string) => void;
  starFilter: "all" | "starred";
  onStarFilterChange: (value: "all" | "starred") => void;
  starredCount: number;
  collapsed: boolean;
};

function GalleryToolbar({
  runOptions,
  selectedRunId,
  onRunChange,
  configOptions,
  config,
  onConfigChange,
  imageSize,
  onImageSizeChange,
  starFilter,
  onStarFilterChange,
  starredCount,
  collapsed,
}: GalleryToolbarProps) {
  if (collapsed) {
    return (
      <Card
        withBorder
        radius="md"
        padding="xs"
        style={{
          width: 50,
          position: "fixed",
          top: "50vh",
          left: "12px",
          transform: "translateY(-50%)",
          zIndex: 5,
          background: "rgba(0, 0, 0, 0.45)",
          backdropFilter: "blur(6px)",
          borderTopLeftRadius: 0,
          borderBottomLeftRadius: 0,
        }}
      >
        <Stack gap="sm" align="center">
          <ToolbarIconControl
            label="Select run"
            icon={<IconListCheck size={16} />}
          >
            <Select
              placeholder="Select a run"
              data={runOptions}
              value={selectedRunId}
              onChange={onRunChange}
              searchable
              allowDeselect={false}
              nothingFoundMessage="No runs"
              disabled={!runOptions.length}
              style={{ width: 240 }}
            />
          </ToolbarIconControl>

          <ToolbarIconControl
            label="Image size"
            icon={<IconArrowsMaximize size={16} />}
          >
            <SegmentedControl
              value={imageSize}
              onChange={(value) => onImageSizeChange(value)}
              data={imageSizeOptions}
              fullWidth
            />
          </ToolbarIconControl>

          <ToolbarIconControl
            label="Star filter"
            icon={<IconFilter size={16} />}
          >
            <Stack gap="xs" style={{ width: 220 }}>
              <SegmentedControl
                value={starFilter}
                onChange={(value) =>
                  onStarFilterChange(value as "all" | "starred")
                }
                data={[
                  { label: "All", value: "all" },
                  { label: "Starred", value: "starred" },
                ]}
                fullWidth
              />
              <Text size="xs" c="dimmed">
                Starred items: {starredCount}
              </Text>
            </Stack>
          </ToolbarIconControl>

          {Object.entries(configOptions).map(([key, option]) => (
            <ToolbarIconControl
              key={key}
              label={option.label}
              icon={<ConfigIconLabel label={option.label} />}
            >
              <SegmentedControl
                value={config[key]}
                onChange={(value) => onConfigChange(key, value)}
                data={option.values.map((value) => ({
                  label: value.label,
                  value: value.value,
                }))}
                fullWidth
              />
            </ToolbarIconControl>
          ))}
        </Stack>
      </Card>
    );
  }

  return (
    <Card
      withBorder
      radius="lg"
      padding="lg"
      style={{
        width: 320,
        position: "fixed",
        top: "50vh",
        left: "12px",
        transform: "translateY(-50%)",
        zIndex: 5,
        borderTopLeftRadius: 0,
        borderBottomLeftRadius: 0,
      }}
    >
      <Stack gap="md">
        <Stack gap={4}>
          <Text fw={600}>Run</Text>
          <Select
            placeholder="Select a run"
            data={runOptions}
            value={selectedRunId}
            onChange={onRunChange}
            searchable
            allowDeselect={false}
            nothingFoundMessage="No runs"
            disabled={!runOptions.length}
          />
        </Stack>

        <Stack gap={4}>
          <Text fw={600}>Image Size</Text>
          <SegmentedControl
            value={imageSize}
            onChange={(value) => onImageSizeChange(value)}
            data={imageSizeOptions}
            fullWidth
          />
        </Stack>

        <Stack gap={4}>
          <Text fw={600}>Items</Text>
          <SegmentedControl
            value={starFilter}
            onChange={(value) => onStarFilterChange(value as "all" | "starred")}
            data={[
              { label: "All", value: "all" },
              { label: "Starred", value: "starred" },
            ]}
            fullWidth
          />
          <Text size="xs" c="dimmed">
            Starred items: {starredCount}
          </Text>
        </Stack>

        <Divider label="Configuration" labelPosition="center" />

        <Stack gap="md">
          {Object.entries(configOptions).map(([key, option]) => (
            <Stack gap={4} key={key}>
              <Text fw={600}>{option.label}</Text>
              <SegmentedControl
                value={config[key]}
                onChange={(value) => onConfigChange(key, value)}
                fullWidth
                data={option.values.map((value) => ({
                  label: value.label,
                  value: value.value,
                }))}
              />
            </Stack>
          ))}
        </Stack>
      </Stack>
    </Card>
  );
}

function ToolbarIconControl({
  label,
  icon,
  children,
}: {
  label: string;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <Popover position="right" withArrow shadow="md">
      <Popover.Target>
        <Tooltip label={label} withinPortal>
          <ActionIcon size="lg" variant="light" aria-label={label}>
            {icon}
          </ActionIcon>
        </Tooltip>
      </Popover.Target>
      <Popover.Dropdown maw={280} miw={220}>
        <Stack gap="xs">
          <Text fw={600} size="sm">
            {label}
          </Text>
          {children}
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}

function ConfigIconLabel({ label }: { label: string }) {
  const initials = label
    .split(" ")
    .map((word) => word[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <Box component="span" style={{ fontSize: "0.75rem", fontWeight: 700 }}>
      {initials}
    </Box>
  );
}
