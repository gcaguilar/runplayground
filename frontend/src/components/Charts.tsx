import { useEffect, useMemo, useState } from "react";
import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import {
  AxisPointerComponent,
  AriaComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import type { EChartsOption } from "echarts";
import { LegacyGridContainLabel } from "echarts/features";
import { CanvasRenderer } from "echarts/renderers";
import ReactECharts from "echarts-for-react/esm/core";
import { BarChart3, HeartPulse, TrendingUp } from "lucide-react";

import type {
  AnalysisLoad,
  ComparisonSplit,
  FitnessPoint,
  GarminMetricPoint,
  GoalHistoryPoint,
  GoalResult,
  RecoveryMetric,
  PaceHrGroup,
  PerformanceSnapshot,
  ProgressWeek,
  StreamPoint,
  WeeklyDay,
} from "@/api/client";
import { useI18n, type MessageKey } from "@/i18n";
import { useTheme } from "@/theme";
import { EmptyState } from "@/components/ui";
import {
  formatClock,
  formatDate,
  formatDistance,
  formatNumber,
  formatPace,
  formatRecoveryValue,
  parseUtc,
  weekdayKeys,
} from "@/lib/format";

type ChartPalette = {
  text: string;
  textStrong: string;
  textMuted: string;
  grid: string;
  axisPointer: string;
  border: string;
  panel: string;
  accent: string;
  accentStrong: string;
  accentDeep: string;
  accentMuted: string;
  accentSoft: string;
  accentFillStart: string;
  accentZero: string;
  orange: string;
  orangeFade: string;
  orangeZero: string;
  blue: string;
  blueFade: string;
  blueFillStart: string;
  blueZero: string;
  red: string;
  violet: string;
  animation: boolean;
  distance: Record<"5k" | "10k" | "half_marathon" | "marathon", string>;
};

const DARK_PALETTE: ChartPalette = {
  text: "#8d9b94",
  textStrong: "#eef5f0",
  textMuted: "#a9b5ae",
  grid: "rgba(255,255,255,0.07)",
  axisPointer: "rgba(255,255,255,0.025)",
  border: "rgba(255,255,255,0.09)",
  panel: "rgba(15, 21, 18, 0.94)",
  accent: "#c9f56a",
  accentStrong: "#dcff94",
  accentDeep: "#769e38",
  accentMuted: "rgba(201, 245, 106, 0.42)",
  accentSoft: "rgba(201, 245, 106, 0.52)",
  accentFillStart: "rgba(201, 245, 106, 0.20)",
  accentZero: "rgba(201, 245, 106, 0)",
  orange: "#ffab6b",
  orangeFade: "rgba(255,171,107,0.16)",
  orangeZero: "rgba(255,171,107,0)",
  blue: "#7bc8ff",
  blueFade: "rgba(123, 200, 255, 0.35)",
  blueFillStart: "rgba(123, 200, 255, 0.20)",
  blueZero: "rgba(123, 200, 255, 0)",
  red: "#ff7b7b",
  violet: "#b79bff",
  animation: true,
  distance: {
    "5k": "#c9f56a",
    "10k": "#7bc8ff",
    half_marathon: "#ffab6b",
    marathon: "#b79bff",
  },
};

const LIGHT_PALETTE: ChartPalette = {
  text: "#4f5f56",
  textStrong: "#16231b",
  textMuted: "#5f7166",
  grid: "rgba(16, 36, 24, 0.14)",
  axisPointer: "rgba(16, 36, 24, 0.05)",
  border: "rgba(16, 36, 24, 0.18)",
  panel: "#ffffff",
  accent: "#3f6b12",
  accentStrong: "#2c5108",
  accentDeep: "#7ea53a",
  accentMuted: "rgba(63, 107, 18, 0.45)",
  accentSoft: "rgba(63, 107, 18, 0.55)",
  accentFillStart: "rgba(63, 107, 18, 0.18)",
  accentZero: "rgba(63, 107, 18, 0)",
  orange: "#a34d00",
  orangeFade: "rgba(163, 77, 0, 0.14)",
  orangeZero: "rgba(163, 77, 0, 0)",
  blue: "#0b6ba8",
  blueFade: "rgba(11, 107, 168, 0.35)",
  blueFillStart: "rgba(11, 107, 168, 0.18)",
  blueZero: "rgba(11, 107, 168, 0)",
  red: "#b42318",
  violet: "#6a45c2",
  animation: true,
  distance: {
    "5k": "#3f6b12",
    "10k": "#0b6ba8",
    half_marathon: "#a34d00",
    marathon: "#6a45c2",
  },
};

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return reduced;
}

function useChartPalette(): ChartPalette {
  const { resolved, printing } = useTheme();
  const reduced = usePrefersReducedMotion();
  return useMemo(() => {
    const base = resolved === "light" || printing ? LIGHT_PALETTE : DARK_PALETTE;
    return printing || reduced ? { ...base, animation: false } : base;
  }, [printing, reduced, resolved]);
}

const chartOpts = { renderer: "canvas" as const };

function ariaOption() {
  return { enabled: true, decal: { show: false } };
}

echarts.use([
  BarChart,
  LineChart,
  ScatterChart,
  AxisPointerComponent,
  AriaComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  LegacyGridContainLabel,
  CanvasRenderer,
]);

type TooltipItem = {
  axisValueLabel?: string;
  dataIndex?: number;
  marker?: string;
  seriesName?: string;
  value?: unknown;
  data?: unknown;
};

export function WeeklyVolumeChart({ days }: { days: WeeklyDay[] }) {
  const { locale, units, t } = useI18n();
  const palette = useChartPalette();
  const volumeUnit = units === "imperial" ? "mi" : "km";
  const values = days.map((day) =>
    Number(
      units === "imperial"
        ? day.distance_m / 1000 / 1.609344
        : day.distance_m / 1000,
    ),
  );
  const total = values.reduce((sum, value) => sum + value, 0);

  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 500,
      animation: palette.animation,
      aria: ariaOption(),
      grid: { left: 6, right: 10, top: 24, bottom: 6, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow", shadowStyle: { color: palette.axisPointer } },
        backgroundColor: palette.panel,
        borderColor: palette.border,
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: palette.textStrong, fontFamily: "Manrope Variable", fontSize: 12 },
        formatter: (params: unknown) => {
          const list = Array.isArray(params) ? params : [params];
          const item = list[0] as TooltipItem | undefined;
          if (!item) return "";
          const index = item.dataIndex ?? 0;
          const day = days[index];
          if (!day) return "";
          const value = values[index] ?? 0;
          return `<div style="font-weight:700;margin-bottom:4px">${item.axisValueLabel ?? ""}</div>
            <div style="display:flex;align-items:center;gap:6px">
              <span style="width:7px;height:7px;border-radius:2px;background:${palette.accent};display:inline-block"></span>
              <span style="color:${palette.textMuted}">${t("chart.distance")}</span>
              <strong style="margin-left:auto">${formatNumber(value, locale, value > 0 && value < 100 ? 2 : 1)} ${volumeUnit}</strong>
            </div>`;
        },
      },
      xAxis: {
        type: "category",
        data: weekdayKeys().map((key) => t(key)),
        axisLine: { lineStyle: { color: palette.grid } },
        axisTick: { show: false },
        axisLabel: { color: palette.text, fontSize: 11, margin: 12, fontFamily: "Manrope Variable" },
      },
      yAxis: {
        type: "value",
        splitNumber: 4,
        axisLabel: {
          color: palette.text,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => formatNumber(value, locale, 0),
        },
        splitLine: { lineStyle: { color: palette.grid, type: "dashed" } },
      },
      series: [
        {
          type: "bar",
          data: values.map((value) => (value > 0 ? value : 0)),
          barWidth: 22,
          itemStyle: {
            borderRadius: [5, 5, 2, 2],
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: palette.accent },
                { offset: 1, color: palette.accentDeep },
              ],
            },
          },
          emphasis: { itemStyle: { color: palette.accentStrong } },
        },
      ],
    }),
    [days, locale, t, units, values, volumeUnit, palette],
  );

  if (total <= 0) {
    return (
      <EmptyState
        compact
        icon={BarChart3}
        title={t("dashboard.volume.empty")}
        description={t("dashboard.volume.subtitle")}
      />
    );
  }

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      opts={chartOpts}
      style={{ height: 258, width: "100%" }}
      notMerge
      lazyUpdate={false}
    />
  );
}

export function ActivityStreamChart({ points }: { points: StreamPoint[] }) {
  const { locale, t, units } = useI18n();
  const palette = useChartPalette();
  const paceUnit = units === "imperial" ? "mi" : "km";

  const series = useMemo(() => {
    const paceData: Array<[number, number]> = [];
    const hrData: Array<[number, number]> = [];
    let previous: StreamPoint | null = null;

    for (const point of points) {
      if (point.t === null || point.t === undefined) {
        previous = point;
        continue;
      }
      if (point.heart_rate && point.heart_rate > 0) {
        hrData.push([point.t, point.heart_rate]);
      }

      let secondsPerKm: number | null = null;
      if (point.speed_mps && point.speed_mps > 0.5) {
        secondsPerKm = 1000 / point.speed_mps;
      } else if (
        previous?.distance_m !== null &&
        previous?.distance_m !== undefined &&
        point.distance_m !== null &&
        point.distance_m !== undefined &&
        previous.t !== null &&
        previous.t !== undefined
      ) {
        const distanceDelta = point.distance_m - previous.distance_m;
        const timeDelta = point.t - previous.t;
        if (distanceDelta > 0 && timeDelta > 0) {
          secondsPerKm = (timeDelta / distanceDelta) * 1000;
        }
      }
      if (secondsPerKm !== null && secondsPerKm > 120 && secondsPerKm < 1500) {
        const raw = units === "imperial" ? secondsPerKm * 1.609344 : secondsPerKm;
        paceData.push([point.t, Math.round(raw)]);
      }
      previous = point;
    }

    return { paceData, hrData };
  }, [points, units]);

  const option = useMemo<EChartsOption>(
    () => ({
      animation: false,
      aria: ariaOption(),
      grid: { left: 10, right: 12, top: 28, bottom: 10, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: palette.panel,
        borderColor: palette.border,
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: palette.textStrong, fontFamily: "Manrope Variable", fontSize: 12 },
        formatter: (params: unknown) => {
          const list = (Array.isArray(params) ? params : [params]) as TooltipItem[];
          if (!list.length) return "";
          const time = Number((list[0].value as [number, number] | undefined)?.[0] ?? 0);
          const rows = list.map((item) => {
            const value = (item.value as [number, number] | undefined)?.[1];
            if (value === undefined) return "";
            const formatted =
              item.seriesName === "pace"
                ? formatPace(Number(value), "metric", { suffix: true }).replace("/km", `/${paceUnit}`)
                : `${formatNumber(value, locale)} bpm`;
            return `<div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              ${item.marker ?? ""}
              <span style="color:${palette.textMuted}">${item.seriesName === "pace" ? t("detail.chart.pace") : t("detail.chart.hr")}</span>
              <strong style="margin-left:auto">${formatted}</strong>
            </div>`;
          });
          return `<div style="font-family:JetBrains Mono Variable;font-size:11px;color:${palette.textMuted}">${formatClock(time)}</div>${rows.join("")}`;
        },
      },
      xAxis: {
        type: "value",
        min: 0,
        axisLine: { lineStyle: { color: palette.grid } },
        axisTick: { show: false },
        axisLabel: {
          color: palette.text,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => {
            if (value >= 3600) {
              const hours = Math.floor(value / 3600);
              const minutes = Math.round((value % 3600) / 60);
              return `${hours}h${minutes ? String(minutes).padStart(2, "0") : ""}`;
            }
            return `${Math.round(value / 60)}m`;
          },
        },
        splitLine: { show: false },
      },
      yAxis: [
        {
          type: "value",
          inverse: true,
          scale: true,
          axisLabel: {
            color: palette.accent,
            fontSize: 10,
            fontFamily: "JetBrains Mono Variable",
            formatter: (value: number) => formatPace(value, units, { suffix: false }),
          },
          splitLine: { lineStyle: { color: palette.grid, type: "dashed" } },
        },
        {
          type: "value",
          scale: true,
          axisLabel: {
            color: palette.orange,
            fontSize: 10,
            fontFamily: "JetBrains Mono Variable",
            formatter: (value: number) => formatNumber(value, locale),
          },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: "pace",
          type: "line",
          data: series.paceData,
          showSymbol: false,
          smooth: 0.18,
          connectNulls: true,
          lineStyle: { color: palette.accent, width: 2 },
          itemStyle: { color: palette.accent },
          sampling: "lttb",
          yAxisIndex: 0,
          z: 3,
        },
        {
          name: "hr",
          type: "line",
          data: series.hrData,
          showSymbol: false,
          smooth: 0.25,
          lineStyle: { color: palette.orange, width: 1.6, opacity: 0.9 },
          itemStyle: { color: palette.orange },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: palette.orangeFade },
                { offset: 1, color: palette.orangeZero },
              ],
            },
          },
          sampling: "lttb",
          yAxisIndex: 1,
          z: 2,
        },
      ],
      dataZoom: [{ type: "inside", filterMode: "none" }],
    }),
    [locale, paceUnit, series.hrData, series.paceData, t, units, palette],
  );

  if (!series.hrData.length && !series.paceData.length) {
    return (
      <EmptyState compact icon={HeartPulse} title={`${formatNumber(points.length, locale)} streams`} />
    );
  }

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      opts={chartOpts}
      style={{ height: 318, width: "100%" }}
      notMerge
      lazyUpdate={false}
    />
  );
}

const DISTANCE_META = [
  { key: "5k", label: "distance.5k" as const, color: "5k" as const },
  { key: "10k", label: "distance.10k" as const, color: "10k" as const },
  { key: "half_marathon", label: "distance.half_marathon" as const, color: "half_marathon" as const },
  { key: "marathon", label: "distance.marathon" as const, color: "marathon" as const },
];

export function PerformanceHistoryChart({ items }: { items: PerformanceSnapshot[] }) {
  const { locale, t } = useI18n();
  const palette = useChartPalette();

  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 450,
      animation: palette.animation,
      aria: ariaOption(),
      grid: { left: 8, right: 16, top: 28, bottom: 8, containLabel: true },
      legend: {
        top: 0,
        right: 0,
        icon: "roundRect",
        itemWidth: 9,
        itemHeight: 9,
        textStyle: { color: palette.text, fontSize: 11, fontFamily: "Manrope Variable" },
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: palette.panel,
        borderColor: palette.border,
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: palette.textStrong, fontFamily: "Manrope Variable", fontSize: 12 },
        formatter: (params: unknown) => {
          const list = (Array.isArray(params) ? params : [params]) as TooltipItem[];
          if (!list.length) return "";
          const header = `<div style="font-weight:700;margin-bottom:4px">${list[0].axisValueLabel ?? ""}</div>`;
          return (
            header +
            list
              .map((item) => {
                const value = Number((item.value as [number, number] | undefined)?.[1]);
                if (!Number.isFinite(value)) return "";
                return `<div style="display:flex;align-items:center;gap:6px;margin-top:4px">
                  ${item.marker ?? ""}
                  <span style="color:${palette.textMuted}">${item.seriesName ?? ""}</span>
                  <strong style="margin-left:auto">${formatClock(value)}</strong>
                </div>`;
              })
              .join("")
          );
        },
      },
      xAxis: {
        type: "category",
        data: items.map((item) => formatDate(item.date, locale, { day: "numeric", month: "short" })),
        axisLine: { lineStyle: { color: palette.grid } },
        axisTick: { show: false },
        axisLabel: {
          color: palette.text,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
          hideOverlap: true,
        },
      },
      yAxis: {
        type: "value",
        inverse: true,
        scale: true,
        axisLabel: {
          color: palette.text,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => formatClock(value),
        },
        splitLine: { lineStyle: { color: palette.grid, type: "dashed" } },
      },
      series: DISTANCE_META.map((distance) => ({
        name: t(distance.label),
        type: "line" as const,
        data: items.map((item) => {
          const prediction = (item.predictions ?? []).find(
            (entry) => entry.distance_key === distance.key,
          );
          return prediction?.planning_s ?? null;
        }),
        connectNulls: true,
        showSymbol: true,
        symbolSize: 5,
        lineStyle: { color: palette.distance[distance.color], width: 2 },
        itemStyle: { color: palette.distance[distance.color] },
        emphasis: { focus: "series" as const },
      })),
    }),
    [items, locale, t, palette],
  );

  if (!items.length) {
    return (
      <EmptyState
        compact
        icon={BarChart3}
        title={t("performance.history.empty")}
        description={t("performance.history.note")}
      />
    );
  }

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      opts={chartOpts}
      style={{ height: 264, width: "100%" }}
      notMerge
      lazyUpdate={false}
    />
  );
}

export function Vo2MaxChart({ points }: { points: GarminMetricPoint[] }) {
  const { locale, t } = useI18n();
  const palette = useChartPalette();
  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 450,
      animation: palette.animation,
      aria: ariaOption(),
      grid: { left: 6, right: 10, top: 18, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: palette.panel,
        borderColor: palette.border,
        borderWidth: 1,
        padding: [9, 11],
        textStyle: { color: palette.textStrong, fontFamily: "Manrope Variable", fontSize: 12 },
        formatter: (params: unknown) => {
          const list = (Array.isArray(params) ? params : [params]) as TooltipItem[];
          const item = list[0];
          if (!item) return "";
          const value = Number((item.value as [number, number] | undefined)?.[1]);
          return `<div style="font-weight:700;margin-bottom:2px">${item.axisValueLabel ?? ""}</div>
            <span style="color:${palette.textMuted}">${t("performance.garmin.vo2max")}</span>
            <strong style="margin-left:8px">${formatNumber(value, locale, 1)}</strong>`;
        },
      },
      xAxis: {
        type: "category",
        data: points.map((point) => formatDate(point.date, locale, { day: "numeric", month: "short" })),
        axisLine: { lineStyle: { color: palette.grid } },
        axisTick: { show: false },
        axisLabel: {
          color: palette.text,
          fontSize: 9,
          fontFamily: "JetBrains Mono Variable",
          hideOverlap: true,
        },
      },
      yAxis: {
        type: "value",
        scale: true,
        splitNumber: 3,
        axisLabel: {
          color: palette.text,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
        },
        splitLine: { lineStyle: { color: palette.grid, type: "dashed" } },
      },
      series: [
        {
          type: "line",
          data: points.map((point) => point.value),
          showSymbol: false,
          smooth: 0.25,
          lineStyle: { color: palette.accent, width: 2 },
          itemStyle: { color: palette.accent },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: palette.accentFillStart },
                { offset: 1, color: palette.accentZero },
              ],
            },
          },
        },
      ],
    }),
    [locale, points, t, palette],
  );

  if (points.length < 2) return null;

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      opts={chartOpts}
      style={{ height: 150, width: "100%" }}
      notMerge
      lazyUpdate={false}
    />
  );
}

export function WeeklyLoadChart({ load }: { load: AnalysisLoad }) {
  const { locale, t, units } = useI18n();
  const palette = useChartPalette();
  const labels = load.weekly.map((point) =>
    formatDate(point.week_start, locale, { day: "numeric", month: "short" }),
  );
  const values = load.weekly.map((point) => point.load);

  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 450,
      animation: palette.animation,
      aria: ariaOption(),
      grid: { left: 8, right: 14, top: 20, bottom: 6, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow", shadowStyle: { color: palette.axisPointer } },
        backgroundColor: palette.panel,
        borderColor: palette.border,
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: palette.textStrong, fontFamily: "Manrope Variable", fontSize: 12 },
        formatter: (params: unknown) => {
          const list = (Array.isArray(params) ? params : [params]) as TooltipItem[];
          const index = list[0]?.dataIndex ?? 0;
          const point = load.weekly[index];
          if (!point) return "";
          return `<div style="font-weight:700;margin-bottom:4px">${formatDate(
            point.week_start,
            locale,
            { day: "numeric", month: "short", year: "numeric" },
          )}</div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="width:7px;height:7px;border-radius:2px;background:${palette.accent};display:inline-block"></span>
              <span style="color:${palette.textMuted}">${t("analysis.load.chartLoad")}</span>
              <strong style="margin-left:auto">${formatNumber(point.load, locale)}</strong>
            </div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="width:7px;height:7px;border-radius:50%;background:${palette.orange};display:inline-block"></span>
              <span style="color:${palette.textMuted}">${t("analysis.load.chartChronic")}</span>
              <strong style="margin-left:auto">${formatNumber(load.chronic_weekly, locale)}</strong>
            </div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="color:${palette.textMuted}">${t("analysis.load.chartDistance")}</span>
              <strong style="margin-left:auto">${formatDistance(
                point.distance_m,
                units,
                locale,
                { digits: 1 },
              )}</strong>
            </div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="color:${palette.textMuted}">${t("analysis.load.chartSessions")}</span>
              <strong style="margin-left:auto">${formatNumber(point.sessions, locale)}</strong>
            </div>`;
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { lineStyle: { color: palette.grid } },
        axisTick: { show: false },
        axisLabel: {
          color: palette.text,
          fontSize: 9.5,
          fontFamily: "JetBrains Mono Variable",
          hideOverlap: true,
        },
      },
      yAxis: {
        type: "value",
        splitNumber: 4,
        axisLabel: {
          color: palette.text,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => formatNumber(value, locale),
        },
        splitLine: { lineStyle: { color: palette.grid, type: "dashed" } },
      },
      series: [
        {
          type: "bar",
          data: values.map((value, index) => ({
            value,
            itemStyle: {
              borderRadius: [4, 4, 2, 2],
              color:
                index === values.length - 1 ? palette.accent : palette.accentMuted,
            },
          })),
          barWidth: "52%",
          emphasis: { itemStyle: { color: palette.accentStrong } },
        },
        {
          type: "line",
          data: values.map(() => load.chronic_weekly),
          showSymbol: false,
          silent: true,
          lineStyle: { color: palette.orange, width: 1.4, type: "dashed", opacity: 0.8 },
          itemStyle: { color: palette.orange },
          z: 3,
        },
      ],
    }),
    [labels, load.chronic_weekly, load.weekly, locale, t, units, values, palette],
  );

  if (!values.some((value) => value > 0)) {
    return (
      <EmptyState
        compact
        icon={BarChart3}
        title={t("analysis.load.empty")}
        description={t("analysis.load.chartSubtitle")}
      />
    );
  }

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      opts={chartOpts}
      style={{ height: 248, width: "100%" }}
      notMerge
      lazyUpdate={false}
    />
  );
}

export function ProgressWeeksChart({ weeks }: { weeks: ProgressWeek[] }) {
  const { locale, t, units } = useI18n();
  const palette = useChartPalette();
  const labels = weeks.map((week) =>
    formatDate(week.week_start, locale, { day: "numeric", month: "short" }),
  );
  const distances = weeks.map((week) => week.distance_m);
  const loads = weeks.map((week) => week.load);

  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 450,
      animation: palette.animation,
      aria: ariaOption(),
      grid: { left: 8, right: 14, top: 20, bottom: 6, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow", shadowStyle: { color: palette.axisPointer } },
        backgroundColor: palette.panel,
        borderColor: palette.border,
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: palette.textStrong, fontFamily: "Manrope Variable", fontSize: 12 },
        formatter: (params: unknown) => {
          const list = (Array.isArray(params) ? params : [params]) as TooltipItem[];
          const index = list[0]?.dataIndex ?? 0;
          const week = weeks[index];
          if (!week) return "";
          return `<div style="font-weight:700;margin-bottom:4px">${formatDate(
            week.week_start,
            locale,
            { day: "numeric", month: "short", year: "numeric" },
          )}</div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="width:7px;height:7px;border-radius:2px;background:${palette.accent};display:inline-block"></span>
              <span style="color:${palette.textMuted}">${t("chart.distance")}</span>
              <strong style="margin-left:auto">${formatDistance(week.distance_m, units, locale, {
                digits: 1,
              })}</strong>
            </div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="width:7px;height:7px;border-radius:50%;background:${palette.orange};display:inline-block"></span>
              <span style="color:${palette.textMuted}">${t("progress.chart.load")}</span>
              <strong style="margin-left:auto">${formatNumber(week.load, locale)}</strong>
            </div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="color:${palette.textMuted}">${t("progress.chart.sessions")}</span>
              <strong style="margin-left:auto">${formatNumber(week.sessions, locale)}</strong>
            </div>`;
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { lineStyle: { color: palette.grid } },
        axisTick: { show: false },
        axisLabel: {
          color: palette.text,
          fontSize: 9.5,
          fontFamily: "JetBrains Mono Variable",
          hideOverlap: true,
        },
      },
      yAxis: [
        {
          type: "value",
          splitNumber: 4,
          axisLabel: {
            color: palette.text,
            fontSize: 10,
            fontFamily: "JetBrains Mono Variable",
            formatter: (value: number) => formatNumber(value, locale),
          },
          splitLine: { lineStyle: { color: palette.grid, type: "dashed" } },
        },
        {
          type: "value",
          splitNumber: 3,
          axisLabel: { show: false },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          type: "bar",
          data: distances.map((value) => ({
            value,
            itemStyle: {
              borderRadius: [4, 4, 2, 2],
              color: value > 0 ? palette.accentSoft : "transparent",
            },
          })),
          barWidth: "58%",
          emphasis: { itemStyle: { color: palette.accent } },
        },
        {
          type: "line",
          yAxisIndex: 1,
          data: loads,
          showSymbol: false,
          smooth: true,
          lineStyle: { color: palette.orange, width: 1.6, opacity: 0.9 },
          itemStyle: { color: palette.orange },
          z: 3,
        },
      ],
    }),
    [distances, labels, loads, locale, t, units, weeks, palette],
  );

  if (!weeks.length || !distances.some((value) => value > 0)) {
    return (
      <EmptyState
        compact
        icon={BarChart3}
        title={t("progress.weekly.empty")}
        description={t("progress.weekly.emptyBody")}
      />
    );
  }

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      opts={chartOpts}
      style={{ height: 252, width: "100%" }}
      notMerge
      lazyUpdate={false}
    />
  );
}

export function FitnessTrendChart({ points }: { points: FitnessPoint[] }) {
  const { locale, t } = useI18n();
  const palette = useChartPalette();
  const labels = points.map((point) =>
    formatDate(point.date, locale, { day: "numeric", month: "short" }),
  );

  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 450,
      animation: palette.animation,
      aria: ariaOption(),
      grid: { left: 8, right: 14, top: 20, bottom: 6, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: palette.panel,
        borderColor: palette.border,
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: palette.textStrong, fontFamily: "Manrope Variable", fontSize: 12 },
        formatter: (params: unknown) => {
          const list = (Array.isArray(params) ? params : [params]) as TooltipItem[];
          const index = list[0]?.dataIndex ?? 0;
          const point = points[index];
          if (!point) return "";
          return `<div style="font-weight:700;margin-bottom:4px">${formatDate(
            point.date,
            locale,
            { day: "numeric", month: "short", year: "numeric" },
          )}</div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="width:7px;height:7px;border-radius:50%;background:${palette.accent};display:inline-block"></span>
              <span style="color:${palette.textMuted}">${t("progress.fitness.chart")}</span>
              <strong style="margin-left:auto">${formatClock(point.time_s)}</strong>
            </div>
            ${
              point.low_s !== null && point.low_s !== undefined && point.high_s !== null && point.high_s !== undefined
                ? `<div style="display:flex;align-items:center;gap:6px;margin-top:4px">
                    <span style="color:${palette.textMuted}">${t("performance.estimate.range")}</span>
                    <strong style="margin-left:auto">${formatClock(point.low_s)} – ${formatClock(point.high_s)}</strong>
                  </div>`
                : ""
            }`;
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { lineStyle: { color: palette.grid } },
        axisTick: { show: false },
        axisLabel: {
          color: palette.text,
          fontSize: 9.5,
          fontFamily: "JetBrains Mono Variable",
          hideOverlap: true,
        },
      },
      yAxis: {
        type: "value",
        inverse: true,
        scale: true,
        axisLabel: {
          color: palette.text,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => formatClock(value),
        },
        splitLine: { lineStyle: { color: palette.grid, type: "dashed" } },
      },
      series: [
        {
          name: t("performance.estimate.range"),
          type: "line",
          data: points.map((point) => point.high_s ?? null),
          showSymbol: false,
          connectNulls: true,
          lineStyle: { color: palette.blueFade, width: 1, type: "dashed" },
          itemStyle: { color: palette.blueFade },
        },
        {
          name: t("performance.estimate.range"),
          type: "line",
          data: points.map((point) => point.low_s ?? null),
          showSymbol: false,
          connectNulls: true,
          lineStyle: { color: palette.blueFade, width: 1, type: "dashed" },
          itemStyle: { color: palette.blueFade },
        },
        {
          name: t("progress.fitness.chart"),
          type: "line",
          data: points.map((point) => point.time_s),
          showSymbol: true,
          symbolSize: 5,
          smooth: true,
          lineStyle: { color: palette.accent, width: 2.2 },
          itemStyle: { color: palette.accent },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: palette.accentFillStart },
                { offset: 1, color: palette.accentZero },
              ],
            },
          },
        },
      ],
    }),
    [labels, locale, points, t, palette],
  );

  if (!points.length) {
    return (
      <EmptyState
        compact
        icon={TrendingUp}
        title={t("progress.fitness.empty")}
        description={t("progress.fitness.emptyBody")}
      />
    );
  }

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      opts={chartOpts}
      style={{ height: 252, width: "100%" }}
      notMerge
      lazyUpdate={false}
    />
  );
}

export function GoalTrendChart({
  points,
  results = [],
  targetTimeS,
}: {
  points: GoalHistoryPoint[];
  results?: GoalResult[];
  targetTimeS: number;
}) {
  const { locale, t } = useI18n();
  const palette = useChartPalette();
  const dates = Array.from(
    new Set([...points.map((point) => point.date), ...results.map((item) => item.date)]),
  ).sort();
  const pointByDate = new Map(points.map((point) => [point.date, point]));
  const labels = dates.map((value) =>
    formatDate(value, locale, { day: "numeric", month: "short" }),
  );
  const predicted = dates.map((value) => pointByDate.get(value)?.predicted_s ?? null);
  const resultByDate = new Map<string, GoalResult[]>();
  for (const result of results) {
    resultByDate.set(result.date, [...(resultByDate.get(result.date) ?? []), result]);
  }
  const resultPoints = results.map((result) => ({
    value: [dates.indexOf(result.date), result.time_s],
    name: result.activity_name,
  }));

  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 450,
      animation: palette.animation,
      aria: ariaOption(),
      grid: { left: 8, right: 14, top: 20, bottom: 6, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: palette.panel,
        borderColor: palette.border,
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: palette.textStrong, fontFamily: "Manrope Variable", fontSize: 12 },
        formatter: (params: unknown) => {
          const list = (Array.isArray(params) ? params : [params]) as TooltipItem[];
          const first = list[0];
          if (!first) return "";
          const index = first.axisValueLabel ? labels.indexOf(first.axisValueLabel) : -1;
          const day = dates[index >= 0 ? index : (first.dataIndex ?? 0)];
          if (!day) return "";
          const point = pointByDate.get(day);
          const actuals = resultByDate.get(day) ?? [];
          const predictedRow = point
            ? `<div style="display:flex;align-items:center;gap:6px;margin-top:4px">
                <span style="width:7px;height:7px;border-radius:50%;background:${palette.accent};display:inline-block"></span>
                <span style="color:${palette.textMuted}">${t("tracking.goal.predicted")}</span>
                <strong style="margin-left:auto">${formatClock(point.predicted_s)}</strong>
              </div>`
            : "";
          const actualRows = actuals
            .map(
              (actual) => `<div style="display:flex;align-items:center;gap:6px;margin-top:4px">
                <span style="width:7px;height:7px;border-radius:50%;background:${palette.orange};display:inline-block"></span>
                <span style="color:${palette.textMuted}">${
                  actual.is_race
                    ? t("tracking.goal.result.race")
                    : t("tracking.goal.result.effort")
                }</span>
                <strong style="margin-left:auto">${formatClock(actual.time_s)}</strong>
              </div>`,
            )
            .join("");
          return `<div style="font-weight:700;margin-bottom:4px">${formatDate(
            day,
            locale,
            { day: "numeric", month: "short", year: "numeric" },
          )}</div>${predictedRow}${actualRows}`;
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { lineStyle: { color: palette.grid } },
        axisTick: { show: false },
        axisLabel: {
          color: palette.text,
          fontSize: 9.5,
          fontFamily: "JetBrains Mono Variable",
          hideOverlap: true,
        },
      },
      yAxis: {
        type: "value",
        inverse: true,
        scale: true,
        axisLabel: {
          color: palette.text,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => formatClock(value),
        },
        splitLine: { lineStyle: { color: palette.grid, type: "dashed" } },
      },
      series: [
        {
          name: t("tracking.goal.predicted"),
          type: "line",
          data: predicted,
          showSymbol: predicted.length <= 40,
          symbolSize: 4,
          connectNulls: true,
          lineStyle: { color: palette.accent, width: 2.2 },
          itemStyle: { color: palette.accent },
          markLine: {
            silent: true,
            symbol: "none",
            label: {
              color: palette.text,
              fontSize: 9,
              formatter: t("tracking.goal.target"),
            },
            lineStyle: { color: palette.orange, width: 1.4, type: "dashed" },
            data: [{ yAxis: targetTimeS }],
          },
        },
        {
          name: t("tracking.goal.results"),
          type: "scatter",
          data: resultPoints,
          symbolSize: 8,
          itemStyle: {
            color: palette.orange,
            borderColor: palette.panel,
            borderWidth: 1,
          },
          z: 6,
        },
      ],
    }),
    [dates, labels, locale, pointByDate, predicted, resultByDate, resultPoints, t, targetTimeS, palette],
  );

  if (dates.length < 2 && results.length === 0) return null;

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      opts={chartOpts}
      style={{ height: 190, width: "100%" }}
      notMerge
      lazyUpdate={false}
    />
  );
}

export function PaceHrChart({ group }: { group: PaceHrGroup }) {
  const { locale, t, units } = useI18n();
  const palette = useChartPalette();
  const points = group.points ?? [];
  const earlyLine = group.early_line ?? [];
  const recentLine = group.recent_line ?? [];
  const early = points
    .filter((point) => point.period === "early")
    .map((point) => ({
      value: [point.avg_hr, point.pace_s_per_km],
      name: point.activity_name,
      date: point.date,
      envPace: point.environment_adjusted_pace_s_per_km,
      envHrPace: point.environment_hr_adjusted_pace_s_per_km,
      temperature: point.temperature_c,
    }));
  const recent = points
    .filter((point) => point.period === "recent")
    .map((point) => ({
      value: [point.avg_hr, point.pace_s_per_km],
      name: point.activity_name,
      date: point.date,
      envPace: point.environment_adjusted_pace_s_per_km,
      envHrPace: point.environment_hr_adjusted_pace_s_per_km,
      temperature: point.temperature_c,
    }));

  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 450,
      animation: palette.animation,
      aria: ariaOption(),
      grid: { left: 10, right: 18, top: 30, bottom: 10, containLabel: true },
      tooltip: {
        trigger: "item",
        backgroundColor: palette.panel,
        borderColor: palette.border,
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: palette.textStrong, fontFamily: "Manrope Variable", fontSize: 12 },
        formatter: (params: unknown) => {
          const item = (Array.isArray(params) ? params[0] : params) as TooltipItem | undefined;
          const data = item?.data as
            | {
                name?: string;
                value?: [number, number];
                date?: string;
                envPace?: number | null;
                envHrPace?: number | null;
                temperature?: number | null;
              }
            | undefined;
          if (!item || !data || !Array.isArray(data.value)) return "";
          const [hr, pace] = data.value;
          const environmentRow =
            data.envPace != null && Math.abs(data.envPace - pace) >= 0.5
              ? `<div style="display:flex;justify-content:space-between;gap:16px;margin-top:3px">
              <span style="color:${palette.textMuted}">${t("progress.paceHr.chartEnvironmentPace")}</span>
              <strong>${formatPace(data.envPace, units)}</strong>
            </div>`
              : "";
          const environmentHrRow =
            data.envHrPace != null && Math.abs(data.envHrPace - pace) >= 0.5
              ? `<div style="display:flex;justify-content:space-between;gap:16px;margin-top:3px">
              <span style="color:${palette.textMuted}">${t("progress.paceHr.chartEnvironmentHrPace")}</span>
              <strong>${formatPace(data.envHrPace, units)}</strong>
            </div>`
              : "";
          const temperatureRow =
            data.temperature != null
              ? `<div style="display:flex;justify-content:space-between;gap:16px;margin-top:3px">
              <span style="color:${palette.textMuted}">${t("progress.paceHr.environment.temperature")}</span>
              <strong>${formatNumber(data.temperature, locale, 1)} °C</strong>
            </div>`
              : "";
          return `<div style="font-weight:700;margin-bottom:3px">${data.name ?? ""}</div>
            <div style="color:${palette.textMuted}">${formatDate(data.date, locale)}</div>
            <div style="display:flex;justify-content:space-between;gap:16px;margin-top:5px">
              <span style="color:${palette.textMuted}">${t("progress.paceHr.chartHr")}</span>
              <strong>${formatNumber(hr, locale)} bpm</strong>
            </div>
            <div style="display:flex;justify-content:space-between;gap:16px;margin-top:3px">
              <span style="color:${palette.textMuted}">${t("progress.paceHr.chartPace")}</span>
              <strong>${formatPace(pace, units)}</strong>
            </div>
            ${environmentRow}${environmentHrRow}${temperatureRow}`;
        },
      },
      xAxis: {
        type: "value",
        name: t("progress.paceHr.chartHr"),
        nameTextStyle: { color: palette.text, fontSize: 9 },
        min: Math.max(80, Number(group.hr_min) - 6),
        max: Number(group.hr_max) + 6,
        axisLine: { lineStyle: { color: palette.grid } },
        axisTick: { show: false },
        axisLabel: {
          color: palette.text,
          fontSize: 9.5,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => formatNumber(value, locale),
        },
        splitLine: { lineStyle: { color: palette.grid, type: "dashed" } },
      },
      yAxis: {
        type: "value",
        inverse: true,
        scale: true,
        name: t("progress.paceHr.chartPace"),
        nameTextStyle: { color: palette.text, fontSize: 9 },
        axisLabel: {
          color: palette.text,
          fontSize: 9.5,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => formatPace(value, units, { suffix: false }),
        },
        splitLine: { lineStyle: { color: palette.grid, type: "dashed" } },
      },
      series: [
        {
          name: t("progress.paceHr.early"),
          type: "scatter",
          data: early,
          symbolSize: 8,
          itemStyle: { color: palette.blue, opacity: 0.75 },
        },
        {
          name: t("progress.paceHr.recent"),
          type: "scatter",
          data: recent,
          symbolSize: 9,
          itemStyle: { color: palette.accent },
        },
        {
          name: t("progress.paceHr.early"),
          type: "line",
          data: earlyLine.map((line) => [line.hr, line.pace_s_per_km]),
          showSymbol: false,
          silent: true,
          lineStyle: { color: palette.blue, width: 1.5, type: "dashed", opacity: 0.7 },
          itemStyle: { color: palette.blue },
        },
        {
          name: t("progress.paceHr.recent"),
          type: "line",
          data: recentLine.map((line) => [line.hr, line.pace_s_per_km]),
          showSymbol: false,
          silent: true,
          lineStyle: { color: palette.accent, width: 1.8, type: "dashed" },
          itemStyle: { color: palette.accent },
        },
      ],
    }),
    [early, earlyLine, group.hr_max, group.hr_min, locale, recent, recentLine, t, units, palette],
  );

  if (!points.length) return null;

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      opts={chartOpts}
      style={{ height: 300, width: "100%" }}
      notMerge
      lazyUpdate={false}
    />
  );
}

export function ComparisonSplitsChart({ splits }: { splits: ComparisonSplit[] }) {
  const { units, t } = useI18n();
  const palette = useChartPalette();
  const labels = splits.map((split) => `${split.index}`);
  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 450,
      animation: palette.animation,
      aria: ariaOption(),
      grid: { left: 8, right: 14, top: 22, bottom: 6, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: palette.panel,
        borderColor: palette.border,
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: palette.textStrong, fontFamily: "Manrope Variable", fontSize: 12 },
        formatter: (params: unknown) => {
          const list = (Array.isArray(params) ? params : [params]) as TooltipItem[];
          const index = list[0]?.dataIndex ?? 0;
          const split = splits[index];
          if (!split) return "";
          return `<div style="font-weight:700;margin-bottom:4px">${t("compare.chart.km", {
            km: split.index,
          })}</div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="width:7px;height:7px;border-radius:50%;background:${palette.accent};display:inline-block"></span>
              <span style="color:${palette.textMuted}">${t("compare.chart.left")}</span>
              <strong style="margin-left:auto">${formatPace(split.left_pace_s_per_km, units)}</strong>
            </div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="width:7px;height:7px;border-radius:50%;background:${palette.orange};display:inline-block"></span>
              <span style="color:${palette.textMuted}">${t("compare.chart.right")}</span>
              <strong style="margin-left:auto">${formatPace(split.right_pace_s_per_km, units)}</strong>
            </div>`;
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        name: t("compare.chart.kmAxis"),
        nameTextStyle: { color: palette.text, fontSize: 10 },
        axisLine: { lineStyle: { color: palette.grid } },
        axisTick: { show: false },
        axisLabel: {
          color: palette.text,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
        },
      },
      yAxis: {
        type: "value",
        inverse: true,
        scale: true,
        axisLabel: {
          color: palette.text,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => formatPace(value, units, { suffix: false }),
        },
        splitLine: { lineStyle: { color: palette.grid, type: "dashed" } },
      },
      series: [
        {
          name: t("compare.chart.left"),
          type: "line",
          data: splits.map((split) => split.left_pace_s_per_km),
          showSymbol: true,
          symbolSize: 4,
          connectNulls: true,
          lineStyle: { color: palette.accent, width: 2 },
          itemStyle: { color: palette.accent },
        },
        {
          name: t("compare.chart.right"),
          type: "line",
          data: splits.map((split) => split.right_pace_s_per_km),
          showSymbol: true,
          symbolSize: 4,
          connectNulls: true,
          lineStyle: { color: palette.orange, width: 2 },
          itemStyle: { color: palette.orange },
        },
      ],
    }),
    [labels, splits, t, units, palette],
  );

  if (splits.length < 2) return null;

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      opts={chartOpts}
      style={{ height: 240, width: "100%" }}
      notMerge
      lazyUpdate={false}
    />
  );
}

export function RecoveryTrendChart({ metric }: { metric: RecoveryMetric }) {
  const { locale, units, t } = useI18n();
  const palette = useChartPalette();
  const points = metric.points ?? [];
  const labels = points.map((point) =>
    formatDate(point.date, locale, { day: "numeric", month: "short" }),
  );
  const values = points.map((point) => point.value);

  const axisValue = (value: number) => {
    if (metric.key === "sleep_duration") {
      return `${formatNumber(value / 3600, locale, 1)}h`;
    }
    if (metric.key === "weight") {
      const shown = units === "imperial" ? value * 2.2046226218 : value;
      return formatNumber(shown, locale, 1);
    }
    return formatNumber(value, locale, 0);
  };

  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 450,
      animation: palette.animation,
      aria: ariaOption(),
      grid: { left: 8, right: 14, top: 20, bottom: 6, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: palette.panel,
        borderColor: palette.border,
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: palette.textStrong, fontFamily: "Manrope Variable", fontSize: 12 },
        formatter: (params: unknown) => {
          const list = (Array.isArray(params) ? params : [params]) as TooltipItem[];
          const item = list[0];
          if (!item) return "";
          const index = item.dataIndex ?? 0;
          const point = points[index];
          if (!point) return "";
          return `<div style="font-weight:700;margin-bottom:4px">${formatDate(
            point.date,
            locale,
            { day: "numeric", month: "short", year: "numeric" },
          )}</div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="width:7px;height:7px;border-radius:50%;background:${palette.blue};display:inline-block"></span>
              <span style="color:${palette.textMuted}">${t(`recovery.metric.${metric.key}` as MessageKey)}</span>
              <strong style="margin-left:auto">${formatRecoveryValue(
                metric.key,
                point.value,
                units,
                locale,
              )}</strong>
            </div>`;
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { lineStyle: { color: palette.grid } },
        axisTick: { show: false },
        axisLabel: {
          color: palette.text,
          fontSize: 9.5,
          fontFamily: "JetBrains Mono Variable",
          hideOverlap: true,
        },
      },
      yAxis: {
        type: "value",
        scale: true,
        splitNumber: 4,
        axisLabel: {
          color: palette.text,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => axisValue(value),
        },
        splitLine: { lineStyle: { color: palette.grid, type: "dashed" } },
      },
      series: [
        {
          type: "line",
          data: values,
          showSymbol: values.length <= 45,
          symbolSize: 4,
          smooth: 0.2,
          lineStyle: { color: palette.blue, width: 2.2 },
          itemStyle: { color: palette.blue },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: palette.blueFillStart },
                { offset: 1, color: palette.blueZero },
              ],
            },
          },
        },
      ],
    }),
    [labels, locale, metric.key, points, t, units, values, palette],
  );

  if (points.length < 2) {
    return (
      <EmptyState
        compact
        icon={TrendingUp}
        title={t("recovery.chart.empty")}
        description={t("recovery.chart.emptyBody")}
      />
    );
  }

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      opts={chartOpts}
      style={{ height: 260, width: "100%" }}
      notMerge
      lazyUpdate={false}
    />
  );
}

export function MiniBars({
  values,
  labels,
}: {
  values: number[];
  labels?: string[];
}) {
  const max = Math.max(...values, 1);
  return (
    <div className="mini-bars" aria-hidden="true">
      {values.map((value, index) => (
        <span
          key={`${labels?.[index] ?? index}-${index}`}
          className={value > 0 ? "mini-bars__bar is-filled" : "mini-bars__bar"}
          style={{ height: `${Math.max(8, (value / max) * 100)}%` }}
        />
      ))}
    </div>
  );
}

export function weekDayLabel(value: string, locale: "es" | "en"): string {
  return new Intl.DateTimeFormat(locale === "es" ? "es-ES" : "en-US", {
    weekday: "short",
  }).format(parseUtc(value));
}
