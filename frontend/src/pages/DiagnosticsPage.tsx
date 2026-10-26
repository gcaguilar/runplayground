import { Link } from "@tanstack/react-router";
import {
  Activity,
  ArrowRight,
  BarChart3,
  CalendarClock,
  CalendarDays,
  Database,
  Flag,
  Gauge,
  HeartPulse,
  RefreshCw,
  ShieldAlert,
  Stethoscope,
  Target,
  Upload,
  Zap,
} from "lucide-react";

import type {
  AnalysisCoverage,
  AnalysisReference,
  DiagnosticsOverview,
} from "@/api/client";
import { useDiagnostics } from "@/api/queries";
import { WeeklyLoadChart } from "@/components/Charts";
import {
  AnalysisConfidence,
  AnalysisMethodCard,
  AnalysisStatusBadge,
  AnalysisWarnings,
  DimensionCard,
  DIMENSION_META,
  IntensityPanel,
  LoadPanel,
  ReasonChips,
} from "@/components/analysis";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  ScoreRing,
  SectionHeading,
  Skeleton,
} from "@/components/ui";
import { useI18n, type Locale, type MessageKey, type Units } from "@/i18n";
import {
  formatClock,
  formatDate,
  formatDateTime,
  formatDistance,
  formatNumber,
  formatPace,
  formatPercent,
} from "@/lib/format";

const DISTANCE_LABELS: Array<[number, MessageKey]> = [
  [5000, "distance.5k"],
  [10000, "distance.10k"],
  [21097.5, "distance.half_marathon"],
  [42195, "distance.marathon"],
];

export function DiagnosticsPage() {
  const { t, locale, units } = useI18n();
  const diagnostics = useDiagnostics();

  if (diagnostics.isLoading) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow={t("diagnostics.page.eyebrow")}
          title={t("diagnostics.page.title")}
        />
        <div className="analysis-skeleton">
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
        </div>
      </div>
    );
  }

  if (diagnostics.isError || !diagnostics.data) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow={t("diagnostics.page.eyebrow")}
          title={t("diagnostics.page.title")}
          description={t("diagnostics.page.subtitle")}
        />
        <ErrorState
          message={
            diagnostics.error instanceof Error
              ? diagnostics.error.message
              : t("diagnostics.error")
          }
          onRetry={() => void diagnostics.refetch()}
        />
      </div>
    );
  }

  const data = diagnostics.data;
  const insufficient = data.status === "insufficient" || data.score === null;
  const warnings = data.warnings ?? [];

  return (
    <div className="page-stack diagnostics-page">
      <PageHeader
        eyebrow={t("diagnostics.page.eyebrow")}
        title={t("diagnostics.page.title")}
        description={t("diagnostics.page.subtitle")}
        actions={
          <div className="analysis-actions">
            <Button
              variant="secondary"
              size="sm"
              loading={diagnostics.isFetching}
              onClick={() => void diagnostics.refetch()}
            >
              <RefreshCw size={15} aria-hidden="true" />
              {t("analysis.actions.refresh")}
            </Button>
            <Link to="/imports" className="button button--primary button--sm">
              <Upload size={15} aria-hidden="true" />
              {t("analysis.actions.import")}
            </Link>
          </div>
        }
      />

      <AnalysisWarnings warnings={warnings} />

      {insufficient ? (
        <Card className="panel">
          <EmptyState
            icon={Stethoscope}
            title={t("diagnostics.empty.title")}
            description={t("diagnostics.empty.body")}
            action={
              <Link to="/imports" className="button button--primary button--sm">
                <Upload size={15} aria-hidden="true" />
                {t("diagnostics.empty.import")}
              </Link>
            }
          />
        </Card>
      ) : (
        <section className="diagnostics-hero">
          <Card className="panel diagnostics-overview-card">
            <div className="diagnostics-overview-card__ring">
              <ScoreRing
                score={Math.round(data.score ?? 0)}
                label={t("diagnostics.overall.scoreLabel")}
              />
              <AnalysisStatusBadge status={data.status} />
            </div>
            <div className="diagnostics-overview-card__copy">
              <span className="eyebrow">{t("diagnostics.overall.eyebrow")}</span>
              <h2>{headlineTitle(data, t)}</h2>
              <p>{headlineBody(data, t)}</p>
              <div className="diagnostics-overview-card__meta">
                <AnalysisConfidence
                  confidence={data.confidence}
                  score={data.confidence_score}
                />
                <span>{t("diagnostics.overall.window", { days: data.window_days })}</span>
                <span>
                  {t("diagnostics.overall.generated", {
                    date: formatDateTime(data.generated_at, locale),
                  })}
                </span>
              </div>
              <GoalStrip data={data} locale={locale} units={units} />
            </div>
          </Card>

          <Card className="panel diagnostics-coverage-card">
            <SectionHeading
              title={t("analysis.coverage.title")}
              subtitle={t("analysis.coverage.subtitle")}
              icon={Database}
            />
            <CoverageStats coverage={data.coverage} locale={locale} units={units} />
            <CoverageFlags coverage={data.coverage} locale={locale} />
            <ReferenceBlock reference={data.reference} locale={locale} />
          </Card>
        </section>
      )}

      {insufficient ? (
        <Card className="panel diagnostics-coverage-card">
          <SectionHeading
            title={t("analysis.coverage.title")}
            subtitle={t("analysis.coverage.subtitle")}
            icon={Database}
          />
          <CoverageStats coverage={data.coverage} locale={locale} units={units} />
          <CoverageFlags coverage={data.coverage} locale={locale} />
          <ReferenceBlock reference={data.reference} locale={locale} />
        </Card>
      ) : null}

      <section className="diagnostics-dimensions">
        <SectionHeading
          title={t("diagnostics.dimensions.title")}
          subtitle={t("diagnostics.dimensions.subtitle")}
          icon={Stethoscope}
          action={<Badge tone="info">{t("diagnostics.dimensions.weights")}</Badge>}
        />
        <div className="dimension-grid">
          {data.dimensions.map((dimension) => (
            <DimensionCard
              key={dimension.key}
              dimension={dimension}
              locale={locale}
              units={units}
            />
          ))}
        </div>
      </section>

      <Card className="panel diagnostics-limiters">
        <SectionHeading
          title={t("diagnostics.limiters.title")}
          subtitle={t("diagnostics.limiters.subtitle")}
          icon={ShieldAlert}
        />
        {data.limiters.length ? (
          <div className="limiter-list">
            {data.limiters.map((limiter) => {
              const meta = DIMENSION_META[limiter.dimension_key];
              const Icon = meta?.icon ?? Gauge;
              return (
                <div className="limiter-row" key={limiter.dimension_key}>
                  <span className="limiter-row__rank">
                    {formatNumber(limiter.priority, locale)}
                  </span>
                  <span className="limiter-row__icon">
                    <Icon size={16} aria-hidden="true" />
                  </span>
                  <div className="limiter-row__copy">
                    <div className="limiter-row__head">
                      <strong>
                        {meta ? t(meta.label) : limiter.dimension_key}
                      </strong>
                      <Badge tone="warning">
                        {t("diagnostics.limiters.impact", {
                          points: formatNumber(limiter.impact, locale, 1),
                        })}
                      </Badge>
                    </div>
                    <ReasonChips reasons={limiter.reasons} />
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="analysis-empty">
            {insufficient
              ? t("diagnostics.limiters.insufficient")
              : t("diagnostics.limiters.empty")}
          </p>
        )}
      </Card>

      {!insufficient ? (
        <>
          <section className="analysis-duo">
            <Card className="panel">
              <IntensityPanel intensity={data.intensity} />
            </Card>
            <Card className="panel">
              <LoadPanel load={data.load} />
            </Card>
          </section>

          <Card className="panel">
            <SectionHeading
              title={t("analysis.load.chartTitle")}
              subtitle={t("analysis.load.chartSubtitle")}
              icon={BarChart3}
              action={<Badge tone="info">{t("analysis.load.estimated")}</Badge>}
            />
            <WeeklyLoadChart load={data.load} />
          </Card>
        </>
      ) : null}

      <AnalysisMethodCard
        title={t("diagnostics.method.title")}
        subtitle={t("diagnostics.method.subtitle")}
        items={[
          {
            icon: Gauge,
            title: t("diagnostics.method.score.title"),
            body: t("diagnostics.method.score.body"),
          },
          {
            icon: Zap,
            title: t("diagnostics.method.intensity.title"),
            body: t("diagnostics.method.intensity.body"),
          },
          {
            icon: Activity,
            title: t("diagnostics.method.load.title"),
            body: t("diagnostics.method.load.body"),
          },
          {
            icon: HeartPulse,
            title: t("diagnostics.method.recovery.title"),
            body: t("diagnostics.method.recovery.body"),
          },
        ]}
      />
    </div>
  );
}

function headlineTitle(
  data: DiagnosticsOverview,
  t: (key: MessageKey, values?: Record<string, string | number>) => string,
): string {
  if (data.headline === "insufficient") return t("diagnostics.headline.insufficient");
  if (data.headline === "balanced") return t("diagnostics.headline.balanced");
  const meta = DIMENSION_META[data.headline];
  if (!meta) return t("diagnostics.headline.limiter", { dimension: data.headline });
  return t("diagnostics.headline.limiter", { dimension: t(meta.label) });
}

function headlineBody(
  data: DiagnosticsOverview,
  t: (key: MessageKey) => string,
): string {
  if (data.headline === "insufficient") return t("diagnostics.headline.insufficientBody");
  if (data.headline === "balanced") return t("diagnostics.headline.balancedBody");
  return t("diagnostics.headline.limiterBody");
}

function GoalStrip({
  data,
  locale,
  units,
}: {
  data: DiagnosticsOverview;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  const goal = data.goal;
  if (!goal) {
    return (
      <div className="diagnostics-goal diagnostics-goal--empty">
        <Target size={15} aria-hidden="true" />
        <span>{t("diagnostics.goal.none")}</span>
        <Link to="/performance" className="text-link">
          {t("diagnostics.goal.set")}
          <ArrowRight size={13} aria-hidden="true" />
        </Link>
      </div>
    );
  }

  const label = distanceLabel(goal.distance_m);
  return (
    <div className="diagnostics-goal">
      <Target size={15} aria-hidden="true" />
      <div>
        <span>{t("diagnostics.goal.title")}</span>
        <strong>
          {label ? t(label) : formatDistance(goal.distance_m, units, locale, { digits: 1 })}
          <span className="dot-sep" aria-hidden="true" />
          {formatClock(goal.target_time_s)}
          <span className="dot-sep" aria-hidden="true" />
          {formatPace(goal.target_time_s / (goal.distance_m / 1000), units)}
        </strong>
        <small>
          {goal.race_name ? `${goal.race_name} · ` : ""}
          {goal.target_date
            ? formatDate(goal.target_date, locale)
            : t("diagnostics.goal.noDate")}
        </small>
      </div>
      <Link to="/performance" className="text-link">
        {t("diagnostics.goal.edit")}
        <ArrowRight size={13} aria-hidden="true" />
      </Link>
    </div>
  );
}

function CoverageStats({
  coverage,
  locale,
  units,
}: {
  coverage: AnalysisCoverage;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  return (
    <div className="coverage-grid">
      <CoverageStat
        icon={Activity}
        label={t("analysis.coverage.activities")}
        value={formatNumber(coverage.activities, locale)}
      />
      <CoverageStat
        icon={CalendarDays}
        label={t("analysis.coverage.weeks")}
        value={`${formatNumber(coverage.weeks_with_data, locale)} / ${formatNumber(
          coverage.window_weeks,
          locale,
        )}`}
      />
      <CoverageStat
        icon={Gauge}
        label={t("analysis.coverage.anchor")}
        value={
          coverage.anchor_pace_s_per_km
            ? formatPace(coverage.anchor_pace_s_per_km, units)
            : t("common.noData")
        }
      />
      <CoverageStat
        icon={HeartPulse}
        label={t("analysis.coverage.readiness")}
        value={formatNumber(coverage.readiness_days, locale)}
      />
      <CoverageStat
        icon={CalendarClock}
        label={t("analysis.coverage.lastActivity")}
        value={formatDate(coverage.last_activity_at, locale)}
      />
      <CoverageStat
        icon={Flag}
        label={t("analysis.coverage.lastRace")}
        value={formatDate(coverage.last_race_at, locale)}
      />
    </div>
  );
}

function CoverageFlags({
  coverage,
  locale,
}: {
  coverage: AnalysisCoverage;
  locale: Locale;
}) {
  const { t } = useI18n();
  return (
    <div className="coverage-flags">
      <Badge tone={coverage.has_hr ? "success" : "warning"} dot>
        {t("analysis.coverage.hr")}: {coverage.has_hr ? t("analysis.yes") : t("analysis.no")}
      </Badge>
      <Badge tone={coverage.trail_share > 0.4 ? "warning" : "neutral"}>
        {t("analysis.coverage.trail")}: {formatPercent(coverage.trail_share * 100, locale)}
      </Badge>
      <Badge tone={coverage.has_anchor ? "success" : "warning"} dot>
        {t("analysis.coverage.anchor")}:{" "}
        {coverage.has_anchor ? t("analysis.yes") : t("analysis.no")}
      </Badge>
    </div>
  );
}

function ReferenceBlock({
  reference,
  locale,
}: {
  reference: AnalysisReference;
  locale: Locale;
}) {
  const { t } = useI18n();
  if (!reference.imported_at) {
    return (
      <div className="analysis-reference analysis-reference--empty">
        <span className="eyebrow">{t("analysis.reference.title")}</span>
        <p>{t("analysis.reference.none")}</p>
        <Link to="/imports" className="text-link">
          {t("analysis.actions.import")}
          <ArrowRight size={13} aria-hidden="true" />
        </Link>
      </div>
    );
  }

  return (
    <div className="analysis-reference">
      <div className="analysis-reference__head">
        <span className="eyebrow">{t("analysis.reference.title")}</span>
        <small>
          {t("analysis.reference.imported", {
            date: formatDate(reference.imported_at, locale),
          })}
        </small>
      </div>
      <div className="analysis-reference__metrics">
        <ReferenceMetric
          label={t("analysis.reference.readiness")}
          value={
            reference.readiness_28d === null || reference.readiness_28d === undefined
              ? "—"
              : formatNumber(reference.readiness_28d, locale, 1)
          }
        />
        <ReferenceMetric
          label={t("analysis.reference.acute")}
          value={formatNumber(reference.acute_load, locale)}
        />
        <ReferenceMetric
          label={t("analysis.reference.chronic")}
          value={formatNumber(reference.chronic_load, locale)}
        />
      </div>
      <p className="analysis-note">{t("analysis.reference.disclaimer")}</p>
    </div>
  );
}

function CoverageStat({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Activity;
  label: string;
  value: string;
}) {
  return (
    <div className="coverage-stat">
      <span>
        <Icon size={13} aria-hidden="true" />
        {label}
      </span>
      <strong>{value}</strong>
    </div>
  );
}

function ReferenceMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="reference-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function distanceLabel(distance: number): MessageKey | null {
  const match = DISTANCE_LABELS.find(([meters]) => Math.abs(meters - distance) < 1);
  return match ? match[1] : null;
}
