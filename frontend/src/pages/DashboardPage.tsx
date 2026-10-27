import { useMemo, useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Clock3,
  Database,
  Gauge,
  Mountain,
  RefreshCw,
  Route,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  Upload,
  type LucideIcon,
} from "lucide-react";

import {
  useActivities,
  useAudit,
  useBriefing,
  useStartSync,
  useSyncStatus,
  useWeeklySummary,
} from "@/api/queries";
import type {
  Activity,
  AuditReport,
  BriefingDistance,
  BriefingInsight,
  BriefingTrend,
  BriefingView,
} from "@/api/client";
import { DIMENSION_META } from "@/components/analysis";
import { WeeklyVolumeChart } from "@/components/Charts";
import { SportGlyph } from "@/components/SportGlyph";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  ProgressBar,
  ScoreRing,
  SectionHeading,
  Skeleton,
} from "@/components/ui";
import { useI18n, type Locale, type MessageKey } from "@/i18n";
import {
  addDays,
  formatClock,
  formatDate,
  formatDelta,
  formatDistance,
  formatDuration,
  formatElevation,
  formatPace,
  formatPercent,
  formatWeekRange,
  localIsoDate,
  scoreBand,
  sportKey,
  weekStartKey,
} from "@/lib/format";
import { cn } from "@/lib/cn";

export function DashboardPage() {
  const { locale, units, t } = useI18n();
  const [weekOffset, setWeekOffset] = useState(0);
  const selectedWeek = weekStartKey(weekOffset);
  const summary = useWeeklySummary(selectedWeek);
  const briefing = useBriefing();
  const recent = useActivities({ limit: 5, sort: "date_desc" });
  const audit = useAudit();
  const sync = useSyncStatus();
  const startSync = useStartSync();

  const data = summary.data;
  const totals = data?.totals;
  const previous = data?.previous;
  const weekEnd = data?.week_end ?? localIsoDate(addDays(new Date(`${selectedWeek}T12:00:00`), 6));

  const focus = useMemo(() => {
    if ((audit.data?.coverage.total_activities ?? 0) === 0) {
      return {
        icon: Upload,
        title: t("dashboard.focus.noActivities.title"),
        description: t("dashboard.focus.noActivities.desc"),
        cta: t("dashboard.focus.noActivities.cta"),
        to: "/imports" as const,
      };
    }
    const missingStreams = audit.data?.findings.find(
      (finding) => finding.code === "missing_streams" && (finding.count ?? 0) > 0,
    );
    if (missingStreams) {
      return {
        icon: Database,
        title: t("dashboard.focus.missingStreams.title"),
        description: t("dashboard.focus.missingStreams.desc"),
        cta: t("dashboard.focus.missingStreams.cta"),
        to: "/data" as const,
      };
    }
    if (!audit.data?.garmin_configured) {
      return {
        icon: RefreshCw,
        title: t("dashboard.focus.noKey.title"),
        description: t("dashboard.focus.noKey.desc"),
        cta: t("dashboard.focus.noKey.cta"),
        to: "/settings" as const,
      };
    }
    return {
      icon: Gauge,
      title: t("dashboard.focus.ready.title"),
      description: t("dashboard.focus.ready.desc"),
      cta: t("dashboard.focus.ready.cta"),
      to: "/performance" as const,
    };
  }, [audit.data, t]);

  const lastRun = sync.data?.last_run;
  const running = Boolean(sync.data?.running);
  const garminConfigured = sync.data?.garmin_configured ?? false;
  const FocusIcon = focus.icon;

  const weekSwitcher = (
    <div className="week-switcher" aria-label={t("dashboard.week.title")}>
      <Button
        size="icon"
        variant="ghost"
        onClick={() => setWeekOffset((value) => value - 1)}
        aria-label={t("dashboard.previousWeek")}
      >
        <ChevronLeft size={18} aria-hidden="true" />
      </Button>
      <div className="week-switcher__label">
        <span>
          {weekOffset === 0
            ? t("dashboard.thisWeek")
            : formatWeekRange(selectedWeek, weekEnd, locale)}
        </span>
        {weekOffset === 0 ? (
          <small>{formatWeekRange(selectedWeek, weekEnd, locale)}</small>
        ) : (
          <button type="button" onClick={() => setWeekOffset(0)}>
            {t("dashboard.currentWeek")}
          </button>
        )}
      </div>
      <Button
        size="icon"
        variant="ghost"
        onClick={() => setWeekOffset((value) => Math.min(0, value + 1))}
        disabled={weekOffset >= 0}
        aria-label={t("dashboard.nextWeek")}
      >
        <ChevronRight size={18} aria-hidden="true" />
      </Button>
    </div>
  );

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={
          <span className="eyebrow-inline">
            <Sparkles size={13} aria-hidden="true" />
            {t("dashboard.page.eyebrow")}
          </span>
        }
        title={t("dashboard.page.title")}
        description={t("dashboard.page.subtitle")}
      />

      <BriefingSection briefing={briefing} locale={locale} units={units} />

      <SectionHeading
        title={t("dashboard.week.title")}
        subtitle={t("dashboard.week.subtitle")}
        icon={CalendarDays}
        action={weekSwitcher}
      />

      {summary.isError ? (
        <ErrorState
          message={summary.error instanceof Error ? summary.error.message : undefined}
          onRetry={() => void summary.refetch()}
        />
      ) : summary.isLoading || !data || !totals || !previous ? (
        <DashboardSkeleton />
      ) : (
        <>
          <section className="stat-grid">
            <StatCard
              label={t("dashboard.metric.distance")}
              value={formatDistance(totals.distance_m, units, locale, { digits: 1 })}
              delta={data.delta.distance_pct}
              previous={previous.distance_m}
              icon={Route}
              sparkline={data.days.map((day) => day.distance_m)}
            />
            <StatCard
              label={t("dashboard.metric.duration")}
              value={formatDuration(totals.duration_s, locale)}
              delta={data.delta.duration_pct}
              previous={previous.duration_s}
              icon={Clock3}
              footnote={`${totals.activities} ${totals.activities === 1 ? t("common.activity") : t("common.activities")}`}
            />
            <StatCard
              label={t("dashboard.metric.elevation")}
              value={formatElevation(totals.elevation_gain_m, units, locale)}
              delta={data.delta.elevation_pct}
              previous={previous.elevation_gain_m}
              icon={Mountain}
            />
            <StatCard
              label={t("dashboard.metric.activeDays")}
              value={`${totals.active_days}/7`}
              icon={CalendarDays}
              footnote={t("dashboard.delta.vsPrev")}
              previous={previous.active_days}
              rawComparison={previous.active_days}
            />
          </section>

          <div className="dashboard-primary">
            <Card className="panel panel--volume">
              <SectionHeading
                title={t("dashboard.volume.title")}
                subtitle={t("dashboard.volume.subtitle")}
                action={
                  <Badge tone="accent">
                    {formatDistance(totals.distance_m, units, locale, { digits: 1 })}
                  </Badge>
                }
              />
              <WeeklyVolumeChart days={data.days} />
            </Card>

            <div className="dashboard-rail">
              <QualityCard data={audit.data} loading={audit.isLoading} error={audit.isError} onRetry={() => void audit.refetch()} />
              <Card className="panel sync-card">
                <SectionHeading
                  title={t("dashboard.sync.title")}
                  icon={RefreshCw}
                  action={
                    <Badge tone={running ? "info" : lastRun?.status === "error" ? "danger" : garminConfigured ? "success" : "neutral"} dot>
                      {running
                        ? t("topbar.syncing")
                        : !garminConfigured
                          ? t("dashboard.sync.notConfigured")
                          : lastRun
                            ? syncStatusLabel(lastRun.status, t)
                            : t("sidebar.never")}
                    </Badge>
                  }
                />
                {garminConfigured ? (
                  <>
                    <div className="sync-card__rows">
                      <div>
                        <span>{t("dashboard.sync.last")}</span>
                        <strong>{lastRun?.finished_at ? formatDate(lastRun.finished_at, locale, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : t("dashboard.sync.never")}</strong>
                      </div>
                      <div>
                        <span>{t("dashboard.sync.next")}</span>
                        <strong>
                          {sync.data?.next_sync_at
                            ? formatDate(sync.data.next_sync_at, locale, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
                            : t("settings.sync.disabled")}
                        </strong>
                      </div>
                    </div>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => startSync.mutate("incremental")}
                      loading={startSync.isPending || running}
                      disabled={running}
                    >
                      <RefreshCw size={14} className={cn(running && "spin")} aria-hidden="true" />
                      {running ? t("settings.sync.running") : t("settings.sync.incremental")}
                    </Button>
                    {startSync.isError ? (
                      <p className="form-error">
                        {startSync.error instanceof Error ? startSync.error.message : t("settings.sync.error")}
                      </p>
                    ) : null}
                  </>
                ) : (
                  <div className="sync-card__off">
                    <CircleAlert size={17} aria-hidden="true" />
                    <p>{t("dashboard.sync.notConfigured")}</p>
                    <Link to="/settings" className="text-link">
                      {t("dashboard.sync.configure")}
                      <ArrowRight size={13} aria-hidden="true" />
                    </Link>
                  </div>
                )}
              </Card>
            </div>
          </div>

          <div className="dashboard-secondary">
            <Card className="panel recent-card">
              <SectionHeading
                title={t("dashboard.recent.title")}
                subtitle={t("dashboard.recent.subtitle")}
                action={
                  <Link to="/activities" className="text-link">
                    {t("common.viewAll")}
                    <ArrowRight size={13} aria-hidden="true" />
                  </Link>
                }
              />
              {recent.isLoading ? (
                <div className="recent-list">
                  {Array.from({ length: 3 }).map((_, index) => (
                    <div className="recent-row" key={index}>
                      <Skeleton className="skeleton--avatar" />
                      <div className="recent-row__copy">
                        <Skeleton className="skeleton--line" />
                        <Skeleton className="skeleton--line skeleton--short" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : recent.data?.items.length ? (
                <div className="recent-list">
                  {recent.data.items.map((activity) => (
                    <RecentRow key={activity.id} activity={activity} locale={locale} units={units} />
                  ))}
                </div>
              ) : (
                <EmptyState
                  compact
                  icon={Route}
                  title={t("dashboard.recent.empty")}
                  action={
                    <Link to="/imports" className="button button--secondary button--sm">
                      <Upload size={14} aria-hidden="true" />
                      {t("dashboard.recent.cta")}
                    </Link>
                  }
                />
              )}
            </Card>

            <Card className={cn("panel focus-card", `focus-card--${focus.to.slice(1)}`)}>
              <div className="focus-card__icon">
                <FocusIcon size={21} aria-hidden="true" />
              </div>
              <div className="focus-card__body">
                <span className="eyebrow">{t("dashboard.focus.title")}</span>
                <h2>{focus.title}</h2>
                <p>{focus.description}</p>
              </div>
              <Link to={focus.to} className="button button--primary button--md focus-card__cta">
                {focus.cta}
                <ArrowRight size={15} aria-hidden="true" />
              </Link>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  delta,
  previous,
  icon: Icon,
  sparkline,
  footnote,
  rawComparison,
}: {
  label: string;
  value: string;
  delta?: number | null;
  previous?: number;
  icon: typeof Route;
  sparkline?: number[];
  footnote?: string;
  rawComparison?: number;
}) {
  const { locale, t } = useI18n();
  const formattedDelta = formatDelta(delta, locale);
  const hasPrevious = (previous ?? 0) > 0;
  const isUp = (delta ?? 0) > 0;

  return (
    <Card className="stat-card">
      <div className="stat-card__top">
        <span className="stat-card__label">{label}</span>
        <span className="stat-card__icon">
          <Icon size={17} aria-hidden="true" />
        </span>
      </div>
      <strong className="stat-card__value">{value}</strong>
      <div className="stat-card__bottom">
        {delta !== undefined && delta !== null ? (
          <span className={cn("delta", isUp ? "delta--up" : "delta--down")}>
            {isUp ? <ArrowUpRight size={12} aria-hidden="true" /> : <ArrowDownRight size={12} aria-hidden="true" />}
            {formattedDelta}
            <small>{t("dashboard.delta.vsPrev")}</small>
          </span>
        ) : rawComparison !== undefined ? (
          <span className="delta delta--flat">
            {rawComparison > 0 ? `${rawComparison}/7 ${t("dashboard.previousWeek").toLowerCase()}` : t("dashboard.delta.noPrev")}
          </span>
        ) : (
          <span className={cn("delta", hasPrevious ? "delta--flat" : "delta--muted")}>
            {hasPrevious ? t("dashboard.delta.same") : t("dashboard.delta.noPrev")}
          </span>
        )}
        {footnote && delta === undefined && rawComparison === undefined ? (
          <small className="stat-card__footnote">{footnote}</small>
        ) : null}
      </div>
      {sparkline ? <MiniSparkline values={sparkline} /> : null}
    </Card>
  );
}

function MiniSparkline({ values }: { values: number[] }) {
  const max = Math.max(...values, 1);
  return (
    <div className="stat-sparkline" aria-hidden="true">
      {values.map((value, index) => (
        <span key={index} style={{ height: `${Math.max(6, (value / max) * 100)}%` }} />
      ))}
    </div>
  );
}

function QualityCard({
  data,
  loading,
  error,
  onRetry,
}: {
  data: AuditReport | undefined;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
}) {
  const { t } = useI18n();
  if (loading) {
    return (
      <Card className="panel quality-card">
        <Skeleton className="skeleton--line" />
        <Skeleton className="skeleton--block" />
      </Card>
    );
  }
  if (error || !data) {
    return (
      <Card className="panel quality-card">
        <ErrorState onRetry={onRetry} />
      </Card>
    );
  }
  const band = scoreBand(data.score);
  const bandLabels: Record<ReturnType<typeof scoreBand>, MessageKey> = {
    excellent: "dashboard.data.excellent",
    good: "dashboard.data.good",
    fair: "dashboard.data.fair",
    poor: "dashboard.data.poor",
  };
  return (
    <Card className="panel quality-card">
      <SectionHeading
        title={t("dashboard.data.title")}
        icon={Database}
        action={
          <Link to="/data" className="text-link">
            {t("dashboard.data.viewAudit")}
            <ArrowRight size={13} aria-hidden="true" />
          </Link>
        }
      />
      <div className="quality-card__body">
        <ScoreRing score={data.score} label={t("dashboard.data.score")} caption={t(bandLabels[band])} />
        <div className="coverage-mini">
          {[
            { label: t("dashboard.coverage.streams"), value: data.coverage.pct_streams },
            { label: t("dashboard.coverage.hr"), value: data.coverage.pct_hr },
            { label: t("dashboard.coverage.gps"), value: data.coverage.pct_gps },
          ].map((row) => (
            <div className="coverage-mini__row" key={row.label}>
              <div>
                <span>{row.label}</span>
                <strong>{Math.round(row.value)}%</strong>
              </div>
              <ProgressBar value={row.value} label={row.label} />
            </div>
          ))}
        </div>
      </div>
      <p className="quality-card__meta">
        {data.coverage.total_activities} {data.coverage.total_activities === 1 ? t("common.activity") : t("common.activities")}
        {data.findings.length ? ` · ${data.findings.length} ${t("data.findings.title").toLowerCase()}` : ""}
      </p>
    </Card>
  );
}

function RecentRow({
  activity,
  locale,
  units,
}: {
  activity: Activity;
  locale: Locale;
  units: "metric" | "imperial";
}) {
  const { t } = useI18n();
  const name = activity.name?.trim() || t(sportKey(activity.sub_sport || activity.sport));
  return (
    <Link
      to="/activities/$activityId"
      params={{ activityId: String(activity.id) }}
      className="recent-row"
    >
      <SportGlyph sport={activity.sub_sport || activity.sport} />
      <div className="recent-row__copy">
        <div className="recent-row__title">
          <strong>{name}</strong>
          {activity.is_race ? <span className="race-flag">{t("detail.race")}</span> : null}
        </div>
        <span>
          {formatDate(activity.start_time_utc, locale, { weekday: "short", day: "numeric", month: "short" })}
          <span className="dot-sep" aria-hidden="true" />
          {t(sportKey(activity.sub_sport || activity.sport))}
        </span>
      </div>
      <div className="recent-row__stats">
        <strong>{formatDistance(activity.distance_m, units, locale)}</strong>
        <span>{formatPace(activity.avg_pace_s_per_km, units)}</span>
      </div>
      <ArrowRight size={15} className="recent-row__arrow" aria-hidden="true" />
    </Link>
  );
}

const BRIEFING_DISTANCE_KEYS: Record<string, MessageKey> = {
  "5k": "distance.5k",
  "10k": "distance.10k",
  half_marathon: "distance.half_marathon",
  marathon: "distance.marathon",
};

function BriefingSection({
  briefing,
  locale,
  units,
}: {
  briefing: ReturnType<typeof useBriefing>;
  locale: Locale;
  units: "metric" | "imperial";
}) {
  const { t } = useI18n();

  if (briefing.isLoading) {
    return (
      <section className="dashboard-briefing">
        <div className="briefing-hero">
          <Card className="panel">
            <Skeleton className="skeleton--line skeleton--short" />
            <Skeleton className="skeleton--title" />
            <Skeleton className="skeleton--block" />
          </Card>
          <Card className="panel">
            <Skeleton className="skeleton--line" />
            <Skeleton className="skeleton--block" />
          </Card>
        </div>
      </section>
    );
  }

  if (briefing.isError || !briefing.data) {
    return (
      <Card className="panel briefing-unavailable">
        <CircleAlert size={18} aria-hidden="true" />
        <p>
          {briefing.error instanceof Error
            ? briefing.error.message
            : t("dashboard.briefing.error")}
        </p>
        <Button variant="secondary" size="sm" onClick={() => void briefing.refetch()}>
          {t("common.retry")}
        </Button>
      </Card>
    );
  }

  const data = briefing.data;
  if (data.status === "insufficient" || !data.fitness_anchor) {
    return (
      <Card className="panel">
        <EmptyState
          icon={Sparkles}
          title={t("dashboard.briefing.empty.title")}
          description={t("dashboard.briefing.empty.body")}
          action={
            <Link to="/imports" className="button button--primary button--sm">
              <Upload size={15} aria-hidden="true" />
              {t("dashboard.briefing.empty.action")}
            </Link>
          }
        />
      </Card>
    );
  }

  const anchor = data.fitness_anchor;
  const signals = data.signals ?? [];
  const distances = data.distances ?? [];
  const trends = data.trends ?? [];

  return (
    <section className="dashboard-briefing">
      <SectionHeading
        title={t("dashboard.briefing.title")}
        subtitle={t("dashboard.briefing.subtitle")}
        icon={Sparkles}
        action={<BriefingConfidence confidence={data.confidence} score={data.confidence_score} />}
      />

      <div className="briefing-hero">
        <Card className="panel briefing-fitness">
          <span className="eyebrow">{t("dashboard.briefing.anchor")}</span>
          <div className="briefing-fitness__value">
            <strong>{formatClock(anchor.time_s)}</strong>
            <span>{formatPace(anchor.pace_s_per_km, units)}</span>
          </div>
          <div className="briefing-fitness__range">
            <span>{t("dashboard.briefing.range")}</span>
            <strong>
              {formatClock(anchor.low_s)} – {formatClock(anchor.high_s)}
            </strong>
          </div>
          <div className="briefing-trends">
            {trends.map((trend) => (
              <BriefingTrendPill key={trend.window_days} trend={trend} locale={locale} />
            ))}
          </div>
        </Card>

        <Card className="panel briefing-message">
          <SectionHeading title={t("dashboard.briefing.headline.title")} icon={Sparkles} />
          <p className="briefing-message__text">{briefingHeadline(data, locale, t)}</p>
          <div className="briefing-evidence">
            <span>{t("dashboard.briefing.headline.evidence")}</span>
            <div>
              {signals
                .filter((signal) => signal.score !== null && signal.score !== undefined)
                .slice(0, 4)
                .map((signal) => (
                  <span className="reason-chip" key={signal.key}>
                    {dimensionLabel(signal.key, t)}: {Math.round(signal.score ?? 0)}
                  </span>
                ))}
            </div>
          </div>
          <Link to="/diagnostics" className="text-link">
            {t("dashboard.briefing.headline.link")}
            <ArrowRight size={13} aria-hidden="true" />
          </Link>
        </Card>
      </div>

      <div className="briefing-conclusions">
        <ConclusionCard
          icon={TrendingUp}
          title={
            data.improvement?.key === "dimension_strength"
              ? t("dashboard.briefing.strength.title")
              : t("dashboard.briefing.improvement.title")
          }
          tone="success"
        >
          {briefingImprovement(data.improvement ?? null, locale, t)}
        </ConclusionCard>
        <ConclusionCard
          icon={TrendingDown}
          title={t("dashboard.briefing.limitation.title")}
          tone="warning"
        >
          {briefingLimitation(data.limitation ?? null, t)}
        </ConclusionCard>
        <ConclusionCard
          icon={Target}
          title={t("dashboard.briefing.action.title")}
          tone="accent"
          to="/training"
          linkLabel={t("dashboard.briefing.action.link")}
        >
          {briefingAction(data.action ?? null, t)}
        </ConclusionCard>
      </div>

      <Card className="panel briefing-predictions">
        <SectionHeading
          title={t("dashboard.briefing.predictions")}
          subtitle={t("dashboard.briefing.predictions.subtitle")}
          icon={Gauge}
        />
        <div className="briefing-distance-grid">
          {distances.map((distance) => (
            <BriefingDistanceTile key={distance.distance_key} distance={distance} />
          ))}
        </div>
      </Card>

      <p className="analysis-note">{t("dashboard.briefing.notes")}</p>
    </section>
  );
}

function briefingHeadline(
  data: BriefingView,
  locale: Locale,
  t: (key: MessageKey, values?: Record<string, string | number>) => string,
): string {
  const params = data.headline_params ?? {};
  const change = formatPercent(Number(params.change_pct ?? 0), locale, 1);
  const window = String(params.window_days ?? 28);
  const limiterKey = params.limiter ? String(params.limiter) : "";
  const limiter = limiterKey ? dimensionLabel(limiterKey, t) : t("common.unknown");
  return t(`dashboard.briefing.headline.${data.headline}` as MessageKey, {
    change,
    window,
    limiter,
  });
}

function briefingImprovement(
  improvement: BriefingInsight | null,
  locale: Locale,
  t: (key: MessageKey, values?: Record<string, string | number>) => string,
): string {
  if (!improvement) return t("dashboard.briefing.improvement.none");
  if (improvement.key === "fitness_trend") {
    return t("dashboard.briefing.improvement.fitness", {
      change: formatPercent(improvement.value ?? 0, locale, 1),
    });
  }
  return t("dashboard.briefing.improvement.dimension", {
    dimension: dimensionLabel(improvement.dimension_key ?? "", t),
    score: Math.round(improvement.value ?? 0),
  });
}

function briefingLimitation(
  limitation: BriefingInsight | null,
  t: (key: MessageKey, values?: Record<string, string | number>) => string,
): string {
  if (!limitation) return t("dashboard.briefing.limitation.none");
  return t("dashboard.briefing.limitation.body", {
    dimension: dimensionLabel(limitation.dimension_key ?? "", t),
    score: Math.round(limitation.value ?? 0),
  });
}

function briefingAction(
  action: { dimension_key: string; score?: number | null } | null,
  t: (key: MessageKey, values?: Record<string, string | number>) => string,
): string {
  if (!action) return t("dashboard.briefing.action.none");
  return t("dashboard.briefing.action.body", {
    dimension: dimensionLabel(action.dimension_key, t),
  });
}

function dimensionLabel(
  key: string,
  t: (key: MessageKey) => string,
): string {
  const meta = DIMENSION_META[key];
  return meta ? t(meta.label) : key || t("common.unknown");
}

function BriefingTrendPill({ trend, locale }: { trend: BriefingTrend; locale: Locale }) {
  const { t } = useI18n();
  const statusKey = `dashboard.briefing.trend.${trend.status}` as MessageKey;
  const tone =
    trend.status === "improving"
      ? "success"
      : trend.status === "worsening"
        ? "danger"
        : "neutral";
  return (
    <div className="briefing-trend">
      <span>{t("dashboard.briefing.weeks", { weeks: Math.round(trend.window_days / 7) })}</span>
      <Badge tone={tone}>{t(statusKey)}</Badge>
      <strong className={cn(trend.status === "improving" && "is-good", trend.status === "worsening" && "is-bad")}>
        {trend.change_pct == null ? "—" : formatPercent(trend.change_pct, locale, 1)}
      </strong>
    </div>
  );
}

function BriefingDistanceTile({ distance }: { distance: BriefingDistance }) {
  const { t } = useI18n();
  return (
    <div className="briefing-distance">
      <span className="briefing-distance__key">
        {t(BRIEFING_DISTANCE_KEYS[distance.distance_key] ?? "distance.10k")}
      </span>
      <strong>{formatClock(distance.time_s)}</strong>
      <small>
        {formatClock(distance.low_s)} – {formatClock(distance.high_s)}
      </small>
      <GoalGap distance={distance} t={t} />
    </div>
  );
}

function GoalGap({
  distance,
  t,
}: {
  distance: BriefingDistance;
  t: (key: MessageKey, values?: Record<string, string | number>) => string;
}) {
  const gap = distance.goal_gap_s;
  if (distance.goal_time_s == null || gap == null) {
    return <span className="briefing-distance__goal is-muted">{t("dashboard.briefing.prediction.noGoal")}</span>;
  }
  if (Math.abs(gap) < 0.5) {
    return (
      <span className="briefing-distance__goal">
        {formatClock(distance.goal_time_s)} · {t("dashboard.briefing.prediction.goalMatch")}
      </span>
    );
  }
  return (
    <span
      className={cn(
        "briefing-distance__goal",
        gap > 0 ? "is-ahead" : "is-behind",
      )}
    >
      {formatClock(distance.goal_time_s)} ·{" "}
      {gap > 0
        ? t("dashboard.briefing.prediction.goalAhead", { gap: formatClock(gap) })
        : t("dashboard.briefing.prediction.goalBehind", { gap: formatClock(Math.abs(gap)) })}
    </span>
  );
}

function ConclusionCard({
  icon: Icon,
  title,
  tone,
  to,
  linkLabel,
  children,
}: {
  icon: LucideIcon;
  title: string;
  tone: "success" | "warning" | "accent";
  to?: "/training";
  linkLabel?: string;
  children: string;
}) {
  return (
    <Card className={cn("panel briefing-conclusion", `briefing-conclusion--${tone}`)}>
      <div className="briefing-conclusion__head">
        <span className="briefing-conclusion__icon">
          <Icon size={17} aria-hidden="true" />
        </span>
        <strong>{title}</strong>
      </div>
      <p>{children}</p>
      {to && linkLabel ? (
        <Link to={to} className="text-link">
          {linkLabel}
          <ArrowRight size={13} aria-hidden="true" />
        </Link>
      ) : null}
    </Card>
  );
}

function BriefingConfidence({ confidence, score }: { confidence: string; score: number }) {
  const { t } = useI18n();
  const label =
    confidence === "high"
      ? "performance.confidence.high"
      : confidence === "medium"
        ? "performance.confidence.medium"
        : "performance.confidence.low";
  const tone = confidence === "high" ? "success" : confidence === "medium" ? "warning" : "danger";
  return (
    <Badge tone={tone}>
      {t("dashboard.briefing.confidence")} · {t(label)} · {Math.round(score * 100)}%
    </Badge>
  );
}

function DashboardSkeleton() {
  return (
    <div className="page-stack">
      <section className="stat-grid">
        {Array.from({ length: 4 }).map((_, index) => (
          <Card className="stat-card" key={index}>
            <Skeleton className="skeleton--line skeleton--short" />
            <Skeleton className="skeleton--title" />
            <Skeleton className="skeleton--line" />
          </Card>
        ))}
      </section>
      <div className="dashboard-primary">
        <Card className="panel">
          <Skeleton className="skeleton--line" />
          <Skeleton className="skeleton--chart" />
        </Card>
        <div className="dashboard-rail">
          <Card className="panel">
            <Skeleton className="skeleton--block" />
          </Card>
          <Card className="panel">
            <Skeleton className="skeleton--block" />
          </Card>
        </div>
      </div>
    </div>
  );
}

function syncStatusLabel(status: string, t: (key: MessageKey) => string): string {
  const known: Record<string, MessageKey> = {
    success: "sync.status.success",
    partial: "sync.status.partial",
    error: "sync.status.error",
    running: "sync.status.running",
    interrupted: "sync.status.interrupted",
  };
  return known[status] ? t(known[status]) : status;
}
