import { useState, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import {
  Activity,
  ArrowRight,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Flag,
  Gauge,
  Info,
  Printer,
  RefreshCw,
  Route,
  Sparkles,
  Target,
  Timer,
  TrendingUp,
  Trophy,
  type LucideIcon,
} from "lucide-react";

import type {
  GoalProgress,
  PlannedRace,
  ProgressHighlight,
  Report,
  ReportNarrative,
  ReportPeriod,
  SportTotal,
} from "@/api/client";
import { useReport } from "@/api/queries";
import { ProgressWeeksChart, WeeklyLoadChart, WeeklyVolumeChart } from "@/components/Charts";
import { AnalysisWarnings, DIMENSION_META, LoadPanel } from "@/components/analysis";
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
  formatDelta,
  formatDistance,
  formatDuration,
  formatElevation,
  formatNumber,
  formatPace,
  formatPercent,
  parseUtc,
  toISODate,
} from "@/lib/format";

const DISTANCE_KEYS: Array<{ meters: number; label: MessageKey }> = [
  { meters: 5000, label: "distance.5k" },
  { meters: 10000, label: "distance.10k" },
  { meters: 21097.5, label: "distance.half_marathon" },
  { meters: 42195, label: "distance.marathon" },
];

const NOTE_KEYS: Record<string, MessageKey> = {
  load_is_estimated: "reports.notes.load_is_estimated",
  not_medical_advice: "reports.notes.not_medical_advice",
  no_previous_period: "reports.notes.no_previous_period",
  race_in_period: "reports.notes.race_in_period",
  goal_missing: "reports.notes.goal_missing",
  no_sessions_in_period: "reports.notes.no_sessions_in_period",
  narrative_is_derived: "reports.notes.narrative_is_derived",
  limitation_is_current: "reports.notes.limitation_is_current",
};

const NARRATIVE_REASON_KEYS: Record<string, MessageKey> = {
  volume_fallback: "reports.narrative.reason.volume_fallback",
  no_fitness_points: "reports.narrative.reason.no_fitness_points",
  small_fitness_history: "reports.narrative.reason.small_fitness_history",
  limitation_is_current: "reports.narrative.reason.limitation_is_current",
  no_measurable_improvement: "reports.narrative.reason.no_measurable_improvement",
};

const GOAL_STATUS_KEYS: Record<string, MessageKey> = {
  ahead: "progress.goal.status.ahead",
  close: "progress.goal.status.close",
  behind: "progress.goal.status.behind",
  unknown: "progress.goal.status.unknown",
};

const READINESS_KEYS: Record<string, MessageKey> = {
  ahead: "progress.race.readiness.ahead",
  on_track: "progress.race.readiness.on_track",
  close: "progress.race.readiness.close",
  behind: "progress.race.readiness.behind",
  no_goal: "progress.race.readiness.no_goal",
  unknown: "progress.race.readiness.unknown",
};

const SPORT_KEYS: Record<string, MessageKey> = {
  running: "sport.running",
  trail_running: "sport.trail_running",
  treadmill_running: "sport.treadmill_running",
  track_running: "sport.track_running",
  indoor_running: "sport.indoor_running",
  virtual_run: "sport.virtual_run",
  cycling: "sport.cycling",
  walking: "sport.walking",
  hiking: "sport.hiking",
  swimming: "sport.swimming",
  strength_training: "sport.strength_training",
  other: "sport.other",
};

const HIGHLIGHT_KEYS: Record<string, MessageKey> = {
  biggest_week: "progress.highlight.biggest_week",
  longest_run: "progress.highlight.longest_run",
  most_elevation: "progress.highlight.most_elevation",
  fastest_5k: "progress.highlight.fastest_5k",
};

function distanceName(
  meters: number,
  units: Units,
  locale: Locale,
): { key: MessageKey | null; text: string } {
  const match = DISTANCE_KEYS.find(
    (item) => Math.abs(item.meters - meters) / item.meters <= 0.01,
  );
  return {
    key: match?.label ?? null,
    text: formatDistance(meters, units, locale, { digits: 1 }),
  };
}

function shiftDate(value: string, period: ReportPeriod, direction: number): string {
  const date = parseUtc(value);
  if (period === "week") {
    date.setDate(date.getDate() + direction * 7);
  } else {
    date.setDate(1);
    date.setMonth(date.getMonth() + direction);
  }
  return toISODate(date);
}

function rangeLabel(report: Report, locale: Locale): string {
  return `${formatDate(report.start, locale, {
    day: "numeric",
    month: "short",
    year: "numeric",
  })} – ${formatDate(report.end, locale, {
    day: "numeric",
    month: "short",
    year: "numeric",
  })}`;
}

export function ReportsPage() {
  const { t, locale, units } = useI18n();
  const [period, setPeriod] = useState<ReportPeriod>("week");
  const [anchor, setAnchor] = useState(() => toISODate(new Date()));
  const report = useReport(period, anchor);

  if (report.isLoading) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow={t("reports.page.eyebrow")} title={t("reports.page.title")} />
        <div className="analysis-skeleton">
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
        </div>
      </div>
    );
  }

  if (report.isError || !report.data) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow={t("reports.page.eyebrow")}
          title={t("reports.page.title")}
          description={t("reports.page.subtitle")}
        />
        <ErrorState
          message={report.error instanceof Error ? report.error.message : t("reports.error")}
          onRetry={() => void report.refetch()}
        />
      </div>
    );
  }

  const data = report.data;
  const isEmpty = data.totals.sessions === 0;

  return (
    <div className="page-stack reports-page">
      <PageHeader
        eyebrow={t("reports.page.eyebrow")}
        title={t("reports.page.title")}
        description={t("reports.page.subtitle")}
        actions={
          <div className="reports-actions">
            <div className="segmented" role="group" aria-label={t("reports.period.week")}>
              {(["week", "month"] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  className={cn(period === value && "is-active")}
                  aria-pressed={period === value}
                  onClick={() => setPeriod(value)}
                >
                  {t(`reports.period.${value}` as MessageKey)}
                </button>
              ))}
            </div>
            <div className="calendar-nav" role="group" aria-label={t("reports.actions.prev")}>
              <Button
                variant="secondary"
                size="icon"
                aria-label={t("reports.actions.prev")}
                onClick={() => setAnchor(shiftDate(anchor, period, -1))}
              >
                <ChevronLeft size={17} aria-hidden="true" />
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setAnchor(toISODate(new Date()))}
              >
                {t("reports.actions.today")}
              </Button>
              <Button
                variant="secondary"
                size="icon"
                aria-label={t("reports.actions.next")}
                onClick={() => setAnchor(shiftDate(anchor, period, 1))}
              >
                <ChevronRight size={17} aria-hidden="true" />
              </Button>
            </div>
            <Button
              variant="secondary"
              size="sm"
              loading={report.isFetching}
              onClick={() => void report.refetch()}
            >
              <RefreshCw size={15} aria-hidden="true" />
              {t("reports.actions.refresh")}
            </Button>
            <Button variant="secondary" size="sm" onClick={() => window.print()}>
              <Printer size={15} aria-hidden="true" />
              {t("reports.actions.print")}
            </Button>
            <Link to="/progress" className="button button--secondary button--sm">
              <ArrowRight size={15} aria-hidden="true" />
              {t("calendar.actions.progress")}
            </Link>
          </div>
        }
      />

      <AnalysisWarnings warnings={data.warnings} />

      <Card className="panel report-hero">
        <div className="report-hero__head">
          <div>
            <span className="eyebrow">{t(`reports.period.${data.period}` as MessageKey)}</span>
            <h2>{rangeLabel(data, locale)}</h2>
            <p>
              {t("reports.generated")}{" "}
              {formatDate(data.generated_at, locale, {
                day: "numeric",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </p>
          </div>
          <Badge tone={isEmpty ? "warning" : "accent"} dot>
            {isEmpty ? t("reports.empty.title") : data.label}
          </Badge>
        </div>

        <div className="report-metrics">
          <ReportMetric
            icon={Route}
            label={t("reports.totals.distance")}
            value={formatDistance(data.totals.distance_m, units, locale, { digits: 1 })}
            delta={data.delta.distance_pct}
          />
          <ReportMetric
            icon={Activity}
            label={t("reports.totals.sessions")}
            value={formatNumber(data.totals.sessions, locale)}
            delta={data.delta.sessions_pct}
          />
          <ReportMetric
            icon={Clock3}
            label={t("reports.totals.duration")}
            value={formatDuration(data.totals.duration_s, locale)}
            delta={data.delta.duration_pct}
          />
          <ReportMetric
            icon={CalendarDays}
            label={t("reports.totals.activeDays")}
            value={formatNumber(data.totals.active_days, locale)}
            delta={data.delta.active_days_pct}
          />
          <ReportMetric
            icon={Gauge}
            label={t("reports.totals.load")}
            value={formatNumber(data.totals.load, locale)}
            delta={data.delta.load_pct}
          />
          <ReportMetric
            icon={TrendingUp}
            label={t("reports.totals.elevation")}
            value={formatElevation(data.totals.elevation_gain_m, units, locale)}
          />
        </div>

        {data.previous.sessions > 0 ? (
          <p className="report-hero__previous">
            {t("reports.delta.vsPrevious")}:{" "}
            {formatDistance(data.previous.distance_m, units, locale, { digits: 1 })} ·{" "}
            {formatNumber(data.previous.sessions, locale)} {t("progress.stats.sessions")}
          </p>
        ) : (
          <p className="report-hero__previous">{t("reports.notes.no_previous_period")}</p>
        )}
      </Card>

      <ReportNarrativeCard narrative={data.narrative} locale={locale} />

      {isEmpty ? (
        <Card className="panel">
          <EmptyState
            icon={CalendarDays}
            title={t("reports.empty.title")}
            description={t("reports.empty.body")}
            action={
              <Link to="/imports" className="button button--primary button--sm">
                {t("analysis.actions.import")}
              </Link>
            }
          />
        </Card>
      ) : null}

      <section className="reports-duo">
        <Card className="panel report-chart-card">
          <SectionHeading
            title={t("reports.volume.title")}
            subtitle={t("reports.volume.subtitle")}
            icon={TrendingUp}
          />
          {data.period === "week" ? (
            <WeeklyVolumeChart days={data.days ?? []} />
          ) : (
            <ProgressWeeksChart weeks={data.weeks ?? []} />
          )}
        </Card>
        <Card className="panel report-load-card">
          <LoadPanel load={data.load} />
          <WeeklyLoadChart load={data.load} />
        </Card>
      </section>

      <section className="reports-duo">
        <Card className="panel">
          <SectionHeading
            title={t("reports.bySport.title")}
            subtitle={t("reports.bySport.subtitle")}
            icon={Activity}
          />
          {(data.by_sport ?? []).length === 0 ? (
            <p className="analysis-empty">{t("reports.empty.body")}</p>
          ) : (
            <div className="report-sport-list">
              {(data.by_sport ?? []).map((sport) => (
                <SportRow
                  key={sport.sport}
                  sport={sport}
                  total={data.totals.distance_m}
                  locale={locale}
                  units={units}
                />
              ))}
            </div>
          )}
        </Card>

        <Card className="panel">
          <SectionHeading
            title={t("reports.highlights.title")}
            icon={Sparkles}
          />
          {(data.highlights ?? []).length === 0 ? (
            <p className="analysis-empty">{t("reports.empty.body")}</p>
          ) : (
            <div className="highlight-list">
              {(data.highlights ?? []).map((highlight) => (
                <HighlightRow
                  key={highlight.key}
                  highlight={highlight}
                  locale={locale}
                  units={units}
                />
              ))}
            </div>
          )}
        </Card>
      </section>

      <section className="reports-duo">
        <Card className="panel">
          <SectionHeading
            title={t("reports.goals.title")}
            subtitle={t("reports.goals.subtitle")}
            icon={Target}
            action={
              <Link to="/performance" className="badge badge--info">
                {t("progress.goals.link")}
              </Link>
            }
          />
          {(data.goals ?? []).length === 0 ? (
            <p className="analysis-empty">{t("reports.noGoals")}</p>
          ) : (
            <div className="report-goal-list">
              {(data.goals ?? []).map((goal) => (
                <ReportGoalRow
                  key={`${goal.distance_key ?? goal.distance_m}`}
                  goal={goal}
                  locale={locale}
                  units={units}
                />
              ))}
            </div>
          )}
        </Card>

        <Card className="panel">
          <SectionHeading
            title={t("reports.races.title")}
            subtitle={t("reports.races.subtitle")}
            icon={Flag}
          />
          {(data.races ?? []).length === 0 ? (
            <p className="analysis-empty">{t("reports.noRaces")}</p>
          ) : (
            <div className="report-race-list">
              {(data.races ?? []).map((race) => (
                <ReportRaceRow key={race.id} race={race} locale={locale} units={units} />
              ))}
            </div>
          )}
        </Card>
      </section>

      <Card className="panel report-notes">
        <SectionHeading title={t("reports.notes.title")} icon={Info} />
        <ul className="notes-list">
          {(data.notes ?? []).map((note) => (
            <li key={note}>
              <Info size={14} aria-hidden="true" />
              <span>{NOTE_KEYS[note] ? t(NOTE_KEYS[note]) : note}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function ReportNarrativeCard({
  narrative,
  locale,
}: {
  narrative: ReportNarrative;
  locale: Locale;
}) {
  const { t } = useI18n();
  const dimension = narrative.limitation ? DIMENSION_META[narrative.limitation] : null;
  const improvement =
    narrative.improvement === "fitness" && narrative.fitness_change_pct != null
      ? t("reports.narrative.improvement.fitness", {
          change: formatClock(Math.abs(narrative.fitness_change_s ?? 0)),
          pct: formatPercent(Math.abs(narrative.fitness_change_pct), locale, 1),
        })
      : narrative.improvement === "volume" && narrative.volume_delta_pct != null
        ? t("reports.narrative.improvement.volume", {
            pct: formatPercent(narrative.volume_delta_pct, locale, 1),
          })
        : t("reports.narrative.improvement.none");
  const limitation = dimension
    ? t(dimension.label)
    : t("reports.narrative.limitation.none");
  const action = narrative.action
    ? t(`training.focus.action.${narrative.action}` as MessageKey)
    : t("training.focus.action.maintain_balance");
  const reasons = (narrative.reasons ?? []).filter((reason) => NARRATIVE_REASON_KEYS[reason]);
  const fitnessPoints = Number(narrative.evidence?.fitness_points ?? 0);
  const volumeDelta = narrative.evidence?.volume_delta_pct;
  const limiterScore = narrative.evidence?.limiter_score;
  const tone =
    narrative.tone === "positive"
      ? "success"
      : narrative.tone === "warning" || narrative.tone === "danger"
        ? "warning"
        : "neutral";

  return (
    <Card className={cn("panel report-narrative", `report-narrative--${narrative.tone}`)}>
      <div className="report-narrative__head">
        <div>
          <span className="eyebrow">{t("reports.narrative.title")}</span>
          <h2>{t(`reports.narrative.key.${narrative.key}` as MessageKey)}</h2>
          <p>{t("reports.narrative.subtitle")}</p>
        </div>
        <div className="report-narrative__confidence">
          <Badge tone={tone}>
            {t("reports.narrative.confidence", {
              score: Math.round(narrative.confidence_score * 100),
            })}
          </Badge>
          <ProgressBar
            value={narrative.confidence_score * 100}
            tone={
              narrative.confidence === "high"
                ? "accent"
                : narrative.confidence === "medium"
                  ? "warning"
                  : "danger"
            }
          />
        </div>
      </div>

      <div className="report-narrative__grid">
        <NarrativeBlock icon={TrendingUp} title={t("reports.narrative.improvement.title")}>
          {improvement}
        </NarrativeBlock>
        <NarrativeBlock
          icon={Target}
          title={t("reports.narrative.limitation.title")}
          note={
            narrative.limitation ? t("reports.narrative.limitation.current") : undefined
          }
        >
          {limitation}
          {limiterScore != null ? (
            <small className="report-narrative__score">{Math.round(Number(limiterScore))}/100</small>
          ) : null}
        </NarrativeBlock>
        <NarrativeBlock
          icon={Sparkles}
          title={t("reports.narrative.action.title")}
          note={t("reports.narrative.action.note")}
        >
          {action}
        </NarrativeBlock>
      </div>

      <div className="report-narrative__evidence">
        <span className="eyebrow">{t("reports.narrative.evidence")}</span>
        <div className="report-narrative__chips">
          {fitnessPoints > 0 ? (
            <span className="reason-chip">
              {t(
                fitnessPoints === 1
                  ? "reports.narrative.evidence.fitnessPointsOne"
                  : "reports.narrative.evidence.fitnessPoints",
                { count: fitnessPoints },
              )}
            </span>
          ) : null}
          {volumeDelta != null ? (
            <span className="reason-chip">
              {t("reports.narrative.evidence.volumeDelta", {
                pct: formatPercent(Number(volumeDelta), locale, 1),
              })}
            </span>
          ) : null}
          {limiterScore != null && dimension ? (
            <span className="reason-chip">
              {t(dimension.label)} {Math.round(Number(limiterScore))}/100
            </span>
          ) : null}
        </div>
      </div>

      {reasons.length ? (
        <ul className="report-narrative__reasons">
          {reasons.map((reason) => (
            <li key={reason}>{t(NARRATIVE_REASON_KEYS[reason])}</li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}

function NarrativeBlock({
  icon: Icon,
  title,
  note,
  children,
}: {
  icon: LucideIcon;
  title: string;
  note?: string;
  children: ReactNode;
}) {
  return (
    <div className="report-narrative__block">
      <span className="report-narrative__icon">
        <Icon size={16} aria-hidden="true" />
      </span>
      <div>
        <h3>{title}</h3>
        <p>{children}</p>
        {note ? <small>{note}</small> : null}
      </div>
    </div>
  );
}

function ReportMetric({
  icon: Icon,
  label,
  value,
  delta,
}: {
  icon: typeof Route;
  label: string;
  value: string;
  delta?: number | null;
}) {
  const { locale } = useI18n();
  const formatted = formatDelta(delta, locale);
  return (
    <div className="report-metric">
      <span className="report-metric__icon">
        <Icon size={15} aria-hidden="true" />
      </span>
      <span className="report-metric__label">{label}</span>
      <strong>{value}</strong>
      {formatted ? (
        <small className={cn("report-metric__delta", (delta ?? 0) > 0 ? "is-up" : "is-down")}>
          {formatted}
        </small>
      ) : null}
    </div>
  );
}

function SportRow({
  sport,
  total,
  locale,
  units,
}: {
  sport: SportTotal;
  total: number;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  const share = total > 0 ? (sport.distance_m / total) * 100 : 0;
  const label = SPORT_KEYS[sport.sport];
  return (
    <div className="report-sport">
      <div className="report-sport__head">
        <strong>{label ? t(label) : sport.sport}</strong>
        <span>
          {sport.activities === 1
            ? t("reports.sport.oneSession", { count: sport.activities })
            : t("reports.sport.sessions", { count: sport.activities })}{" "}
          · {formatDistance(sport.distance_m, units, locale, { digits: 1 })}
        </span>
      </div>
      <ProgressBar value={share} label={sport.sport} />
      <div className="report-sport__meta">
        <span>{formatNumber(share, locale, 0)}%</span>
        <span>{formatDuration(sport.duration_s, locale)}</span>
      </div>
    </div>
  );
}

function ReportGoalRow({
  goal,
  locale,
  units,
}: {
  goal: GoalProgress;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  const status = GOAL_STATUS_KEYS[goal.status] ?? GOAL_STATUS_KEYS.unknown;
  const distance = distanceName(goal.distance_m, units, locale);
  return (
    <div className="report-goal">
      <div>
        <strong>{distance.key ? t(distance.key) : distance.text}</strong>
        <span>
          {t("progress.goal.target")} {formatClock(goal.target_time_s)} ·{" "}
          {t("progress.goal.predicted")} {formatClock(goal.current_time_s)}
        </span>
      </div>
      <Badge
        tone={
          goal.status === "ahead"
            ? "success"
            : goal.status === "close"
              ? "warning"
              : goal.status === "behind"
                ? "danger"
                : "neutral"
        }
      >
        {t(status)}
      </Badge>
    </div>
  );
}

function ReportRaceRow({
  race,
  locale,
  units,
}: {
  race: PlannedRace;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  return (
    <div className="report-race">
      <div>
        <strong>{race.name}</strong>
        <span>
          {formatDate(race.race_date, locale)} ·{" "}
          {formatDistance(race.distance_m, units, locale, { digits: 1 })}
        </span>
      </div>
      <div className="report-race__meta">
        <Badge tone={race.priority === "A" ? "accent" : "neutral"}>{race.priority}</Badge>
        <Badge
          tone={
            race.status === "completed"
              ? "success"
              : race.status === "cancelled"
                ? "warning"
                : "neutral"
          }
        >
          {t(`progress.race.status.${race.status}` as MessageKey)}
        </Badge>
        <span>
          {READINESS_KEYS[race.readiness] ? t(READINESS_KEYS[race.readiness]) : race.readiness}
        </span>
        {race.target_pace_s_per_km ? (
          <small>{formatPace(race.target_pace_s_per_km, units)}</small>
        ) : null}
      </div>
    </div>
  );
}

function HighlightRow({
  highlight,
  locale,
  units,
}: {
  highlight: ProgressHighlight;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  const label = HIGHLIGHT_KEYS[highlight.key];
  let value = formatNumber(highlight.value, locale, 1);
  let icon = Trophy;
  if (highlight.key === "fastest_5k") {
    value = formatClock(highlight.value);
    icon = Timer;
  } else if (highlight.key === "most_elevation") {
    value = formatElevation(highlight.value, units, locale);
    icon = TrendingUp;
  } else if (highlight.key === "biggest_week" || highlight.key === "longest_run") {
    value = formatDistance(highlight.value, units, locale, { digits: 1 });
    icon = Route;
  }
  const Icon = icon;

  return (
    <div className="highlight-row">
      <span className="highlight-row__icon">
        <Icon size={15} aria-hidden="true" />
      </span>
      <div>
        <span>{label ? t(label) : highlight.key}</span>
        {highlight.date ? <small>{formatDate(highlight.date, locale)}</small> : null}
      </div>
      <strong>{value}</strong>
    </div>
  );
}
