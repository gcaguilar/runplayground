import { useMemo, useState } from "react";
import { Link, useSearch } from "@tanstack/react-router";
import {
  ArrowLeftRight,
  ArrowRight,
  CircleAlert,
  Gauge,
  Info,
  RefreshCw,
  Target,
} from "lucide-react";

import type {
  Activity,
  ComparisonInsight,
  ComparisonMetric,
  ComparisonSide,
  ComparisonView,
} from "@/api/client";
import { useActivities, useComparison } from "@/api/queries";
import { ComparisonSplitsChart } from "@/components/Charts";
import { SportGlyph } from "@/components/SportGlyph";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  ProgressBar,
  SectionHeading,
  Skeleton,
} from "@/components/ui";
import { useI18n, type Locale, type MessageKey, type Units } from "@/i18n";
import { cn } from "@/lib/cn";
import {
  formatClock,
  formatDate,
  formatDistance,
  formatDuration,
  formatElevation,
  formatNumber,
  formatPace,
  sportKey,
} from "@/lib/format";

const STATUS_KEYS: Record<string, MessageKey> = {
  comparable: "compare.status.comparable",
  limited: "compare.status.limited",
  not_comparable: "compare.status.not_comparable",
};

const STATUS_TONE: Record<string, "success" | "warning" | "danger"> = {
  comparable: "success",
  limited: "warning",
  not_comparable: "danger",
};

const REASON_KEYS: Record<string, MessageKey> = {
  different_sport: "compare.reasons.different_sport",
  different_terrain: "compare.reasons.different_terrain",
  distance_mismatch: "compare.reasons.distance_mismatch",
  distance_gap: "compare.reasons.distance_gap",
  duration_gap: "compare.reasons.duration_gap",
  terrain_gap: "compare.reasons.terrain_gap",
  terrain_small_gap: "compare.reasons.terrain_small_gap",
};

const WARNING_KEYS: Record<string, MessageKey> = {
  missing_streams: "compare.warning.missing_streams",
  missing_hr: "compare.warning.missing_hr",
  missing_cadence: "compare.warning.missing_cadence",
  race_vs_training: "compare.warning.race_vs_training",
  no_splits: "compare.warning.no_splits",
};

const METRIC_KEYS: Record<string, MessageKey> = {
  pace_s_per_km: "compare.metric.pace_s_per_km",
  avg_hr: "compare.metric.avg_hr",
  max_hr: "compare.metric.max_hr",
  cadence_spm: "compare.metric.cadence_spm",
  power_w: "compare.metric.power_w",
  elevation_gain_m: "compare.metric.elevation_gain_m",
  training_effect: "compare.metric.training_effect",
  training_load: "compare.metric.training_load",
};

const INSIGHT_KEYS: Record<string, MessageKey> = {
  similar_effort: "compare.insight.similar_effort",
  faster_same_effort: "compare.insight.faster_same_effort",
  faster_higher_effort: "compare.insight.faster_higher_effort",
  slower_same_effort: "compare.insight.slower_same_effort",
  slower_higher_effort: "compare.insight.slower_higher_effort",
  slower_lower_effort: "compare.insight.slower_lower_effort",
  similar_pace_lower_hr: "compare.insight.similar_pace_lower_hr",
  longer_session: "compare.insight.longer_session",
  terrain_difference: "compare.insight.terrain_difference",
  no_clear_difference: "compare.insight.no_clear_difference",
  comparison_not_comparable: "compare.insight.comparison_not_comparable",
};

const NOTE_KEYS: Record<string, MessageKey> = {
  summary_metrics_only: "compare.notes.summary_metrics_only",
  conditions_not_controlled: "compare.notes.conditions_not_controlled",
  association_not_causation: "compare.notes.association_not_causation",
  not_medical_advice: "compare.notes.not_medical_advice",
  no_split_streams: "compare.notes.no_split_streams",
};

function secondaryText(activity: Activity, locale: Locale, units: Units): string {
  return `${formatDate(activity.start_time_utc, locale)} · ${formatDistance(
    activity.distance_m,
    units,
    locale,
    { digits: 1 },
  )}`;
}

function metricValue(
  metric: ComparisonMetric,
  value: number | null | undefined,
  units: Units,
  locale: Locale,
): string {
  if (value === null || value === undefined) return "—";
  if (metric.key === "pace_s_per_km") return formatPace(value, units);
  if (metric.key === "avg_hr" || metric.key === "max_hr") {
    return `${formatNumber(value, locale)} bpm`;
  }
  if (metric.key === "cadence_spm") return `${formatNumber(value, locale)} spm`;
  if (metric.key === "power_w") return `${formatNumber(value, locale)} W`;
  if (metric.key === "elevation_gain_m") return formatElevation(value, units, locale);
  return formatNumber(value, locale, 1);
}

function deltaValue(
  metric: ComparisonMetric,
  units: Units,
  locale: Locale,
): string {
  if (metric.delta === null || metric.delta === undefined) return "—";
  const sign = metric.delta > 0 ? "+" : metric.delta < 0 ? "−" : "";
  const absolute = Math.abs(metric.delta);
  if (metric.key === "pace_s_per_km") return `${sign}${formatClock(absolute)}`;
  if (metric.key === "avg_hr" || metric.key === "max_hr") {
    return `${sign}${formatNumber(absolute, locale)} bpm`;
  }
  if (metric.key === "cadence_spm") return `${sign}${formatNumber(absolute, locale)} spm`;
  if (metric.key === "power_w") return `${sign}${formatNumber(absolute, locale)} W`;
  if (metric.key === "elevation_gain_m") {
    return `${sign}${formatElevation(absolute, units, locale)}`;
  }
  return `${sign}${formatNumber(absolute, locale, 1)}`;
}

function sidePace(side: ComparisonSide, units: Units): string {
  return formatPace(side.pace_s_per_km, units);
}

export function ComparePage() {
  const { t, locale, units } = useI18n();
  const search = useSearch({ strict: false }) as { left?: number };
  const activities = useActivities({ limit: 100, sort: "date_desc" });
  const items = activities.data?.items ?? [];
  const [leftChoice, setLeftChoice] = useState<string | null>(
    search.left ? String(search.left) : null,
  );
  const [rightChoice, setRightChoice] = useState<string | null>(null);

  const effectiveLeft = useMemo(() => {
    if (leftChoice && items.some((item) => String(item.id) === leftChoice)) {
      return leftChoice;
    }
    return items[0] ? String(items[0].id) : undefined;
  }, [items, leftChoice]);

  const effectiveRight = useMemo(() => {
    if (
      rightChoice &&
      rightChoice !== effectiveLeft &&
      items.some((item) => String(item.id) === rightChoice)
    ) {
      return rightChoice;
    }
    return items.find((item) => String(item.id) !== effectiveLeft)
      ? String(items.find((item) => String(item.id) !== effectiveLeft)?.id)
      : undefined;
  }, [effectiveLeft, items, rightChoice]);

  const comparison = useComparison(effectiveLeft, effectiveRight);

  const swap = () => {
    setLeftChoice(effectiveRight ?? null);
    setRightChoice(effectiveLeft ?? null);
  };

  if (activities.isLoading) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow={t("compare.page.eyebrow")} title={t("compare.page.title")} />
        <div className="analysis-skeleton">
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
        </div>
      </div>
    );
  }

  if (activities.isError) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow={t("compare.page.eyebrow")}
          title={t("compare.page.title")}
          description={t("compare.page.subtitle")}
        />
        <ErrorState
          message={
            activities.error instanceof Error ? activities.error.message : t("compare.error")
          }
          onRetry={() => void activities.refetch()}
        />
      </div>
    );
  }

  return (
    <div className="page-stack compare-page">
      <PageHeader
        eyebrow={t("compare.page.eyebrow")}
        title={t("compare.page.title")}
        description={t("compare.page.subtitle")}
        actions={
          <div className="compare-actions">
            <Button
              variant="secondary"
              size="sm"
              loading={comparison.isFetching}
              onClick={() => void comparison.refetch()}
            >
              <RefreshCw size={15} aria-hidden="true" />
              {t("compare.actions.refresh")}
            </Button>
            <Link to="/activities" className="button button--secondary button--sm">
              <ArrowRight size={15} aria-hidden="true" />
              {t("compare.actions.activities")}
            </Link>
          </div>
        }
      />

      {items.length < 2 ? (
        <Card className="panel">
          <EmptyState
            icon={ArrowLeftRight}
            title={t("compare.empty.title")}
            description={t("compare.empty.body")}
            action={
              <Link to="/imports" className="button button--primary button--sm">
                <ArrowRight size={15} aria-hidden="true" />
                {t("compare.empty.action")}
              </Link>
            }
          />
        </Card>
      ) : (
        <>
          <Card className="panel compare-selector">
            <SectionHeading
              title={t("compare.select.title")}
              icon={ArrowLeftRight}
              action={
                <Button variant="ghost" size="sm" onClick={swap}>
                  <ArrowLeftRight size={14} aria-hidden="true" />
                  {t("compare.select.swap")}
                </Button>
              }
            />
            <div className="compare-selector__grid">
              <label className="select-field">
                <span>{t("compare.select.left")}</span>
                <select
                  value={effectiveLeft ?? ""}
                  onChange={(event) => setLeftChoice(event.target.value)}
                >
                  {items.map((activity) => (
                    <option key={activity.id} value={activity.id}>
                      {activity.name || t(sportKey(activity.sub_sport || activity.sport))} ·{" "}
                      {secondaryText(activity, locale, units)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="select-field">
                <span>{t("compare.select.right")}</span>
                <select
                  value={effectiveRight ?? ""}
                  onChange={(event) => setRightChoice(event.target.value)}
                >
                  {items
                    .filter((activity) => String(activity.id) !== effectiveLeft)
                    .map((activity) => (
                      <option key={activity.id} value={activity.id}>
                        {activity.name || t(sportKey(activity.sub_sport || activity.sport))} ·{" "}
                        {secondaryText(activity, locale, units)}
                      </option>
                    ))}
                </select>
              </label>
            </div>
          </Card>

          {comparison.isLoading ? (
            <div className="analysis-skeleton">
              <Skeleton className="skeleton--panel" />
              <Skeleton className="skeleton--panel" />
            </div>
          ) : comparison.isError || !comparison.data ? (
            <ErrorState
              message={
                comparison.error instanceof Error
                  ? comparison.error.message
                  : t("compare.error")
              }
              onRetry={() => void comparison.refetch()}
            />
          ) : (
            <ComparisonResult data={comparison.data} />
          )}
        </>
      )}
    </div>
  );
}

function ComparisonResult({ data }: { data: ComparisonView }) {
  const { t, locale, units } = useI18n();
  const statusTone = STATUS_TONE[data.status] ?? "warning";
  const reasons = data.reasons ?? [];
  const warnings = data.warnings ?? [];
  const metrics = data.metrics ?? [];
  const insights = data.insights ?? [];
  const splits = data.splits ?? [];
  const notes = data.notes ?? [];
  return (
    <>
      <Card className="panel compare-status">
        <div className="compare-status__head">
          <div>
            <span className="eyebrow">{t("compare.score")}</span>
            <strong>{Math.round(data.comparability * 100)}%</strong>
          </div>
          <Badge tone={statusTone}>{t(STATUS_KEYS[data.status] ?? "compare.status.limited")}</Badge>
        </div>
        <ProgressBar
          value={data.comparability * 100}
          tone={statusTone === "success" ? "accent" : statusTone === "danger" ? "danger" : "warning"}
        />
        {reasons.length || warnings.length ? (
          <div className="compare-status__tags">
            {reasons.map((reason) => (
              <Badge key={reason} tone="warning" dot>
                {REASON_KEYS[reason] ? t(REASON_KEYS[reason]) : reason}
              </Badge>
            ))}
            {warnings.map((warning) => (
              <Badge key={warning} tone="neutral" dot>
                {WARNING_KEYS[warning] ? t(WARNING_KEYS[warning]) : warning}
              </Badge>
            ))}
          </div>
        ) : null}
      </Card>

      <section className="compare-sides">
        <SideCard side={data.left} label={t("compare.metric.left")} units={units} locale={locale} />
        <SideCard side={data.right} label={t("compare.metric.right")} units={units} locale={locale} />
      </section>

      <Card className="panel compare-metrics">
        <SectionHeading title={t("compare.metric.title")} icon={Gauge} />
        <div className="compare-table">
          <div className="compare-table__head">
            <span>{t("compare.metric.metric")}</span>
            <span>{t("compare.metric.left")}</span>
            <span>{t("compare.metric.right")}</span>
            <span>{t("compare.metric.delta")}</span>
            <span />
          </div>
          {metrics.map((metric) => (
            <div className="compare-table__row" key={metric.key}>
              <span>{t(METRIC_KEYS[metric.key] ?? "compare.metric.metric")}</span>
              <strong>{metricValue(metric, metric.left, units, locale)}</strong>
              <strong>{metricValue(metric, metric.right, units, locale)}</strong>
              <span className="compare-table__delta">{deltaValue(metric, units, locale)}</span>
              <BetterBadge better={metric.better} />
            </div>
          ))}
        </div>
      </Card>

      <Card className="panel compare-insights">
        <SectionHeading
          title={t("compare.insight.title")}
          subtitle={t("compare.insight.subtitle")}
          icon={Target}
        />
        <div className="compare-insights__list">
          {insights.map((insight) => (
            <div className="compare-insight" key={`${insight.key}-${insight.value ?? ""}`}>
              <span className="compare-insight__icon">
                <Info size={16} aria-hidden="true" />
              </span>
              <p>{insightText(insight, units, locale, t)}</p>
            </div>
          ))}
        </div>
      </Card>

      <Card className="panel compare-splits">
        <SectionHeading
          title={t("compare.splits.title")}
          subtitle={t("compare.splits.subtitle")}
          icon={Gauge}
        />
        {splits.length ? (
          <>
            <ComparisonSplitsChart splits={splits} />
            <div className="compare-splits__foot">
              <span>{t("compare.chart.left")}</span>
              <span>{t("compare.chart.right")}</span>
            </div>
          </>
        ) : (
          <EmptyState compact icon={Gauge} title={t("compare.splits.empty")} />
        )}
      </Card>

      <Card className="panel compare-notes">
        <div className="compare-notes__head">
          <CircleAlert size={16} aria-hidden="true" />
          <strong>{t("compare.notes.title")}</strong>
        </div>
        <ul>
          {notes
            .filter((note) => NOTE_KEYS[note])
            .map((note) => (
              <li key={note}>{t(NOTE_KEYS[note])}</li>
            ))}
        </ul>
      </Card>
    </>
  );
}

function SideCard({
  side,
  label,
  units,
  locale,
}: {
  side: ComparisonSide;
  label: string;
  units: Units;
  locale: Locale;
}) {
  const { t } = useI18n();
  return (
    <Card className="panel compare-side">
      <div className="compare-side__head">
        <Badge tone="info">{label}</Badge>
        <Badge tone={side.is_race ? "accent" : "neutral"}>
          {side.is_race ? t("compare.side.race") : t("compare.side.training")}
        </Badge>
      </div>
      <div className="compare-side__identity">
        <SportGlyph sport={side.sub_sport || side.sport} />
        <div>
          <strong>{side.name || t(sportKey(side.sub_sport || side.sport))}</strong>
          <small>{formatDate(side.start_time_utc, locale)}</small>
        </div>
      </div>
      <div className="compare-side__stats">
        <SideMetric label={t("compare.side.distance")} value={formatDistance(side.distance_m, units, locale, { digits: 2 })} />
        <SideMetric label={t("compare.side.duration")} value={formatDuration(side.duration_s, locale)} />
        <SideMetric label={t("compare.side.pace")} value={sidePace(side, units)} accent />
        <SideMetric label={t("compare.side.hr")} value={side.avg_hr ? `${formatNumber(side.avg_hr, locale)} bpm` : "—"} />
        <SideMetric label={t("compare.side.cadence")} value={side.cadence_spm ? `${formatNumber(side.cadence_spm, locale)} spm` : "—"} />
        <SideMetric label={t("compare.side.elevation")} value={formatElevation(side.elevation_gain_m, units, locale)} />
      </div>
    </Card>
  );
}

function SideMetric({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="compare-side__stat">
      <span>{label}</span>
      <strong className={cn(accent && "is-accent")}>{value}</strong>
    </div>
  );
}

function BetterBadge({ better }: { better: string }) {
  const { t } = useI18n();
  if (better === "unknown") return <span className="compare-better is-muted">—</span>;
  const key =
    better === "left"
      ? "compare.metric.better.left"
      : better === "right"
        ? "compare.metric.better.right"
        : "compare.metric.better.similar";
  return (
    <span className={cn("compare-better", `is-${better}`)}>{t(key)}</span>
  );
}

function insightText(
  insight: ComparisonInsight,
  units: Units,
  locale: Locale,
  t: (key: MessageKey, values?: Record<string, string | number>) => string,
): string {
  const key = INSIGHT_KEYS[insight.key];
  if (!key) return insight.key;
  const value = insight.value;
  const params: Record<string, string | number> = {};
  if (value !== null && value !== undefined) {
    if (insight.key === "longer_session") {
      params.value = formatDistance(value, units, locale, { digits: 2 });
    } else if (insight.key === "terrain_difference") {
      params.value = formatNumber(value, locale, 1);
    } else if (insight.key === "similar_pace_lower_hr") {
      params.value = formatNumber(value, locale);
    } else {
      params.value = formatClock(value);
    }
  }
  if (insight.params?.hr_delta !== undefined) {
    params.hr = formatNumber(Number(insight.params.hr_delta), locale);
  }
  return t(key, params);
}
