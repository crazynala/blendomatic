import { json } from "@remix-run/node";
import type { ActionFunctionArgs, LoaderFunctionArgs } from "@remix-run/node";
import {
  Link,
  useLoaderData,
  useRevalidator,
  useSearchParams,
  useFetcher,
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
  Modal,
  Select,
  MultiSelect,
  Textarea,
  Switch,
  Divider,
  Alert,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import {
  IconAlertTriangle,
  IconPlus,
  IconInfoCircle,
} from "@tabler/icons-react";
import { useDisclosure } from "@mantine/hooks";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  loadRunFormOptions,
  createRunFromSelection,
  type RunFormOptions,
  type RunSelection,
} from "../utils/run-planner.server";
import { listRunSummaries } from "../utils/run-store.server";
import { WorkspaceNav } from "../components/workspace-nav";

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const filter = url.searchParams.get("filter") ?? "all";
  const summaries = await listRunSummaries(200);
  const runOptions = await loadRunFormOptions();
  return json({ summaries, filter, runOptions });
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
    return json({
      success: true,
      runId: result.runId,
      totalJobs: result.totalJobs,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return json({ success: false, error: message }, { status: 400 });
  }
}

type LoaderData = {
  summaries: Awaited<ReturnType<typeof listRunSummaries>>;
  filter: string;
  runOptions: RunFormOptions;
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
  const { summaries, filter, runOptions } = useLoaderData<LoaderData>();
  const [searchParams, setSearchParams] = useSearchParams();
  const revalidator = useRevalidator();
  const [newRunOpened, { open: openNewRun, close: closeNewRun }] =
    useDisclosure(false);

  const handleRunCreated = useCallback(() => {
    closeNewRun();
    revalidator.revalidate();
  }, [closeNewRun, revalidator]);

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

  const creationDisabled =
    runOptions.modes.length === 0 ||
    runOptions.garments.length === 0 ||
    runOptions.fabrics.length === 0;

  return (
    <Container size="xl" py="xl">
      <NewRunModal
        opened={newRunOpened}
        onClose={closeNewRun}
        onCreated={handleRunCreated}
        options={runOptions}
      />
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
            variant="filled"
            color="grape"
            leftSection={<IconPlus size={16} />}
            onClick={openNewRun}
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

type NewRunModalProps = {
  opened: boolean;
  onClose: () => void;
  onCreated: () => void;
  options: RunFormOptions;
};

function NewRunModal({
  opened,
  onClose,
  onCreated,
  options,
}: NewRunModalProps) {
  const fetcher = useFetcher<typeof action>();
  const [mode, setMode] = useState(() => options.modes[0]?.value ?? "");
  const [garmentId, setGarmentId] = useState(
    () => options.garments[0]?.id ?? ""
  );
  const [selectedFabrics, setSelectedFabrics] = useState<string[]>(() =>
    options.fabrics.map((fabric) => fabric.id)
  );
  const [selectedAssets, setSelectedAssets] = useState<string[]>(() =>
    (options.garments[0]?.assets ?? []).map((asset) => asset.name)
  );
  const [selectedViews, setSelectedViews] = useState<string[]>(() =>
    (options.garments[0]?.views ?? []).map((view) => view.code)
  );
  const [note, setNote] = useState("");
  const [saveDebugFiles, setSaveDebugFiles] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const lastHandledRun = useRef<string | null>(null);
  const optionsRef = useRef(options);
  const wasOpened = useRef(opened);

  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  const resetForm = useCallback(() => {
    const current = optionsRef.current;
    const defaultMode = current.modes[0]?.value ?? "";
    const defaultGarment = current.garments[0]?.id ?? "";
    const garmentDef =
      current.garments.find((g) => g.id === defaultGarment) ??
      current.garments[0] ??
      null;
    setMode(defaultMode);
    setGarmentId(defaultGarment);
    setSelectedFabrics(current.fabrics.map((fabric) => fabric.id));
    setSelectedAssets(garmentDef?.assets.map((asset) => asset.name) ?? []);
    setSelectedViews(garmentDef?.views.map((view) => view.code) ?? []);
    setNote("");
    setSaveDebugFiles(false);
    setFormError(null);
  }, []);

  useEffect(() => {
    if (opened && !wasOpened.current) {
      resetForm();
    }
    if (!opened) {
      setFormError(null);
    }
    wasOpened.current = opened;
  }, [opened, resetForm]);

  const garment = useMemo(() => {
    return options.garments.find((entry) => entry.id === garmentId) ?? null;
  }, [garmentId, options.garments]);

  useEffect(() => {
    if (!garment) {
      setSelectedAssets([]);
      setSelectedViews([]);
      return;
    }
    setSelectedAssets(garment.assets.map((asset) => asset.name));
    setSelectedViews(garment.views.map((view) => view.code));
  }, [garmentId]);

  const isSubmitting = fetcher.state !== "idle";
  const serverError =
    fetcher.data && !fetcher.data.success ? fetcher.data.error ?? null : null;
  const errorMessage = formError || serverError;

  useEffect(() => {
    if (fetcher.data?.success && fetcher.data.runId) {
      if (lastHandledRun.current === fetcher.data.runId) {
        return;
      }
      lastHandledRun.current = fetcher.data.runId;
      onCreated();
    }
  }, [fetcher.data, onCreated]);

  const garmentOptions = useMemo(
    () =>
      options.garments.map((entry) => ({
        value: entry.id,
        label: entry.name,
      })),
    [options.garments]
  );

  const fabricOptions = useMemo(
    () =>
      options.fabrics.map((fabric) => ({
        value: fabric.id,
        label: fabric.name,
      })),
    [options.fabrics]
  );

  const assetOptions = useMemo(
    () =>
      (garment?.assets ?? []).map((asset) => ({
        value: asset.name,
        label: asset.name,
      })),
    [garment]
  );

  const viewOptions = useMemo(
    () =>
      (garment?.views ?? []).map((view) => ({
        value: view.code,
        label: view.label,
      })),
    [garment]
  );

  const modeOptions = useMemo(
    () =>
      options.modes.map((entry) => ({
        value: entry.value,
        label: entry.label,
      })),
    [options.modes]
  );

  const estimatedJobs =
    selectedFabrics.length * selectedAssets.length * selectedViews.length;

  const handleSubmit = () => {
    setFormError(null);
    if (!mode || !garmentId) {
      setFormError("Select a mode and garment");
      return;
    }
    if (!selectedFabrics.length) {
      setFormError("Select at least one fabric");
      return;
    }
    if (!selectedAssets.length) {
      setFormError("Select at least one asset");
      return;
    }
    if (!selectedViews.length) {
      setFormError("Select at least one view");
      return;
    }
    const payload: RunSelection = {
      note,
      mode,
      garmentId,
      fabrics: selectedFabrics,
      assets: selectedAssets,
      views: selectedViews,
      saveDebugFiles,
    };
    const formData = new FormData();
    formData.append("intent", "create-run");
    formData.append("payload", JSON.stringify(payload));
    fetcher.submit(formData, { method: "post" });
  };

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="New Run"
      size="lg"
      centered
      overflow="inside"
    >
      <Stack gap="md">
        <Select
          label="Mode"
          placeholder="Select a mode"
          data={modeOptions}
          value={mode || null}
          onChange={(value) => setMode(value ?? "")}
          disabled={!modeOptions.length}
          withinPortal={false}
        />
        <Select
          label="Garment"
          placeholder="Select a garment"
          data={garmentOptions}
          value={garmentId || null}
          onChange={(value) => setGarmentId(value ?? "")}
          disabled={!garmentOptions.length}
          withinPortal={false}
        />
        <MultiSelect
          label="Fabrics"
          data={fabricOptions}
          value={selectedFabrics}
          onChange={setSelectedFabrics}
          searchable
          placeholder="Select fabrics"
          disabled={!fabricOptions.length}
          withinPortal={false}
        />
        <MultiSelect
          label="Views"
          data={viewOptions}
          value={selectedViews}
          onChange={setSelectedViews}
          searchable
          placeholder={garment ? "Select views" : "Select a garment first"}
          disabled={!garment || !viewOptions.length}
          withinPortal={false}
        />
        <MultiSelect
          label="Assets"
          data={assetOptions}
          value={selectedAssets}
          onChange={setSelectedAssets}
          searchable
          placeholder={garment ? "Select assets" : "Select a garment first"}
          disabled={!garment || !assetOptions.length}
          withinPortal={false}
        />
        <Textarea
          label="Operator Note"
          placeholder="Optional context for this run"
          minRows={2}
          value={note}
          onChange={(event) => setNote(event.currentTarget.value)}
        />
        <Switch
          label="Save debug files"
          checked={saveDebugFiles}
          onChange={(event) => setSaveDebugFiles(event.currentTarget.checked)}
        />
        <Text size="sm" c="dimmed">
          Estimated combinations: {estimatedJobs || "—"}
        </Text>
        {errorMessage && (
          <Alert
            color="red"
            title="Unable to create run"
            icon={<IconInfoCircle size={16} />}
          >
            {errorMessage}
          </Alert>
        )}
        <Divider />
        <Group justify="space-between">
          <Button variant="default" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            color="grape"
            onClick={handleSubmit}
            loading={isSubmitting}
            disabled={isSubmitting}
          >
            Create Run
          </Button>
        </Group>
      </Stack>
    </Modal>
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
