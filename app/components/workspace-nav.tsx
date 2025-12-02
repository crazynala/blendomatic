import { SegmentedControl } from "@mantine/core";
import { useLocation, useNavigate } from "@remix-run/react";
import type { ComponentPropsWithoutRef } from "react";

const NAV_SEGMENTS = [
  { label: "Gallery", value: "/" },
  { label: "Mesh", value: "/mesh" },
  { label: "Runs", value: "/runs" },
] as const;

type WorkspaceNavProps = ComponentPropsWithoutRef<typeof SegmentedControl> & {
  valueOverride?: string | null;
};

function resolvePathname(pathname: string): string {
  if (pathname.startsWith("/mesh")) {
    return "/mesh";
  }
  if (pathname.startsWith("/runs")) {
    return "/runs";
  }
  return "/";
}

export function WorkspaceNav({ valueOverride, ...rest }: WorkspaceNavProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const currentValue = valueOverride ?? resolvePathname(location.pathname);

  return (
    <SegmentedControl
      value={currentValue}
      onChange={(value) => {
        navigate(value);
      }}
      radius="xl"
      size="md"
      data={NAV_SEGMENTS}
      {...rest}
    />
  );
}
