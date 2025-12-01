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

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const mode = url.searchParams.get("mode");
  const date = url.searchParams.get("date");
  const data = await describeRenders(mode, date);
  return json(data);
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

export default function GalleryRoute() {
  const { modes, selectedMode, selectedDate, gallery, configOptions } =
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

  const dateOptions = useMemo(() => {
    return modes.find((mode) => mode.name === selectedMode)?.dates ?? [];
  }, [modes, selectedMode]);

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

  const handleModeChange = (value: string | null) => {
    if (!value) return;
    const params = new URLSearchParams(searchParams);
    params.set("mode", value);
    params.delete("date");
    navigate(`/?${params.toString()}`);
  };

  const handleDateChange = (value: string | null) => {
    if (!value) return;
    const params = new URLSearchParams(searchParams);
    if (selectedMode) {
      params.set("mode", selectedMode);
    }
    params.set("date", value);
    navigate(`/?${params.toString()}`);
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
        <Stack gap="xs">
          <Title order={2}>Render Explorer</Title>
          <Text c="dimmed">
            Browse completed renders, compare fabrics, and adjust the global
            configuration controls to see how each garment responds.
          </Text>
        </Stack>

        <Card withBorder radius="lg" padding="lg">
          <Stack gap="md">
            <Group gap="md" align="flex-end">
              <Select
                label="Mode"
                placeholder="Select mode"
                data={modes.map((mode) => ({
                  label: mode.name,
                  value: mode.name,
                }))}
                value={selectedMode}
                onChange={handleModeChange}
                allowDeselect={false}
              />
              <Select
                label="Date"
                placeholder="Select date"
                data={dateOptions.map((date) => ({
                  label: date,
                  value: date,
                }))}
                value={selectedDate}
                onChange={handleDateChange}
                allowDeselect={false}
                disabled={!dateOptions.length}
              />
            </Group>

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
            We couldn&apos;t find any PNG outputs for this mode/date. Try
            another combination once renders are available.
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
