import { useMemo } from "react";
import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import {
  AxisPointerComponent,
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import type { EChartsOption } from "echarts";
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
  PaceHrGroup,
  PerformanceSnapshot,
  ProgressWeek,
  StreamPoint,
  WeeklyDay,
} from "@/api/client";
import { useI18n } from "@/i18n";
import { EmptyState } from "@/components/ui";
import {
  formatClock,
  formatDate,
  formatDistance,
  formatNumber,
  formatPace,
  parseUtc,
  weekdayKeys,
} from "@/lib/format";

const TEXT = "#8d9b94";
const GRID = "rgba(255,255,255,0.07)";
const ACCENT = "#c9f56a";
const ORANGE = "#ffab6b";
const EARLY = "#7bc8ff";
const PANEL = "rgba(15, 21, 18, 0.94)";

const chartOpts = { renderer: "canvas" as const };

echarts.use([
  BarChart,
  LineChart,
  ScatterChart,
  AxisPointerComponent,
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
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
      grid: { left: 6, right: 10, top: 24, bottom: 6, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow", shadowStyle: { color: "rgba(255,255,255,0.025)" } },
        backgroundColor: PANEL,
        borderColor: "rgba(255,255,255,0.09)",
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: "#eef5f0", fontFamily: "Manrope Variable", fontSize: 12 },
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
              <span style="width:7px;height:7px;border-radius:2px;background:${ACCENT};display:inline-block"></span>
              <span style="color:#a9b5ae">${t("chart.distance")}</span>
              <strong style="margin-left:auto">${formatNumber(value, locale, value > 0 && value < 100 ? 2 : 1)} ${volumeUnit}</strong>
            </div>`;
        },
      },
      xAxis: {
        type: "category",
        data: weekdayKeys().map((key) => t(key)),
        axisLine: { lineStyle: { color: GRID } },
        axisTick: { show: false },
        axisLabel: { color: TEXT, fontSize: 11, margin: 12, fontFamily: "Manrope Variable" },
      },
      yAxis: {
        type: "value",
        splitNumber: 4,
        axisLabel: {
          color: TEXT,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => formatNumber(value, locale, 0),
        },
        splitLine: { lineStyle: { color: GRID, type: "dashed" } },
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
                { offset: 0, color: ACCENT },
                { offset: 1, color: "#769e38" },
              ],
            },
          },
          emphasis: { itemStyle: { color: "#dcff94" } },
        },
      ],
    }),
    [days, locale, t, units, values, volumeUnit],
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
      lazyUpdate
    />
  );
}

export function ActivityStreamChart({ points }: { points: StreamPoint[] }) {
  const { locale, t, units } = useI18n();
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
      grid: { left: 10, right: 12, top: 28, bottom: 10, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: PANEL,
        borderColor: "rgba(255,255,255,0.09)",
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: "#eef5f0", fontFamily: "Manrope Variable", fontSize: 12 },
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
              <span style="color:#a9b5ae">${item.seriesName === "pace" ? t("detail.chart.pace") : t("detail.chart.hr")}</span>
              <strong style="margin-left:auto">${formatted}</strong>
            </div>`;
          });
          return `<div style="font-family:JetBrains Mono Variable;font-size:11px;color:#a9b5ae">${formatClock(time)}</div>${rows.join("")}`;
        },
      },
      xAxis: {
        type: "value",
        min: 0,
        axisLine: { lineStyle: { color: GRID } },
        axisTick: { show: false },
        axisLabel: {
          color: TEXT,
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
            color: ACCENT,
            fontSize: 10,
            fontFamily: "JetBrains Mono Variable",
            formatter: (value: number) => formatPace(value, units, { suffix: false }),
          },
          splitLine: { lineStyle: { color: GRID, type: "dashed" } },
        },
        {
          type: "value",
          scale: true,
          axisLabel: {
            color: ORANGE,
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
          lineStyle: { color: ACCENT, width: 2 },
          itemStyle: { color: ACCENT },
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
          lineStyle: { color: ORANGE, width: 1.6, opacity: 0.9 },
          itemStyle: { color: ORANGE },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(255,171,107,0.16)" },
                { offset: 1, color: "rgba(255,171,107,0)" },
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
    [locale, paceUnit, series.hrData, series.paceData, t, units],
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
      lazyUpdate
    />
  );
}

const DISTANCE_META = [
  { key: "5k", label: "distance.5k" as const, color: "#c9f56a" },
  { key: "10k", label: "distance.10k" as const, color: "#7bc8ff" },
  { key: "half_marathon", label: "distance.half_marathon" as const, color: "#ffab6b" },
  { key: "marathon", label: "distance.marathon" as const, color: "#b79bff" },
];

export function PerformanceHistoryChart({ items }: { items: PerformanceSnapshot[] }) {
  const { locale, t } = useI18n();

  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 450,
      grid: { left: 8, right: 16, top: 28, bottom: 8, containLabel: true },
      legend: {
        top: 0,
        right: 0,
        icon: "roundRect",
        itemWidth: 9,
        itemHeight: 9,
        textStyle: { color: TEXT, fontSize: 11, fontFamily: "Manrope Variable" },
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: PANEL,
        borderColor: "rgba(255,255,255,0.09)",
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: "#eef5f0", fontFamily: "Manrope Variable", fontSize: 12 },
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
                  <span style="color:#a9b5ae">${item.seriesName ?? ""}</span>
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
        axisLine: { lineStyle: { color: GRID } },
        axisTick: { show: false },
        axisLabel: {
          color: TEXT,
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
          color: TEXT,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => formatClock(value),
        },
        splitLine: { lineStyle: { color: GRID, type: "dashed" } },
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
        lineStyle: { color: distance.color, width: 2 },
        itemStyle: { color: distance.color },
        emphasis: { focus: "series" as const },
      })),
    }),
    [items, locale, t],
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
      lazyUpdate
    />
  );
}

export function Vo2MaxChart({ points }: { points: GarminMetricPoint[] }) {
  const { locale, t } = useI18n();
  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 450,
      grid: { left: 6, right: 10, top: 18, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: PANEL,
        borderColor: "rgba(255,255,255,0.09)",
        borderWidth: 1,
        padding: [9, 11],
        textStyle: { color: "#eef5f0", fontFamily: "Manrope Variable", fontSize: 12 },
        formatter: (params: unknown) => {
          const list = (Array.isArray(params) ? params : [params]) as TooltipItem[];
          const item = list[0];
          if (!item) return "";
          const value = Number((item.value as [number, number] | undefined)?.[1]);
          return `<div style="font-weight:700;margin-bottom:2px">${item.axisValueLabel ?? ""}</div>
            <span style="color:#a9b5ae">${t("performance.garmin.vo2max")}</span>
            <strong style="margin-left:8px">${formatNumber(value, locale, 1)}</strong>`;
        },
      },
      xAxis: {
        type: "category",
        data: points.map((point) => formatDate(point.date, locale, { day: "numeric", month: "short" })),
        axisLine: { lineStyle: { color: GRID } },
        axisTick: { show: false },
        axisLabel: {
          color: TEXT,
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
          color: TEXT,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
        },
        splitLine: { lineStyle: { color: GRID, type: "dashed" } },
      },
      series: [
        {
          type: "line",
          data: points.map((point) => point.value),
          showSymbol: false,
          smooth: 0.25,
          lineStyle: { color: ACCENT, width: 2 },
          itemStyle: { color: ACCENT },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(201,245,106,0.20)" },
                { offset: 1, color: "rgba(201,245,106,0)" },
              ],
            },
          },
        },
      ],
    }),
    [locale, points, t],
  );

  if (points.length < 2) return null;

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      opts={chartOpts}
      style={{ height: 150, width: "100%" }}
      notMerge
      lazyUpdate
    />
  );
}

export function WeeklyLoadChart({ load }: { load: AnalysisLoad }) {
  const { locale, t, units } = useI18n();
  const labels = load.weekly.map((point) =>
    formatDate(point.week_start, locale, { day: "numeric", month: "short" }),
  );
  const values = load.weekly.map((point) => point.load);

  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 450,
      grid: { left: 8, right: 14, top: 20, bottom: 6, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow", shadowStyle: { color: "rgba(255,255,255,0.025)" } },
        backgroundColor: PANEL,
        borderColor: "rgba(255,255,255,0.09)",
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: "#eef5f0", fontFamily: "Manrope Variable", fontSize: 12 },
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
              <span style="width:7px;height:7px;border-radius:2px;background:${ACCENT};display:inline-block"></span>
              <span style="color:#a9b5ae">${t("analysis.load.chartLoad")}</span>
              <strong style="margin-left:auto">${formatNumber(point.load, locale)}</strong>
            </div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="width:7px;height:7px;border-radius:50%;background:${ORANGE};display:inline-block"></span>
              <span style="color:#a9b5ae">${t("analysis.load.chartChronic")}</span>
              <strong style="margin-left:auto">${formatNumber(load.chronic_weekly, locale)}</strong>
            </div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="color:#a9b5ae">${t("analysis.load.chartDistance")}</span>
              <strong style="margin-left:auto">${formatDistance(
                point.distance_m,
                units,
                locale,
                { digits: 1 },
              )}</strong>
            </div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="color:#a9b5ae">${t("analysis.load.chartSessions")}</span>
              <strong style="margin-left:auto">${formatNumber(point.sessions, locale)}</strong>
            </div>`;
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { lineStyle: { color: GRID } },
        axisTick: { show: false },
        axisLabel: {
          color: TEXT,
          fontSize: 9.5,
          fontFamily: "JetBrains Mono Variable",
          hideOverlap: true,
        },
      },
      yAxis: {
        type: "value",
        splitNumber: 4,
        axisLabel: {
          color: TEXT,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => formatNumber(value, locale),
        },
        splitLine: { lineStyle: { color: GRID, type: "dashed" } },
      },
      series: [
        {
          type: "bar",
          data: values.map((value, index) => ({
            value,
            itemStyle: {
              borderRadius: [4, 4, 2, 2],
              color:
                index === values.length - 1 ? ACCENT : "rgba(201, 245, 106, 0.42)",
            },
          })),
          barWidth: "52%",
          emphasis: { itemStyle: { color: "#dcff94" } },
        },
        {
          type: "line",
          data: values.map(() => load.chronic_weekly),
          showSymbol: false,
          silent: true,
          lineStyle: { color: ORANGE, width: 1.4, type: "dashed", opacity: 0.8 },
          itemStyle: { color: ORANGE },
          z: 3,
        },
      ],
    }),
    [labels, load.chronic_weekly, load.weekly, locale, t, units, values],
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
      lazyUpdate
    />
  );
}

export function ProgressWeeksChart({ weeks }: { weeks: ProgressWeek[] }) {
  const { locale, t, units } = useI18n();
  const labels = weeks.map((week) =>
    formatDate(week.week_start, locale, { day: "numeric", month: "short" }),
  );
  const distances = weeks.map((week) => week.distance_m);
  const loads = weeks.map((week) => week.load);

  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 450,
      grid: { left: 8, right: 14, top: 20, bottom: 6, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow", shadowStyle: { color: "rgba(255,255,255,0.025)" } },
        backgroundColor: PANEL,
        borderColor: "rgba(255,255,255,0.09)",
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: "#eef5f0", fontFamily: "Manrope Variable", fontSize: 12 },
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
              <span style="width:7px;height:7px;border-radius:2px;background:${ACCENT};display:inline-block"></span>
              <span style="color:#a9b5ae">${t("chart.distance")}</span>
              <strong style="margin-left:auto">${formatDistance(week.distance_m, units, locale, {
                digits: 1,
              })}</strong>
            </div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="width:7px;height:7px;border-radius:50%;background:${ORANGE};display:inline-block"></span>
              <span style="color:#a9b5ae">${t("progress.chart.load")}</span>
              <strong style="margin-left:auto">${formatNumber(week.load, locale)}</strong>
            </div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="color:#a9b5ae">${t("progress.chart.sessions")}</span>
              <strong style="margin-left:auto">${formatNumber(week.sessions, locale)}</strong>
            </div>`;
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { lineStyle: { color: GRID } },
        axisTick: { show: false },
        axisLabel: {
          color: TEXT,
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
            color: TEXT,
            fontSize: 10,
            fontFamily: "JetBrains Mono Variable",
            formatter: (value: number) => formatNumber(value, locale),
          },
          splitLine: { lineStyle: { color: GRID, type: "dashed" } },
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
              color: value > 0 ? "rgba(201, 245, 106, 0.52)" : "transparent",
            },
          })),
          barWidth: "58%",
          emphasis: { itemStyle: { color: ACCENT } },
        },
        {
          type: "line",
          yAxisIndex: 1,
          data: loads,
          showSymbol: false,
          smooth: true,
          lineStyle: { color: ORANGE, width: 1.6, opacity: 0.9 },
          itemStyle: { color: ORANGE },
          z: 3,
        },
      ],
    }),
    [distances, labels, loads, locale, t, units, weeks],
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
      lazyUpdate
    />
  );
}

export function FitnessTrendChart({ points }: { points: FitnessPoint[] }) {
  const { locale, t } = useI18n();
  const labels = points.map((point) =>
    formatDate(point.date, locale, { day: "numeric", month: "short" }),
  );

  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 450,
      grid: { left: 8, right: 14, top: 20, bottom: 6, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: PANEL,
        borderColor: "rgba(255,255,255,0.09)",
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: "#eef5f0", fontFamily: "Manrope Variable", fontSize: 12 },
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
              <span style="width:7px;height:7px;border-radius:50%;background:${ACCENT};display:inline-block"></span>
              <span style="color:#a9b5ae">${t("progress.fitness.chart")}</span>
              <strong style="margin-left:auto">${formatClock(point.time_s)}</strong>
            </div>
            ${
              point.low_s !== null && point.low_s !== undefined && point.high_s !== null && point.high_s !== undefined
                ? `<div style="display:flex;align-items:center;gap:6px;margin-top:4px">
                    <span style="color:#a9b5ae">${t("performance.estimate.range")}</span>
                    <strong style="margin-left:auto">${formatClock(point.low_s)} – ${formatClock(point.high_s)}</strong>
                  </div>`
                : ""
            }`;
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { lineStyle: { color: GRID } },
        axisTick: { show: false },
        axisLabel: {
          color: TEXT,
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
          color: TEXT,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => formatClock(value),
        },
        splitLine: { lineStyle: { color: GRID, type: "dashed" } },
      },
      series: [
        {
          name: t("performance.estimate.range"),
          type: "line",
          data: points.map((point) => point.high_s ?? null),
          showSymbol: false,
          connectNulls: true,
          lineStyle: { color: "rgba(123, 200, 255, 0.35)", width: 1, type: "dashed" },
          itemStyle: { color: "rgba(123, 200, 255, 0.35)" },
        },
        {
          name: t("performance.estimate.range"),
          type: "line",
          data: points.map((point) => point.low_s ?? null),
          showSymbol: false,
          connectNulls: true,
          lineStyle: { color: "rgba(123, 200, 255, 0.35)", width: 1, type: "dashed" },
          itemStyle: { color: "rgba(123, 200, 255, 0.35)" },
        },
        {
          name: t("progress.fitness.chart"),
          type: "line",
          data: points.map((point) => point.time_s),
          showSymbol: true,
          symbolSize: 5,
          smooth: true,
          lineStyle: { color: ACCENT, width: 2.2 },
          itemStyle: { color: ACCENT },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(201, 245, 106, 0.18)" },
                { offset: 1, color: "rgba(201, 245, 106, 0)" },
              ],
            },
          },
        },
      ],
    }),
    [labels, locale, points, t],
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
      lazyUpdate
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
      grid: { left: 8, right: 14, top: 20, bottom: 6, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: PANEL,
        borderColor: "rgba(255,255,255,0.09)",
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: "#eef5f0", fontFamily: "Manrope Variable", fontSize: 12 },
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
                <span style="width:7px;height:7px;border-radius:50%;background:${ACCENT};display:inline-block"></span>
                <span style="color:#a9b5ae">${t("tracking.goal.predicted")}</span>
                <strong style="margin-left:auto">${formatClock(point.predicted_s)}</strong>
              </div>`
            : "";
          const actualRows = actuals
            .map(
              (actual) => `<div style="display:flex;align-items:center;gap:6px;margin-top:4px">
                <span style="width:7px;height:7px;border-radius:50%;background:${ORANGE};display:inline-block"></span>
                <span style="color:#a9b5ae">${
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
        axisLine: { lineStyle: { color: GRID } },
        axisTick: { show: false },
        axisLabel: {
          color: TEXT,
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
          color: TEXT,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => formatClock(value),
        },
        splitLine: { lineStyle: { color: GRID, type: "dashed" } },
      },
      series: [
        {
          name: t("tracking.goal.predicted"),
          type: "line",
          data: predicted,
          showSymbol: predicted.length <= 40,
          symbolSize: 4,
          connectNulls: true,
          lineStyle: { color: ACCENT, width: 2.2 },
          itemStyle: { color: ACCENT },
          markLine: {
            silent: true,
            symbol: "none",
            label: {
              color: TEXT,
              fontSize: 9,
              formatter: t("tracking.goal.target"),
            },
            lineStyle: { color: ORANGE, width: 1.4, type: "dashed" },
            data: [{ yAxis: targetTimeS }],
          },
        },
        {
          name: t("tracking.goal.results"),
          type: "scatter",
          data: resultPoints,
          symbolSize: 8,
          itemStyle: {
            color: ORANGE,
            borderColor: "#0f1512",
            borderWidth: 1,
          },
          z: 6,
        },
      ],
    }),
    [dates, labels, locale, pointByDate, predicted, resultByDate, resultPoints, t, targetTimeS],
  );

  if (dates.length < 2 && results.length === 0) return null;

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      opts={chartOpts}
      style={{ height: 190, width: "100%" }}
      notMerge
      lazyUpdate
    />
  );
}

export function PaceHrChart({ group }: { group: PaceHrGroup }) {
  const { locale, t, units } = useI18n();
  const points = group.points ?? [];
  const earlyLine = group.early_line ?? [];
  const recentLine = group.recent_line ?? [];
  const early = points
    .filter((point) => point.period === "early")
    .map((point) => ({
      value: [point.avg_hr, point.pace_s_per_km],
      name: point.activity_name,
      date: point.date,
    }));
  const recent = points
    .filter((point) => point.period === "recent")
    .map((point) => ({
      value: [point.avg_hr, point.pace_s_per_km],
      name: point.activity_name,
      date: point.date,
    }));

  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 450,
      grid: { left: 10, right: 18, top: 30, bottom: 10, containLabel: true },
      tooltip: {
        trigger: "item",
        backgroundColor: PANEL,
        borderColor: "rgba(255,255,255,0.09)",
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: "#eef5f0", fontFamily: "Manrope Variable", fontSize: 12 },
        formatter: (params: unknown) => {
          const item = (Array.isArray(params) ? params[0] : params) as TooltipItem | undefined;
          const data = item?.data as
            | { name?: string; value?: [number, number]; date?: string }
            | undefined;
          if (!item || !data || !Array.isArray(data.value)) return "";
          const [hr, pace] = data.value;
          return `<div style="font-weight:700;margin-bottom:3px">${data.name ?? ""}</div>
            <div style="color:#a9b5ae">${formatDate(data.date, locale)}</div>
            <div style="display:flex;justify-content:space-between;gap:16px;margin-top:5px">
              <span style="color:#a9b5ae">${t("progress.paceHr.chartHr")}</span>
              <strong>${formatNumber(hr, locale)} bpm</strong>
            </div>
            <div style="display:flex;justify-content:space-between;gap:16px;margin-top:3px">
              <span style="color:#a9b5ae">${t("progress.paceHr.chartPace")}</span>
              <strong>${formatPace(pace, units)}</strong>
            </div>`;
        },
      },
      xAxis: {
        type: "value",
        name: t("progress.paceHr.chartHr"),
        nameTextStyle: { color: TEXT, fontSize: 9 },
        min: Math.max(80, Number(group.hr_min) - 6),
        max: Number(group.hr_max) + 6,
        axisLine: { lineStyle: { color: GRID } },
        axisTick: { show: false },
        axisLabel: {
          color: TEXT,
          fontSize: 9.5,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => formatNumber(value, locale),
        },
        splitLine: { lineStyle: { color: GRID, type: "dashed" } },
      },
      yAxis: {
        type: "value",
        inverse: true,
        scale: true,
        name: t("progress.paceHr.chartPace"),
        nameTextStyle: { color: TEXT, fontSize: 9 },
        axisLabel: {
          color: TEXT,
          fontSize: 9.5,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => formatPace(value, units, { suffix: false }),
        },
        splitLine: { lineStyle: { color: GRID, type: "dashed" } },
      },
      series: [
        {
          name: t("progress.paceHr.early"),
          type: "scatter",
          data: early,
          symbolSize: 8,
          itemStyle: { color: EARLY, opacity: 0.75 },
        },
        {
          name: t("progress.paceHr.recent"),
          type: "scatter",
          data: recent,
          symbolSize: 9,
          itemStyle: { color: ACCENT },
        },
        {
          name: t("progress.paceHr.early"),
          type: "line",
          data: earlyLine.map((line) => [line.hr, line.pace_s_per_km]),
          showSymbol: false,
          silent: true,
          lineStyle: { color: EARLY, width: 1.5, type: "dashed", opacity: 0.7 },
          itemStyle: { color: EARLY },
        },
        {
          name: t("progress.paceHr.recent"),
          type: "line",
          data: recentLine.map((line) => [line.hr, line.pace_s_per_km]),
          showSymbol: false,
          silent: true,
          lineStyle: { color: ACCENT, width: 1.8, type: "dashed" },
          itemStyle: { color: ACCENT },
        },
      ],
    }),
    [early, earlyLine, group.hr_max, group.hr_min, locale, recent, recentLine, t, units],
  );

  if (!points.length) return null;

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      opts={chartOpts}
      style={{ height: 300, width: "100%" }}
      notMerge
      lazyUpdate
    />
  );
}

export function ComparisonSplitsChart({ splits }: { splits: ComparisonSplit[] }) {
  const { units, t } = useI18n();
  const labels = splits.map((split) => `${split.index}`);
  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 450,
      grid: { left: 8, right: 14, top: 22, bottom: 6, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: PANEL,
        borderColor: "rgba(255,255,255,0.09)",
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: "#eef5f0", fontFamily: "Manrope Variable", fontSize: 12 },
        formatter: (params: unknown) => {
          const list = (Array.isArray(params) ? params : [params]) as TooltipItem[];
          const index = list[0]?.dataIndex ?? 0;
          const split = splits[index];
          if (!split) return "";
          return `<div style="font-weight:700;margin-bottom:4px">${t("compare.chart.km", {
            km: split.index,
          })}</div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="width:7px;height:7px;border-radius:50%;background:${ACCENT};display:inline-block"></span>
              <span style="color:#a9b5ae">${t("compare.chart.left")}</span>
              <strong style="margin-left:auto">${formatPace(split.left_pace_s_per_km, units)}</strong>
            </div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
              <span style="width:7px;height:7px;border-radius:50%;background:${ORANGE};display:inline-block"></span>
              <span style="color:#a9b5ae">${t("compare.chart.right")}</span>
              <strong style="margin-left:auto">${formatPace(split.right_pace_s_per_km, units)}</strong>
            </div>`;
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        name: t("compare.chart.kmAxis"),
        nameTextStyle: { color: TEXT, fontSize: 10 },
        axisLine: { lineStyle: { color: GRID } },
        axisTick: { show: false },
        axisLabel: {
          color: TEXT,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
        },
      },
      yAxis: {
        type: "value",
        inverse: true,
        scale: true,
        axisLabel: {
          color: TEXT,
          fontSize: 10,
          fontFamily: "JetBrains Mono Variable",
          formatter: (value: number) => formatPace(value, units, { suffix: false }),
        },
        splitLine: { lineStyle: { color: GRID, type: "dashed" } },
      },
      series: [
        {
          name: t("compare.chart.left"),
          type: "line",
          data: splits.map((split) => split.left_pace_s_per_km),
          showSymbol: true,
          symbolSize: 4,
          connectNulls: true,
          lineStyle: { color: ACCENT, width: 2 },
          itemStyle: { color: ACCENT },
        },
        {
          name: t("compare.chart.right"),
          type: "line",
          data: splits.map((split) => split.right_pace_s_per_km),
          showSymbol: true,
          symbolSize: 4,
          connectNulls: true,
          lineStyle: { color: ORANGE, width: 2 },
          itemStyle: { color: ORANGE },
        },
      ],
    }),
    [labels, splits, t, units],
  );

  if (splits.length < 2) return null;

  return (
    <ReactECharts
      echarts={echarts}
      option={option}
      opts={chartOpts}
      style={{ height: 240, width: "100%" }}
      notMerge
      lazyUpdate
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
