/**
 * <EChart /> — theme-aware Apache ECharts wrapper.
 *
 * The option is built by the caller through `buildOption(theme)` so axis/grid
 * colors follow the CSS variables and re-render when light/dark is toggled
 * (a plain `echarts.init` keeps the colors it was created with).
 */
import * as React from "react";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";
import { useUiStore } from "@/store/ui";
import { cn } from "@/lib/cn";

export interface ChartTheme {
  text: string;
  muted: string;
  border: string;
  primary: string;
  positive: string;
  negative: string;
  surface: string;
}

function readTheme(): ChartTheme {
  const styles = getComputedStyle(document.documentElement);
  const hsl = (name: string, fallback: string): string => {
    const value = styles.getPropertyValue(name).trim();
    return value ? `hsl(${value})` : fallback;
  };
  return {
    text: hsl("--foreground", "#111"),
    muted: hsl("--muted-foreground", "#666"),
    border: hsl("--border", "#ccc"),
    primary: hsl("--primary", "#2563eb"),
    positive: hsl("--positive", "#059669"),
    negative: hsl("--negative", "#dc2626"),
    surface: hsl("--card", "#fff"),
  };
}

export interface EChartProps {
  buildOption: (theme: ChartTheme) => EChartsOption;
  height?: number;
  className?: string;
  "data-testid"?: string;
}

export function EChart({
  buildOption,
  height = 280,
  className,
  "data-testid": testId,
}: EChartProps): React.JSX.Element {
  const ref = React.useRef<HTMLDivElement | null>(null);
  const theme = useUiStore((s) => s.theme);

  React.useEffect(() => {
    if (!ref.current) return;
    const colors = readTheme();
    const chart = echarts.init(ref.current);
    chart.setOption({
      textStyle: { fontFamily: "Vazirmatn Variable, Vazirmatn, sans-serif", color: colors.text },
      tooltip: {
        backgroundColor: colors.surface,
        borderColor: colors.border,
        textStyle: { color: colors.text },
      },
      ...buildOption(colors),
    });
    const onResize = (): void => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [buildOption, theme]);

  return (
    <div ref={ref} style={{ height }} className={cn("w-full", className)} data-testid={testId} />
  );
}
