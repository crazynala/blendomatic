import { json } from "@remix-run/node";
import type { ActionFunctionArgs, LoaderFunctionArgs } from "@remix-run/node";
import {
  Link,
  useFetcher,
  useLoaderData,
  useNavigate,
} from "@remix-run/react";
import {
  Accordion,
  Alert,
  Button,
  Card,
  Checkbox,
  Container,
  Divider,
  Group,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Text,
  TextInput,
  Textarea,
  Title,
} from "@mantine/core";
import { IconArrowLeft, IconInfoCircle } from "@tabler/icons-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { WorkspaceNav } from "../components/workspace-nav";
import {
  loadRunFormOptions,
  createRunFromSelection,
  getExpectedRunNumber,
  type RunFormOptions,
  type RunSelection,
} from "../utils/run-planner.server";

export async function loader({}: LoaderFunctionArgs) {
  const runOptions = await loadRunFormOptions();
  const expectedRunNumber = await getExpectedRunNumber();
  return json({ runOptions, expectedRunNumber });
}

export async function action({ request }: ActionFunctionArgs) {
  const formData = await request.formData();
  const intent = formData.get("intent");
  if (intent !== "create-run") {
    return json({ success: false, error: "Unknown intent" }, { status: 400 });
  }
  const payloadRaw = formData.get("payload");
  if (typeof payloadRaw !== "string") {
    return json({ success: false, error: "Missing payload" }, { status: 400 });
  }
  let parsed: RunSelection;
  try {
    parsed = JSON.parse(payloadRaw) as RunSelection;
  } catch (error) {
    return json({ success: false, error: "Invalid payload" }, { status: 400 });
  }
  try {
    const result = await createRunFromSelection(parsed);
    return json({ success: true, ...result });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return json({ success: false, error: message }, { status: 400 });
  }
}

type LoaderData = Awaited<ReturnType<typeof loader>>;
type GarmentSelectionState = {
  enabled: boolean;
  fabrics: string[];
  views: string[];
  assets: string[];
};
type CategoryKey = "fabrics" | "views" | "assets";

const emptySelection: GarmentSelectionState = {
  enabled: false,
  fabrics: [],
  views: [],
  assets: [],
};

function buildInitialState(options: RunFormOptions): Record<string, GarmentSelectionState> {
  const fabricDefaults = options.fabrics.map((fabric) => fabric.id);
  const initial: Record<string, GarmentSelectionState> = {};
  options.garments.forEach((garment) => {
    initial[garment.id] = {
      enabled: false,
      fabrics: [...fabricDefaults],
      views: garment.views.map((view) => view.code),
      assets: garment.assets.map((asset) => asset.name),
    };
  });
  return initial;
}

export default function NewRunRoute() {
  const { runOptions, expectedRunNumber } = useLoaderData<LoaderData>();
  const fetcher = useFetcher<typeof action>();
  const navigate = useNavigate();
  const [mode, setMode] = useState(runOptions.modes[0]?.value ?? "");
  const [note, setNote] = useState("");
  const [saveDebugFiles, setSaveDebugFiles] = useState(false);
  const [runNumber, setRunNumber] = useState(
    () => expectedRunNumber?.padded ?? ""
  );
  const [formError, setFormError] = useState<string | null>(null);
  const [selections, setSelections] = useState<Record<string, GarmentSelectionState>>(() =>
    buildInitialState(runOptions)
  );
  const lastHandledRun = useRef<string | null>(null);

  useEffect(() => {
    setSelections(buildInitialState(runOptions));
    setMode(runOptions.modes[0]?.value ?? "");
    setRunNumber(expectedRunNumber?.padded ?? "");
  }, [runOptions, expectedRunNumber]);

  useEffect(() => {
    if (fetcher.data?.success && fetcher.data.runId) {
      if (lastHandledRun.current === fetcher.data.runId) return;
      lastHandledRun.current = fetcher.data.runId;
      navigate(`/runs/${fetcher.data.runId}`);
    }
  }, [fetcher.data, navigate]);

  const garmentLookup = useMemo(() => {
    return new Map(runOptions.garments.map((garment) => [garment.id, garment]));
  }, [runOptions.garments]);

  const fabricOptions = runOptions.fabrics;
  const modeOptions = runOptions.modes.map((entry) => ({
    value: entry.value,
    label: entry.label,
  }));

  const activeGarments = useMemo(() => {
    return runOptions.garments
      .map((garment) => {
        const selection = selections[garment.id] ?? emptySelection;
        if (!selection.enabled) return null;
        return {
          garmentId: garment.id,
          name: garment.name,
          fabrics: selection.fabrics,
          views: selection.views,
          assets: selection.assets,
        };
      })
      .filter(Boolean) as {
      garmentId: string;
      name: string;
      fabrics: string[];
      views: string[];
      assets: string[];
    }[];
  }, [runOptions.garments, selections]);

  const estimatedJobs = useMemo(() => {
    return activeGarments.reduce((total, entry) => {
      return total + entry.fabrics.length * entry.views.length * entry.assets.length;
    }, 0);
  }, [activeGarments]);

  const isSubmitting = fetcher.state !== "idle";
  const serverError =
    fetcher.data && !fetcher.data.success ? fetcher.data.error ?? null : null;
  const errorMessage = formError || serverError;

  const creationBlocked =
    !runOptions.modes.length || !runOptions.garments.length || !runOptions.fabrics.length;

  const handleGarmentToggle = (garmentId: string, checked: boolean) => {
    const garment = garmentLookup.get(garmentId);
    if (!garment) return;
    const allFabrics = fabricOptions.map((fabric) => fabric.id);
    setSelections((prev) => ({
      ...prev,
      [garmentId]: {
        enabled: checked,
        fabrics: checked ? [...allFabrics] : [],
        views: checked ? garment.views.map((view) => view.code) : [],
        assets: checked ? garment.assets.map((asset) => asset.name) : [],
      },
    }));
  };

  const handleCategoryMasterToggle = (
    garmentId: string,
    key: CategoryKey,
    checked: boolean
  ) => {
    setSelections((prev) => {
      const current = prev[garmentId] ?? emptySelection;
      const garment = garmentLookup.get(garmentId);
      if (!garment) return prev;
      const allValues =
        key === "fabrics"
          ? fabricOptions.map((fabric) => fabric.id)
          : key === "views"
          ? garment.views.map((view) => view.code)
          : garment.assets.map((asset) => asset.name);
      return {
        ...prev,
        [garmentId]: {
          ...current,
          [key]: checked ? [...allValues] : [],
        },
      };
    });
  };

  const handleCategoryItemToggle = (
    garmentId: string,
    key: CategoryKey,
    value: string,
    checked: boolean
  ) => {
    setSelections((prev) => {
      const current = prev[garmentId];
      if (!current) return prev;
      const nextValues = new Set(current[key]);
      if (checked) {
        nextValues.add(value);
      } else {
        nextValues.delete(value);
      }
      return {
        ...prev,
        [garmentId]: {
          ...current,
          [key]: Array.from(nextValues),
        },
      };
    });
  };

  const validationIssues = activeGarments
    .map((entry) => {
      const missing: string[] = [];
      if (!entry.fabrics.length) missing.push("fabrics");
      if (!entry.views.length) missing.push("views");
      if (!entry.assets.length) missing.push("assets");
      return missing.length
        ? `${entry.name} is missing ${missing.join(", ")}`
        : null;
    })
    .filter(Boolean);

  const handleSubmit = () => {
    setFormError(null);
    const trimmedNote = note.trim();
    if (!trimmedNote) {
      setFormError("Operator note is required");
      return;
    }
    if (!mode) {
      setFormError("Select a mode");
      return;
    }
    const trimmedRunNumber = runNumber.trim();
    let numericRunNumber: number | null = null;
    if (trimmedRunNumber) {
      if (!/^[0-9]+$/.test(trimmedRunNumber)) {
        setFormError("Run number must be a positive integer");
        return;
      }
      numericRunNumber = Number(trimmedRunNumber);
      if (!Number.isInteger(numericRunNumber) || numericRunNumber < 1) {
        setFormError("Run number must be a positive integer");
        return;
      }
    }
    if (!activeGarments.length) {
      setFormError("Select at least one garment");
      return;
    }
    if (validationIssues.length) {
      setFormError(validationIssues.join(". "));
      return;
    }
    const payload: RunSelection = {
      note: trimmedNote,
      mode,
      garments: activeGarments.map((entry) => ({
        garmentId: entry.garmentId,
        fabrics: entry.fabrics,
        views: entry.views,
        assets: entry.assets,
      })),
      saveDebugFiles,
      runNumber: numericRunNumber ?? undefined,
    };
    const formData = new FormData();
    formData.append("intent", "create-run");
    formData.append("payload", JSON.stringify(payload));
    fetcher.submit(formData, { method: "post" });
  };

  return (
    <Container size="xl" py="xl">
      <Stack gap="xl">
        <WorkspaceNav />
        <Group justify="space-between" align="flex-start">
          <Stack gap={4}>
            <Group gap="xs">
              <Button
                component={Link}
                to="/runs"
                variant="subtle"
                color="grape"
                leftSection={<IconArrowLeft size={16} />}
              >
                Back to runs
              </Button>
            </Group>
            <Title order={2}>Plan a new run</Title>
            <Text c="dimmed">
              Configure multiple garments, fabrics, views, and assets in a single batch.
            </Text>
          </Stack>
        </Group>
        <Card withBorder padding="xl" radius="lg">
          <Stack gap="xl">
            <Stack gap="md">
              <Textarea
                label="Operator Note"
                description="Required context for everyone reviewing this run"
                placeholder="Document why this run is needed..."
                required
                value={note}
                onChange={(event) => setNote(event.currentTarget.value)}
                minRows={3}
              />
              <Select
                label="Mode"
                placeholder="Select a mode"
                data={modeOptions}
                value={mode || null}
                onChange={(value) => setMode(value ?? "")}
                withinPortal={false}
                disabled={!modeOptions.length}
                required
              />
              <TextInput
                label="Run number (optional)"
                description="Leave blank to auto-increment; setting a number updates the shared counter."
                placeholder="Auto"
                value={runNumber}
                onChange={(event) => setRunNumber(event.currentTarget.value)}
              />
              <Switch
                label="Save debug files"
                checked={saveDebugFiles}
                onChange={(event) => setSaveDebugFiles(event.currentTarget.checked)}
              />
            </Stack>

            <Card withBorder padding="lg" radius="lg" bg="var(--mantine-color-gray-0)">
              <Stack gap={4}>
                <Text fw={600}>Estimated combinations</Text>
                <Text>
                  {estimatedJobs || "—"} potential jobs across {activeGarments.length || "0"} garment
                  {activeGarments.length === 1 ? "" : "s"}.
                </Text>
              </Stack>
            </Card>

            {errorMessage && (
              <Alert
                color="red"
                title="Unable to create run"
                icon={<IconInfoCircle size={16} />}
              >
                {errorMessage}
              </Alert>
            )}

            {creationBlocked ? (
              <Alert color="yellow" title="Run creation unavailable" icon={<IconInfoCircle size={16} />}>
                Add at least one mode, garment, and fabric configuration to continue.
              </Alert>
            ) : (
              <Accordion variant="contained" chevronPosition="left" multiple>
                {runOptions.garments.map((garment) => {
                  const selection = selections[garment.id] ?? emptySelection;
                  const summary = `${selection.fabrics.length} fabrics • ${selection.views.length} views • ${selection.assets.length} assets`;
                  return (
                    <Accordion.Item key={garment.id} value={garment.id}>
                      <Accordion.Control>
                        <Group justify="space-between" align="center">
                          <Stack gap={2}>
                            <Text fw={600}>{garment.name}</Text>
                            <Text size="sm" c="dimmed">
                              {selection.enabled ? summary : "Not included in this run"}
                            </Text>
                          </Stack>
                          <Checkbox
                            checked={selection.enabled}
                            onClick={(event) => event.stopPropagation()}
                            onChange={(event) =>
                              handleGarmentToggle(garment.id, event.currentTarget.checked)
                            }
                            label={selection.enabled ? "Remove" : "Include"}
                          />
                        </Group>
                      </Accordion.Control>
                      <Accordion.Panel>
                        <Stack gap="md">
                          <GarmentCategorySection
                            garmentId={garment.id}
                            label="Fabrics"
                            description="Choose which materials apply to this garment"
                            options={fabricOptions.map((fabric) => ({
                              label: fabric.name,
                              value: fabric.id,
                            }))}
                            selected={selection.fabrics}
                            disabled={!selection.enabled}
                            onMasterToggle={(checked) =>
                              handleCategoryMasterToggle(garment.id, "fabrics", checked)
                            }
                            onItemToggle={(value, checked) =>
                              handleCategoryItemToggle(garment.id, "fabrics", value, checked)
                            }
                          />
                          <GarmentCategorySection
                            garmentId={garment.id}
                            label="Views"
                            description="Pick every camera/viewpoint combination"
                            options={garment.views.map((view) => ({
                              label: view.label,
                              value: view.code,
                            }))}
                            selected={selection.views}
                            disabled={!selection.enabled}
                            onMasterToggle={(checked) =>
                              handleCategoryMasterToggle(garment.id, "views", checked)
                            }
                            onItemToggle={(value, checked) =>
                              handleCategoryItemToggle(garment.id, "views", value, checked)
                            }
                          />
                          <GarmentCategorySection
                            garmentId={garment.id}
                            label="Assets"
                            description="Mesh or prop bundles tied to this garment"
                            options={garment.assets.map((asset) => ({
                              label: asset.name,
                              value: asset.name,
                            }))}
                            selected={selection.assets}
                            disabled={!selection.enabled}
                            onMasterToggle={(checked) =>
                              handleCategoryMasterToggle(garment.id, "assets", checked)
                            }
                            onItemToggle={(value, checked) =>
                              handleCategoryItemToggle(garment.id, "assets", value, checked)
                            }
                          />
                        </Stack>
                      </Accordion.Panel>
                    </Accordion.Item>
                  );
                })}
              </Accordion>
            )}

            <Divider />
            <Group justify="space-between">
              <Button component={Link} to="/runs" variant="default">
                Cancel
              </Button>
              <Button
                color="grape"
                onClick={handleSubmit}
                disabled={creationBlocked || isSubmitting}
                loading={isSubmitting}
              >
                Create run
              </Button>
            </Group>
          </Stack>
        </Card>
      </Stack>
    </Container>
  );
}

type GarmentCategorySectionProps = {
  garmentId: string;
  label: string;
  description: string;
  options: { label: string; value: string }[];
  selected: string[];
  disabled: boolean;
  onMasterToggle: (checked: boolean) => void;
  onItemToggle: (value: string, checked: boolean) => void;
};

function GarmentCategorySection({
  garmentId,
  label,
  description,
  options,
  selected,
  disabled,
  onMasterToggle,
  onItemToggle,
}: GarmentCategorySectionProps) {
  const allSelected = selected.length === options.length && options.length > 0;
  const indeterminate = selected.length > 0 && !allSelected;

  return (
    <Accordion variant="separated" radius="md">
      <Accordion.Item value={`${garmentId}-${label}`}>
        <Accordion.Control>
          <Group justify="space-between" align="center">
            <Stack gap={2}>
              <Text fw={600}>{label}</Text>
              <Text size="sm" c="dimmed">
                {description}
              </Text>
            </Stack>
            <Checkbox
              checked={allSelected}
              indeterminate={indeterminate}
              disabled={disabled || !options.length}
              onClick={(event) => event.stopPropagation()}
              onChange={(event) => onMasterToggle(event.currentTarget.checked)}
              label={options.length ? `${selected.length}/${options.length}` : "—"}
            />
          </Group>
        </Accordion.Control>
        <Accordion.Panel>
          {!options.length ? (
            <Text size="sm" c="dimmed">
              No {label.toLowerCase()} available.
            </Text>
          ) : (
            <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="sm">
              {options.map((option) => (
                <Checkbox
                  key={option.value}
                  label={option.label}
                  value={option.value}
                  checked={selected.includes(option.value)}
                  disabled={disabled}
                  onChange={(event) =>
                    onItemToggle(option.value, event.currentTarget.checked)
                  }
                />
              ))}
            </SimpleGrid>
          )}
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}
