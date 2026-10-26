import { useMemo } from "react";
import { BarChart, LineChart } from "echarts/charts";
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
import { BarChart3, HeartPulse } from "lucide-react";

import type {
  AnalysisLoad,
  GarminMetricPoint,
  PerformanceSnapshot,
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
const PANEL = "rgba(15, 21, 18, 0.94)";

const chartOpts = { renderer: "canvas" as const };

echarts.use([
  BarChart,
  LineChart,
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
