import type { LucideIcon } from "lucide-react";
import {
  Activity,
  CircleAlert,
  HeartPulse,
  Repeat2,
  Target,
  TrendingUp,
  Zap,
} from "lucide-react";

import type {
  AnalysisDimension,
  AnalysisIntensity,
  AnalysisLoad,
} from "@/api/client";
import {
  Badge,
  Card,
  ProgressBar,
  SectionHeading,
} from "@/components/ui";
import { useI18n, type Locale, type MessageKey, type Units } from "@/i18n";
import { cn } from "@/lib/cn";
import { formatDistance, formatNumber, formatPercent } from "@/lib/format";

type BadgeTone = "neutral" | "accent" | "success" | "warning" | "danger" | "info";

export const DIMENSION_META: Record<
  string,
  { label: MessageKey; icon: LucideIcon; color: string; weight: number }
> = {
  volume: {
    label: "diagnostics.dimension.volume",
    icon: TrendingUp,
    color: "var(--accent)",
    weight: 15,
  },
  consistency: {
    label: "diagnostics.dimension.consistency",
    icon: Repeat2,
    color: "var(--blue)",
    weight: 15,
  },
  intensity: {
    label: "diagnostics.dimension.intensity",
    icon: Zap,
    color: "var(--orange)",
    weight: 20,
  },
  load: {
    label: "diagnostics.dimension.load",
    icon: Activity,
    color: "#e3c56b",
    weight: 20,
  },
  recovery: {
    label: "diagnostics.dimension.recovery",
    icon: HeartPulse,
    color: "var(--violet)",
    weight: 15,
  },
  specificity: {
    label: "diagnostics.dimension.specificity",
    icon: Target,
    color: "var(--red)",
    weight: 15,
  },
};

const STATUS_KEYS: Record<string, MessageKey> = {
  strong: "analysis.status.strong",
  ok: "analysis.status.ok",
  watch: "analysis.status.watch",
  risk: "analysis.status.risk",
  unknown: "analysis.status.unknown",
  insufficient: "analysis.status.insufficient",
};

const STATUS_TONES: Record<string, BadgeTone> = {
  strong: "success",
  ok: "accent",
  watch: "warning",
  risk: "danger",
  unknown: "neutral",
  insufficient: "neutral",
};

const CONFIDENCE_KEYS: Record<string, MessageKey> = {
  high: "analysis.confidence.high",
  medium: "analysis.confidence.medium",
  low: "analysis.confidence.low",
};

const REASON_KEYS: Record<string, MessageKey> = {
  insufficient_volume: "analysis.reason.insufficient_volume",
  no_recent_volume: "analysis.reason.no_recent_volume",
  low_volume: "analysis.reason.low_volume",
  volume_ok: "analysis.reason.volume_ok",
  ramp_fast: "analysis.reason.ramp_fast",
  volume_declining: "analysis.reason.volume_declining",
  volume_stable: "analysis.reason.volume_stable",
  starting_block: "analysis.reason.starting_block",
  insufficient_consistency: "analysis.reason.insufficient_consistency",
  consistent_weeks: "analysis.reason.consistent_weeks",
  missed_weeks: "analysis.reason.missed_weeks",
  regular_frequency: "analysis.reason.regular_frequency",
  few_runs: "analysis.reason.few_runs",
  long_gap: "analysis.reason.long_gap",
  acceptable_consistency: "analysis.reason.acceptable_consistency",
  no_intensity_data: "analysis.reason.no_intensity_data",
  too_much_easy: "analysis.reason.too_much_easy",
  too_much_hard: "analysis.reason.too_much_hard",
  gray_zone: "analysis.reason.gray_zone",
  little_easy: "analysis.reason.little_easy",
  little_hard: "analysis.reason.little_hard",
  balanced: "analysis.reason.balanced",
  acceptable_distribution: "analysis.reason.acceptable_distribution",
  no_load_data: "analysis.reason.no_load_data",
  load_spike: "analysis.reason.load_spike",
  load_rising: "analysis.reason.load_rising",
  load_low: "analysis.reason.load_low",
  load_falling: "analysis.reason.load_falling",
  load_balanced: "analysis.reason.load_balanced",
  ramp_drop: "analysis.reason.ramp_drop",
  acceptable_load: "analysis.reason.acceptable_load",
  insufficient_recovery: "analysis.reason.insufficient_recovery",
  few_rest_days: "analysis.reason.few_rest_days",
  rest_ok: "analysis.reason.rest_ok",
  back_to_back_hard: "analysis.reason.back_to_back_hard",
  long_streak: "analysis.reason.long_streak",
  insufficient_specificity: "analysis.reason.insufficient_specificity",
  long_run_ok: "analysis.reason.long_run_ok",
  long_run_short: "analysis.reason.long_run_short",
  no_long_run: "analysis.reason.no_long_run",
  quality_ok: "analysis.reason.quality_ok",
  little_quality: "analysis.reason.little_quality",
  no_quality: "analysis.reason.no_quality",
  race_specific: "analysis.reason.race_specific",
  no_goal_effort: "analysis.reason.no_goal_effort",
  no_goal: "analysis.reason.no_goal",
};

const WARNING_KEYS: Record<string, MessageKey> = {
  no_activities: "analysis.warning.no_activities",
  few_activities: "analysis.warning.few_activities",
  no_anchor: "analysis.warning.no_anchor",
  no_hr: "analysis.warning.no_hr",
  no_goal: "analysis.warning.no_goal",
  no_readiness: "analysis.warning.no_readiness",
  short_history: "analysis.warning.short_history",
  stale_data: "analysis.warning.stale_data",
  trail_heavy: "analysis.warning.trail_heavy",
};

const INTENSITY_META = [
  { key: "easy", label: "analysis.intensity.easy", color: "var(--accent)" },
  { key: "moderate", label: "analysis.intensity.moderate", color: "var(--orange)" },
  { key: "hard", label: "analysis.intensity.hard", color: "var(--red)" },
] as const satisfies ReadonlyArray<{ key: string; label: MessageKey; color: string }>;

export function AnalysisWarnings({ warnings }: { warnings?: string[] }) {
  const { t } = useI18n();
  if (!warnings?.length) return null;

  return (
    <div className="analysis-warnings" role="status">
      <span className="analysis-warnings__icon">
        <CircleAlert size={16} aria-hidden="true" />
      </span>
      <div className="analysis-warnings__list">
        {warnings.map((warning) => (
          <Badge key={warning} tone="warning" dot>
            {WARNING_KEYS[warning] ? t(WARNING_KEYS[warning]) : warning}
          </Badge>
        ))}
      </div>
    </div>
  );
}

export function AnalysisStatusBadge({ status }: { status: string }) {
  const { t } = useI18n();
  return (
    <Badge tone={STATUS_TONES[status] ?? "neutral"} dot>
      {STATUS_KEYS[status] ? t(STATUS_KEYS[status]) : status}
    </Badge>
  );
}

export function AnalysisConfidence({
  confidence,
  score,
}: {
  confidence: string;
  score: number;
}) {
  const { t } = useI18n();
  const tone: BadgeTone =
    confidence === "high" ? "success" : confidence === "medium" ? "warning" : "danger";
  const label = CONFIDENCE_KEYS[confidence] ? t(CONFIDENCE_KEYS[confidence]) : confidence;
  return (
    <Badge tone={tone}>
      {label} · {Math.round(score * 100)}%
    </Badge>
  );
}

export function ReasonChips({
  reasons,
  className,
}: {
  reasons?: string[];
  className?: string;
}) {
  const { t } = useI18n();
  if (!reasons?.length) return null;

  return (
    <div className={cn("reason-list", className)}>
      {reasons.map((reason) => (
        <span className="reason-chip" key={reason}>
          {REASON_KEYS[reason] ? t(REASON_KEYS[reason]) : reason}
        </span>
      ))}
    </div>
  );
}

export function DimensionCard({
  dimension,
  locale,
  units,
}: {
  dimension: AnalysisDimension;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  const meta = DIMENSION_META[dimension.key];
  const Icon = meta?.icon ?? Activity;
  const label = meta ? t(meta.label) : dimension.key;
  const score = dimension.score ?? null;
  const metrics = dimensionMetrics(dimension, t, locale, units);

  return (
    <Card
      className="dimension-card"
      style={{ ["--dimension-accent" as string]: meta?.color ?? "var(--accent)" }}
    >
      <div className="dimension-card__head">
        <div className="dimension-card__name">
          <span className="dimension-card__icon">
            <Icon size={16} aria-hidden="true" />
          </span>
          <div>
            <strong>{label}</strong>
            <small>
              {meta ? t("diagnostics.dimensions.weight", { weight: meta.weight }) : null}
            </small>
          </div>
        </div>
        <AnalysisStatusBadge status={dimension.status} />
      </div>

      <div className="dimension-card__score">
        {score === null ? (
          <strong className="is-empty">—</strong>
        ) : (
          <strong>{Math.round(score)}</strong>
        )}
        <span>/ 100</span>
        <AnalysisConfidence
          confidence={dimension.confidence}
          score={dimension.confidence_score}
        />
      </div>

      {score === null ? (
        <p className="dimension-card__empty">{t("diagnostics.dimensions.noData")}</p>
      ) : (
        <ProgressBar value={score} tone={scoreTone(score)} />
      )}

      {metrics.length ? (
        <div className="dimension-metrics">
          {metrics.map((metric) => (
            <div className="dimension-metric" key={metric.label}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </div>
          ))}
        </div>
      ) : null}

      <ReasonChips reasons={dimension.reasons} />
    </Card>
  );
}

export function IntensityPanel({ intensity }: { intensity: AnalysisIntensity }) {
  const { t, locale } = useI18n();
  const targets = new Map(intensity.targets.map((target) => [target.key, target]));
  const classified = intensity.classified_sessions;
  const buckets = INTENSITY_META.map((meta) => ({
    ...meta,
    bucket: intensity.buckets.find((bucket) => bucket.key === meta.key),
    target: targets.get(meta.key),
  }));

  return (
    <div className="intensity-panel">
      <SectionHeading
        title={t("analysis.intensity.title")}
        subtitle={t("analysis.intensity.subtitle")}
        icon={Zap}
        action={<AnalysisStatusBadge status={intensity.status} />}
      />

      {classified === 0 ? (
        <p className="analysis-empty">{t("analysis.intensity.empty")}</p>
      ) : (
        <>
          <div className="intensity-bar" role="img" aria-label={t("analysis.intensity.title")}>
            {buckets.map(({ key, color, bucket }) =>
              bucket && bucket.share > 0 ? (
                <span
                  key={key}
                  className="intensity-bar__segment"
                  style={{ flexGrow: bucket.share, background: color }}
                />
              ) : null,
            )}
          </div>

          <div className="intensity-rows">
            {buckets.map(({ key, label, color, bucket, target }) => (
              <div className="intensity-row" key={key}>
                <span
                  className="intensity-row__dot"
                  style={{ background: color }}
                  aria-hidden="true"
                />
                <span className="intensity-row__label">{t(label)}</span>
                {target ? (
                  <span className="intensity-row__target">
                    {t("analysis.intensity.target")} {Math.round(target.low * 100)}–
                    {Math.round(target.high * 100)}%
                  </span>
                ) : null}
                <strong>{formatPercent((bucket?.share ?? 0) * 100, locale)}</strong>
                <small>
                  {t("analysis.intensity.sessions", {
                    count: formatNumber(bucket?.sessions ?? 0, locale),
                  })}
                </small>
              </div>
            ))}
          </div>

          <div className="intensity-meta">
            <span>
              {t("analysis.intensity.classified", {
                count: formatNumber(classified, locale),
              })}
            </span>
            {intensity.unknown_sessions > 0 ? (
              <span>
                {t("analysis.intensity.unknown", {
                  count: formatNumber(intensity.unknown_sessions, locale),
                })}
              </span>
            ) : null}
          </div>
        </>
      )}

      <ReasonChips reasons={intensity.reasons} />
      <p className="analysis-note">{t("analysis.intensity.note")}</p>
    </div>
  );
}

export function LoadPanel({ load }: { load: AnalysisLoad }) {
  const { t, locale } = useI18n();
  const ratio = load.ratio ?? null;
  const ratioTone =
    ratio === null ? "is-empty" : ratio > 1.3 || ratio < 0.8 ? "is-off" : "is-ok";

  return (
    <div className="load-panel">
      <SectionHeading
        title={t("analysis.load.title")}
        subtitle={t("analysis.load.subtitle")}
        icon={Activity}
        action={<AnalysisStatusBadge status={load.status} />}
      />

      {ratio === null ? (
        <p className="analysis-empty">{t("analysis.load.empty")}</p>
      ) : (
        <div className="load-summary">
          <div className={cn("load-ratio", ratioTone)}>
            <span>{t("analysis.load.ratio")}</span>
            <strong>{formatNumber(ratio, locale, 2)}</strong>
            <small>{t("analysis.load.target")}</small>
          </div>
          <div className="load-metrics">
            <LoadMetric
              label={t("analysis.load.acute")}
              value={formatNumber(load.acute_7d, locale)}
            />
            <LoadMetric
              label={t("analysis.load.chronic")}
              value={formatNumber(load.chronic_weekly, locale)}
            />
            <LoadMetric
              label={t("analysis.load.ramp")}
              value={formatSignedPercent(load.ramp_pct, locale)}
            />
          </div>
        </div>
      )}

      <ReasonChips reasons={load.reasons} />
      <p className="analysis-note">{t("analysis.load.note")}</p>
    </div>
  );
}

export function AnalysisMethodCard({
  title,
  subtitle,
  items,
}: {
  title: string;
  subtitle: string;
  items: Array<{ icon: LucideIcon; title: string; body: string }>;
}) {
  const { t } = useI18n();
  return (
    <Card className="panel analysis-method">
      <SectionHeading title={title} subtitle={subtitle} icon={CircleAlert} />
      <div className="method-grid">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <div className="method-item" key={item.title}>
              <span className="method-item__icon">
                <Icon size={17} aria-hidden="true" />
              </span>
              <div>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </div>
            </div>
          );
        })}
      </div>
      <p className="analysis-note">{t("analysis.notMedical")}</p>
    </Card>
  );
}

function LoadMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="load-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function dimensionMetrics(
  dimension: AnalysisDimension,
  t: (key: MessageKey) => string,
  locale: Locale,
  units: Units,
): Array<{ label: string; value: string }> {
  const metrics = dimension.metrics ?? {};

  switch (dimension.key) {
    case "volume":
      return [
        {
          label: t("diagnostics.metric.weeklyAvg"),
          value: formatDistance(metrics.weekly_avg_m, units, locale, { digits: 1 }),
        },
        {
          label: t("diagnostics.metric.trend28"),
          value: formatSignedPercent(metrics.trend_pct, locale),
        },
        {
          label: t("diagnostics.metric.longest28"),
          value: formatDistance(metrics.longest_28_m, units, locale, { digits: 1 }),
        },
      ];
    case "consistency":
      return [
        {
          label: t("diagnostics.metric.activeWeeks"),
          value: `${formatNumber(metrics.active_weeks, locale)} / ${formatNumber(
            metrics.weeks,
            locale,
          )}`,
        },
        {
          label: t("diagnostics.metric.runsPerWeek"),
          value: formatNumber(metrics.runs_per_week, locale, 1),
        },
        {
          label: t("diagnostics.metric.longestGap"),
          value: `${formatNumber(metrics.longest_gap_days, locale)} ${t("common.days")}`,
        },
      ];
    case "intensity":
      return [
        {
          label: t("analysis.intensity.easy"),
          value: formatPercent((metrics.easy_share ?? 0) * 100, locale),
        },
        {
          label: t("analysis.intensity.moderate"),
          value: formatPercent((metrics.moderate_share ?? 0) * 100, locale),
        },
        {
          label: t("analysis.intensity.hard"),
          value: formatPercent((metrics.hard_share ?? 0) * 100, locale),
        },
      ];
    case "load":
      return [
        {
          label: t("diagnostics.metric.ratio"),
          value: formatNumber(metrics.ratio, locale, 2),
        },
        {
          label: t("diagnostics.metric.acute"),
          value: formatNumber(metrics.acute_7d, locale),
        },
        {
          label: t("diagnostics.metric.ramp"),
          value: formatSignedPercent(metrics.ramp_pct, locale),
        },
      ];
    case "recovery":
      return [
        {
          label: t("diagnostics.metric.restDays"),
          value: formatNumber(metrics.rest_days_per_week, locale, 1),
        },
        {
          label: t("diagnostics.metric.streak"),
          value: `${formatNumber(metrics.longest_streak, locale)} ${t("common.days")}`,
        },
        {
          label: t("diagnostics.metric.readiness"),
          value:
            metrics.readiness === undefined
              ? "—"
              : formatNumber(metrics.readiness, locale),
        },
      ];
    case "specificity":
      return [
        {
          label: t("diagnostics.metric.longest28"),
          value: formatDistance(metrics.longest_28_m, units, locale, { digits: 1 }),
        },
        {
          label: t("diagnostics.metric.targetLong"),
          value: formatDistance(metrics.target_long_m, units, locale, { digits: 1 }),
        },
        {
          label: t("diagnostics.metric.hardSessions"),
          value: formatNumber(metrics.hard_sessions, locale),
        },
      ];
    default:
      return [];
  }
}

function formatSignedPercent(
  value: number | null | undefined,
  locale: Locale,
): string {
  if (value === null || value === undefined) return "—";
  const rounded = formatNumber(value, locale, 1);
  return value > 0 ? `+${rounded}%` : `${rounded}%`;
}

function scoreTone(score: number): "accent" | "warning" | "danger" {
  if (score >= 70) return "accent";
  if (score >= 45) return "warning";
  return "danger";
}
