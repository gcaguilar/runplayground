import { useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  Activity,
  ArrowRight,
  Battery,
  CircleAlert,
  HeartPulse,
  Info,
  Moon,
  RefreshCw,
  Scale,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

import type { RecoveryMetric } from "@/api/client";
import { useRecovery } from "@/api/queries";
import { RecoveryTrendChart } from "@/components/Charts";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  SectionHeading,
  Skeleton,
} from "@/components/ui";
import { useI18n, type Locale, type MessageKey, type Units } from "@/i18n";
import { cn } from "@/lib/cn";
import {
  formatDate,
  formatRecoveryDelta,
  formatRecoveryValue,
} from "@/lib/format";

const WINDOWS = [30, 90, 180] as const;

const METRIC_META: Record<string, { label: MessageKey; icon: LucideIcon }> = {
  sleep_duration: { label: "recovery.metric.sleep_duration", icon: Moon },
  sleep_score: { label: "recovery.metric.sleep_score", icon: Sparkles },
  hrv: { label: "recovery.metric.hrv", icon: HeartPulse },
  resting_hr: { label: "recovery.metric.resting_hr", icon: Activity },
  body_battery: { label: "recovery.metric.body_battery", icon: Battery },
  weight: { label: "recovery.metric.weight", icon: Scale },
};

const WARNING_KEYS: Record<string, MessageKey> = {
  no_sleep_data: "recovery.warning.no_sleep_data",
  no_sleep_score_data: "recovery.warning.no_sleep_score_data",
  no_hrv_data: "recovery.warning.no_hrv_data",
  no_resting_hr_data: "recovery.warning.no_resting_hr_data",
  no_body_battery_data: "recovery.warning.no_body_battery_data",
  no_weight_data: "recovery.warning.no_weight_data",
  no_recovery_data: "recovery.warning.no_recovery_data",
  partial_recovery_data: "recovery.warning.partial_recovery_data",
  stale_recovery_data: "recovery.warning.stale_recovery_data",
  short_recovery_history: "recovery.warning.short_recovery_history",
};

const NOTE_KEYS: Record<string, MessageKey> = {
  recovery_is_context_only: "recovery.notes.recovery_is_context_only",
  not_medical_advice: "recovery.notes.not_medical_advice",
  from_garmin_export: "recovery.notes.from_garmin_export",
  sleep_duration_in_seconds: "recovery.notes.sleep_duration_in_seconds",
  weight_is_not_a_performance_metric: "recovery.notes.weight_is_not_a_performance_metric",
  import_garmin_export: "recovery.notes.import_garmin_export",
};

const CHART_PRIORITY = [
  "sleep_duration",
  "hrv",
  "resting_hr",
  "body_battery",
  "sleep_score",
  "weight",
] as const;

export function RecoveryPage() {
  const { t, locale, units } = useI18n();
  const [days, setDays] = useState<number>(90);
  const [selectedKey, setSelectedKey] = useState<string>("sleep_duration");
  const recovery = useRecovery(days);

  if (recovery.isLoading) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow={t("recovery.page.eyebrow")} title={t("recovery.page.title")} />
        <div className="analysis-skeleton">
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
        </div>
      </div>
    );
  }

  if (recovery.isError || !recovery.data) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow={t("recovery.page.eyebrow")}
          title={t("recovery.page.title")}
          description={t("recovery.page.subtitle")}
        />
        <ErrorState
          message={
            recovery.error instanceof Error ? recovery.error.message : t("recovery.error")
          }
          onRetry={() => void recovery.refetch()}
        />
      </div>
    );
  }

  const data = recovery.data;
  const metrics = data.metrics ?? [];
  const chartable = CHART_PRIORITY.map((key) =>
    metrics.find((metric) => metric.key === key),
  ).filter(
    (metric): metric is RecoveryMetric =>
      Boolean(metric && (metric.points ?? []).length >= 2),
  );
  const activeMetric =
    chartable.find((metric) => metric.key === selectedKey) ?? chartable[0];
  const insufficient = data.status === "insufficient";

  return (
    <div className="page-stack recovery-page">
      <PageHeader
        eyebrow={t("recovery.page.eyebrow")}
        title={t("recovery.page.title")}
        description={t("recovery.page.subtitle")}
        actions={
          <div className="recovery-actions">
            <div className="segmented" role="group" aria-label={t("recovery.page.title")}>
              {WINDOWS.map((value) => (
                <button
                  key={value}
                  type="button"
                  className={cn(days === value && "is-active")}
                  aria-pressed={days === value}
                  onClick={() => setDays(value)}
                >
                  {t(`recovery.window.${value}` as MessageKey)}
                </button>
              ))}
            </div>
            <Button
              variant="secondary"
              size="sm"
              loading={recovery.isFetching}
              onClick={() => void recovery.refetch()}
            >
              <RefreshCw size={15} aria-hidden="true" />
              {t("recovery.actions.refresh")}
            </Button>
            <Link to="/imports" className="button button--secondary button--sm">
              <ArrowRight size={15} aria-hidden="true" />
              {t("recovery.actions.import")}
            </Link>
          </div>
        }
      />

      {data.warnings?.length ? (
        <div className="analysis-warnings" role="status">
          <span className="analysis-warnings__icon">
            <CircleAlert size={16} aria-hidden="true" />
          </span>
          <div className="analysis-warnings__list">
            {data.warnings.map((warning) => (
              <Badge key={warning} tone="warning" dot>
                {WARNING_KEYS[warning] ? t(WARNING_KEYS[warning]) : warning}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}

      {insufficient ? (
        <Card className="panel">
          <EmptyState
            icon={HeartPulse}
            title={t("recovery.empty.title")}
            description={t("recovery.empty.body")}
            action={
              <Link to="/imports" className="button button--primary button--sm">
                <ArrowRight size={15} aria-hidden="true" />
                {t("recovery.empty.action")}
              </Link>
            }
          />
        </Card>
      ) : (
        <>
          <section className="recovery-grid">
            {metrics.map((metric) => (
              <RecoveryMetricCard
                key={metric.key}
                metric={metric}
                locale={locale}
                units={units}
              />
            ))}
          </section>

          <Card className="panel recovery-chart-card">
            <SectionHeading
              title={t("recovery.chart.title")}
              subtitle={t("recovery.chart.subtitle")}
              icon={Activity}
              action={
                data.imported_at ? (
                  <Badge tone="info">
                    {t("recovery.importedAt")}{" "}
                    {formatDate(data.imported_at, locale)}
                  </Badge>
                ) : null
              }
            />
            {chartable.length > 1 ? (
              <div className="recovery-chart__selector" role="group" aria-label={t("recovery.chart.select")}>
                {chartable.map((metric) => (
                  <button
                    key={metric.key}
                    type="button"
                    className={cn(activeMetric?.key === metric.key && "is-active")}
                    aria-pressed={activeMetric?.key === metric.key}
                    onClick={() => setSelectedKey(metric.key)}
                  >
                    {METRIC_META[metric.key]
                      ? t(METRIC_META[metric.key].label)
                      : metric.key}
                  </button>
                ))}
              </div>
            ) : null}
            {activeMetric ? (
              <RecoveryTrendChart metric={activeMetric} />
            ) : (
              <EmptyState
                compact
                icon={Activity}
                title={t("recovery.chart.empty")}
                description={t("recovery.chart.emptyBody")}
              />
            )}
          </Card>
        </>
      )}

      <section className="recovery-lower">
        <Card className="panel recovery-context">
          <SectionHeading
            title={t("recovery.context.title")}
            subtitle={t("recovery.context.subtitle")}
            icon={Info}
          />
          <p className="recovery-context__body">{t("recovery.context.body")}</p>
        </Card>

        <Card className="panel recovery-notes">
          <SectionHeading title={t("recovery.notes.title")} icon={Info} />
          <ul className="tracking-notes">
            {(data.notes ?? [])
              .filter((note) => NOTE_KEYS[note])
              .map((note) => (
                <li key={note}>{t(NOTE_KEYS[note])}</li>
              ))}
          </ul>
        </Card>
      </section>
    </div>
  );
}

function RecoveryMetricCard({
  metric,
  locale,
  units,
}: {
  metric: RecoveryMetric;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  const meta = METRIC_META[metric.key];
  const Icon = meta?.icon ?? Activity;
  const hasData = metric.latest_value != null;

  return (
    <Card className={cn("panel recovery-card", !hasData && "is-empty")}>
      <div className="recovery-card__head">
        <div className="recovery-card__title">
          <span className="recovery-card__icon">
            <Icon size={17} aria-hidden="true" />
          </span>
          <strong>{meta ? t(meta.label) : metric.key}</strong>
        </div>
        {hasData ? (
          <Badge tone="neutral">
            {t("recovery.metric.coverage", { days: metric.coverage_days })}
          </Badge>
        ) : (
          <Badge tone="neutral">{t("recovery.metric.noData")}</Badge>
        )}
      </div>

      {hasData ? (
        <>
          <div className="recovery-card__value">
            <strong>{formatRecoveryValue(metric.key, metric.latest_value, units, locale)}</strong>
            <span>
              {metric.latest_date
                ? formatDate(metric.latest_date, locale)
                : t("recovery.metric.noData")}
            </span>
          </div>

          <div className="recovery-card__stats">
            <div>
              <span>{t("recovery.metric.avg7")}</span>
              <strong>{formatRecoveryValue(metric.key, metric.avg_7d, units, locale)}</strong>
            </div>
            <div>
              <span>{t("recovery.metric.avg28")}</span>
              <strong>{formatRecoveryValue(metric.key, metric.avg_28d, units, locale)}</strong>
            </div>
            <div>
              <span>{t("recovery.metric.change28")}</span>
              <strong>
                {formatRecoveryDelta(metric.key, metric.change_28d, units, locale)}
              </strong>
            </div>
          </div>
        </>
      ) : (
        <p className="recovery-card__empty">{t("recovery.metric.missingBody")}</p>
      )}
    </Card>
  );
}
