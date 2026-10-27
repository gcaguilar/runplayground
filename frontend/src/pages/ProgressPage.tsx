import { useState, type FormEvent } from "react";
import { Link } from "@tanstack/react-router";
import {
  Activity,
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  Flag,
  Gauge,
  MapPin,
  Pencil,
  Plus,
  RefreshCw,
  Route,
  Sparkles,
  Target,
  Timer,
  Trash2,
  TrendingUp,
  Trophy,
  type LucideIcon,
} from "lucide-react";

import type {
  GoalProgress,
  PersonalBest,
  PlannedRace,
  PlannedRaceCreate,
  PlannedRaceUpdate,
  ProgressHighlight,
} from "@/api/client";
import {
  useCreateRace,
  useDeleteRace,
  useProgress,
  useRaces,
  useUpdateRace,
} from "@/api/queries";
import { FitnessTrendChart, ProgressWeeksChart } from "@/components/Charts";
import {
  AnalysisMethodCard,
  AnalysisWarnings,
} from "@/components/analysis";
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
  formatElevation,
  formatNumber,
  formatPace,
  parseTimeInput,
  toISODate,
} from "@/lib/format";

const PHASE_KEYS: Record<string, MessageKey> = {
  maintenance: "training.phase.maintenance",
  base: "training.phase.base",
  build: "training.phase.build",
  peak: "training.phase.peak",
  taper: "training.phase.taper",
  recovery: "training.phase.recovery",
};

const READINESS_TONE: Record<string, "neutral" | "accent" | "success" | "warning" | "danger"> = {
  ahead: "success",
  on_track: "accent",
  close: "warning",
  behind: "danger",
  no_goal: "neutral",
  unknown: "neutral",
};

const READINESS_KEYS: Record<string, MessageKey> = {
  ahead: "progress.race.readiness.ahead",
  on_track: "progress.race.readiness.on_track",
  close: "progress.race.readiness.close",
  behind: "progress.race.readiness.behind",
  no_goal: "progress.race.readiness.no_goal",
  unknown: "progress.race.readiness.unknown",
};

const PRIORITY_LABELS: Record<string, MessageKey> = {
  A: "progress.race.priority.A",
  B: "progress.race.priority.B",
  C: "progress.race.priority.C",
};

const GOAL_STATUS_KEYS: Record<string, MessageKey> = {
  ahead: "progress.goal.status.ahead",
  close: "progress.goal.status.close",
  behind: "progress.goal.status.behind",
  unknown: "progress.goal.status.unknown",
};

const GOAL_STATUS_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  ahead: "success",
  close: "warning",
  behind: "danger",
  unknown: "neutral",
};

const HIGHLIGHT_KEYS: Record<string, MessageKey> = {
  biggest_week: "progress.highlight.biggest_week",
  longest_run: "progress.highlight.longest_run",
  most_elevation: "progress.highlight.most_elevation",
  fastest_5k: "progress.highlight.fastest_5k",
};

const WINDOWS = [90, 180, 365] as const;

const DISTANCE_PRESETS = [
  { key: "5k", meters: 5000, label: "distance.5k" as MessageKey },
  { key: "10k", meters: 10000, label: "distance.10k" as MessageKey },
  { key: "half_marathon", meters: 21097.5, label: "distance.half_marathon" as MessageKey },
  { key: "marathon", meters: 42195, label: "distance.marathon" as MessageKey },
] as const;

type Priority = "A" | "B" | "C";

function presetKey(distanceM: number): string {
  const match = DISTANCE_PRESETS.find(
    (preset) => Math.abs(preset.meters - distanceM) / preset.meters <= 0.01,
  );
  return match?.key ?? "custom";
}

function standardLabel(distanceM: number): MessageKey | null {
  const match = DISTANCE_PRESETS.find(
    (preset) => Math.abs(preset.meters - distanceM) / preset.meters <= 0.01,
  );
  return match?.label ?? null;
}

export function ProgressPage() {
  const { t, locale, units } = useI18n();
  const [days, setDays] = useState<number>(180);
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const progress = useProgress(days);
  const races = useRaces();

  if (progress.isLoading) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow={t("progress.page.eyebrow")} title={t("progress.page.title")} />
        <div className="analysis-skeleton">
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
        </div>
      </div>
    );
  }

  if (progress.isError || !progress.data) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow={t("progress.page.eyebrow")}
          title={t("progress.page.title")}
          description={t("progress.page.subtitle")}
        />
        <ErrorState
          message={
            progress.error instanceof Error ? progress.error.message : t("progress.error")
          }
          onRetry={() => void progress.refetch()}
        />
      </div>
    );
  }

  const data = progress.data;
  const raceList = races.data ?? data.races;
  const orderedRaces = sortRaces(raceList);
  const insufficient = data.status === "insufficient" && data.totals.sessions === 0;

  return (
    <div className="page-stack progress-page">
      <PageHeader
        eyebrow={t("progress.page.eyebrow")}
        title={t("progress.page.title")}
        description={t("progress.page.subtitle")}
        actions={
          <div className="progress-actions">
            <div className="segmented" role="group" aria-label={t("progress.window.label")}>
              {WINDOWS.map((value) => (
                <button
                  key={value}
                  type="button"
                  className={cn(days === value && "is-active")}
                  aria-pressed={days === value}
                  onClick={() => setDays(value)}
                >
                  {t(`progress.window.${value}` as MessageKey)}
                </button>
              ))}
            </div>
            <Button
              variant="secondary"
              size="sm"
              loading={progress.isFetching}
              onClick={() => void progress.refetch()}
            >
              <RefreshCw size={15} aria-hidden="true" />
              {t("analysis.actions.refresh")}
            </Button>
            <Link to="/calendar" className="button button--secondary button--sm">
              <CalendarDays size={15} aria-hidden="true" />
              {t("progress.actions.calendar")}
            </Link>
            <Link to="/reports" className="button button--secondary button--sm">
              <ArrowRight size={15} aria-hidden="true" />
              {t("progress.actions.reports")}
            </Link>
          </div>
        }
      />

      <AnalysisWarnings warnings={data.warnings} />

      <section className="stat-grid progress-stats">
        <ProgressStat
          icon={Route}
          label={t("progress.stats.distance")}
          value={formatDistance(data.totals.distance_m, units, locale, { digits: 1 })}
          delta={data.delta.distance_pct}
          previous={data.previous.distance_m}
        />
        <ProgressStat
          icon={Activity}
          label={t("progress.stats.sessions")}
          value={formatNumber(data.totals.sessions, locale)}
          delta={data.delta.sessions_pct}
          previous={data.previous.sessions}
        />
        <ProgressStat
          icon={CalendarDays}
          label={t("progress.stats.activeDays")}
          value={formatNumber(data.totals.active_days, locale)}
          delta={data.delta.active_days_pct}
          previous={data.previous.active_days}
        />
        <ProgressStat
          icon={Gauge}
          label={t("progress.stats.load")}
          value={formatNumber(data.totals.load, locale)}
          delta={data.delta.load_pct}
          previous={data.previous.load}
        />
      </section>

      {insufficient ? (
        <Card className="panel">
          <EmptyState
            icon={TrendingUp}
            title={t("progress.weekly.empty")}
            description={t("progress.page.subtitle")}
            action={
              <Link to="/imports" className="button button--primary button--sm">
                <Plus size={15} aria-hidden="true" />
                {t("analysis.actions.import")}
              </Link>
            }
          />
        </Card>
      ) : null}

      <section className="progress-duo">
        <Card className="panel progress-chart-card">
          <SectionHeading
            title={t("progress.weekly.title")}
            subtitle={t("progress.weekly.subtitle")}
            icon={TrendingUp}
            action={<Badge tone="info">{t(`progress.window.${days}` as MessageKey)}</Badge>}
          />
          <ProgressWeeksChart weeks={data.weeks} />
        </Card>
        <Card className="panel progress-chart-card">
          <SectionHeading
            title={t("progress.fitness.title")}
            subtitle={t("progress.fitness.subtitle")}
            icon={Gauge}
          />
          <FitnessTrendChart points={data.fitness} />
        </Card>
      </section>

      <section className="progress-duo">
        <Card className="panel progress-consistency">
          <SectionHeading
            title={t("progress.consistency.title")}
            subtitle={t("progress.consistency.subtitle")}
            icon={CalendarDays}
          />
          <div className="progress-metrics">
            <MetricTile
              label={t("progress.consistency.activeDays")}
              value={formatNumber(data.consistency.active_days, locale)}
            />
            <MetricTile
              label={t("progress.consistency.currentStreak")}
              value={t(streakKey(data.consistency.current_streak_days), {
                days: data.consistency.current_streak_days,
              })}
            />
            <MetricTile
              label={t("progress.consistency.longestStreak")}
              value={t(streakKey(data.consistency.longest_streak_days), {
                days: data.consistency.longest_streak_days,
              })}
            />
            <MetricTile
              label={t("progress.consistency.bestWeek")}
              value={formatDistance(data.consistency.best_week_m, units, locale, {
                digits: 1,
              })}
            />
          </div>
          <div className="progress-consistency__bar">
            <div className="progress-consistency__head">
              <span>{t("progress.consistency.avgWeek")}</span>
              <strong>
                {formatDistance(data.consistency.weekly_average_m, units, locale, {
                  digits: 1,
                })}
              </strong>
            </div>
            <ProgressBar
              value={
                data.consistency.best_week_m > 0
                  ? (data.consistency.weekly_average_m / data.consistency.best_week_m) * 100
                  : 0
              }
              label={t("progress.consistency.progress")}
            />
          </div>
          <p className="analysis-note">
            {t("progress.consistency.weeksWithData", {
              active: data.consistency.weeks_with_data,
              total: data.consistency.weeks,
            })}
          </p>
        </Card>

        <Card className="panel progress-goals">
          <SectionHeading
            title={t("progress.goals.title")}
            subtitle={t("progress.goals.subtitle")}
            icon={Target}
            action={
              <Link to="/performance" className="badge badge--info">
                {t("progress.goals.link")}
              </Link>
            }
          />
          {data.goals.length === 0 ? (
            <EmptyState
              compact
              icon={Target}
              title={t("progress.goals.empty")}
              description={t("progress.goals.emptyBody")}
            />
          ) : (
            <div className="goal-progress-list">
              {data.goals.map((goal) => (
                <GoalProgressCard
                  key={`${goal.distance_key ?? goal.distance_m}`}
                  goal={goal}
                  locale={locale}
                  units={units}
                />
              ))}
            </div>
          )}
        </Card>
      </section>

      <section className="progress-duo">
        <Card className="panel progress-bests">
          <SectionHeading
            title={t("progress.pb.title")}
            subtitle={t("progress.pb.subtitle")}
            icon={Trophy}
          />
          {data.best_efforts.length === 0 ? (
            <EmptyState
              compact
              icon={Trophy}
              title={t("progress.pb.empty")}
              description={t("progress.pb.emptyBody")}
            />
          ) : (
            <div className="best-effort-list">
              {data.best_efforts.map((best) => (
                <BestEffortRow
                  key={best.distance_key}
                  best={best}
                  locale={locale}
                  units={units}
                />
              ))}
            </div>
          )}
        </Card>

        <Card className="panel progress-highlights">
          <SectionHeading title={t("progress.highlight.title")} icon={Sparkles} />
          {data.highlights.length === 0 ? (
            <p className="analysis-empty">{t("progress.pb.emptyBody")}</p>
          ) : (
            <div className="highlight-list">
              {data.highlights.map((highlight) => (
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

      <Card className="panel progress-races">
        <SectionHeading
          title={t("progress.races.title")}
          subtitle={t("progress.races.subtitle")}
          icon={Flag}
          action={
            <Button
              variant="primary"
              size="sm"
              onClick={() => setEditing(editing === "new" ? null : "new")}
            >
              <Plus size={15} aria-hidden="true" />
              {t("progress.races.add")}
            </Button>
          }
        />

        {editing === "new" ? (
          <RaceForm key="new" onClose={() => setEditing(null)} />
        ) : null}

        {orderedRaces.length === 0 && editing !== "new" ? (
          <EmptyState
            icon={Flag}
            title={t("progress.races.empty")}
            description={t("progress.races.emptyBody")}
            action={
              <Button variant="secondary" size="sm" onClick={() => setEditing("new")}>
                <Plus size={15} aria-hidden="true" />
                {t("progress.races.add")}
              </Button>
            }
          />
        ) : (
          <div className="race-plan-list">
            {orderedRaces.map((race) =>
              editing === race.id ? (
                <RaceForm key={`edit-${race.id}`} race={race} onClose={() => setEditing(null)} />
              ) : (
                <RaceCard
                  key={race.id}
                  race={race}
                  locale={locale}
                  units={units}
                  onEdit={() => setEditing(race.id)}
                />
              ),
            )}
          </div>
        )}
      </Card>

      <AnalysisMethodCard
        title={t("progress.method.title")}
        subtitle={t("progress.method.subtitle")}
        items={[
          {
            icon: TrendingUp,
            title: t("progress.method.model.title"),
            body: t("progress.method.model.body"),
          },
          {
            icon: CalendarDays,
            title: t("progress.method.calendar.title"),
            body: t("progress.method.calendar.body"),
          },
          {
            icon: Flag,
            title: t("progress.method.races.title"),
            body: t("progress.method.races.body"),
          },
        ]}
      />
    </div>
  );
}

function streakKey(days: number): MessageKey {
  return days === 1 ? "progress.consistency.oneDay" : "progress.consistency.days";
}

function goalGapLabel(
  gap: number,
  t: ReturnType<typeof useI18n>["t"],
): string {
  // The API returns goal time minus forecast: negative means the goal is
  // faster than the forecast, so the athlete is behind it.
  return gap >= 0
    ? t("progress.goal.gapAhead", { gap: formatClock(gap) })
    : t("progress.goal.gapBehind", { gap: formatClock(Math.abs(gap)) });
}

function sortRaces(races: PlannedRace[]): PlannedRace[] {
  const today = toISODate(new Date());
  return [...races].sort((left, right) => {
    const leftUpcoming =
      left.status === "planned" && left.race_date >= today ? 0 : 1;
    const rightUpcoming =
      right.status === "planned" && right.race_date >= today ? 0 : 1;
    if (leftUpcoming !== rightUpcoming) return leftUpcoming - rightUpcoming;
    if (leftUpcoming === 0) return left.race_date.localeCompare(right.race_date);
    return right.race_date.localeCompare(left.race_date);
  });
}

function ProgressStat({
  icon: Icon,
  label,
  value,
  delta,
  previous,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  delta: number | null | undefined;
  previous: number;
}) {
  const { locale, t } = useI18n();
  const formattedDelta = formatDelta(delta, locale);
  const hasDelta = formattedDelta !== null;
  const isUp = (delta ?? 0) > 0;

  return (
    <Card className="stat-card" as="article">
      <div className="stat-card__top">
        <span className="stat-card__label">{label}</span>
        <span className="stat-card__icon">
          <Icon size={16} aria-hidden="true" />
        </span>
      </div>
      <span className="stat-card__value">{value}</span>
      <div className="stat-card__bottom">
        {hasDelta ? (
          <span className={cn("progress-delta", isUp ? "is-up" : "is-down")}>
            {formattedDelta}
          </span>
        ) : (
          <span className="progress-delta is-neutral">—</span>
        )}
        <span className="stat-card__footnote">
          {previous > 0 ? t("progress.delta.vsPrevious") : t("progress.delta.noPrevious")}
        </span>
      </div>
    </Card>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="progress-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function GoalProgressCard({
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
  const tone = GOAL_STATUS_TONE[goal.status] ?? "neutral";
  const gap = goal.gap_s;

  return (
    <article className="goal-progress">
      <div className="goal-progress__head">
        <div>
          <strong>
            {(() => {
              const label = standardLabel(goal.distance_m);
              return label
                ? t(label)
                : formatDistance(goal.distance_m, units, locale, { digits: 1 });
            })()}
          </strong>
          {goal.race_name ? <span>{goal.race_name}</span> : null}
        </div>
        <Badge tone={tone} dot>
          {t(status)}
        </Badge>
      </div>
      <div className="goal-progress__times">
        <div>
          <span>{t("progress.goal.target")}</span>
          <strong>{formatClock(goal.target_time_s)}</strong>
        </div>
        <div>
          <span>{t("progress.goal.predicted")}</span>
          <strong>{formatClock(goal.current_time_s)}</strong>
        </div>
        <div>
          <span>{t("progress.goal.range")}</span>
          <strong>
            {formatClock(goal.low_s)} – {formatClock(goal.high_s)}
          </strong>
        </div>
      </div>
      {gap !== null && gap !== undefined ? (
        <p className={cn("goal-progress__gap", gap >= 0 ? "is-ahead" : "is-behind")}>
          {goalGapLabel(gap, t)}
        </p>
      ) : null}
      <ProgressBar
        value={goal.readiness_pct ?? 0}
        tone={
          tone === "success"
            ? "accent"
            : tone === "warning"
              ? "warning"
              : tone === "danger"
                ? "danger"
                : "accent"
        }
        label={t("progress.goal.readiness")}
      />
      <div className="goal-progress__foot">
        <span>{t("progress.goal.readiness")}</span>
        <strong>
          {goal.readiness_pct !== null && goal.readiness_pct !== undefined
            ? `${formatNumber(goal.readiness_pct, locale, 1)}%`
            : "—"}
        </strong>
        {goal.target_date ? <span>{formatDate(goal.target_date, locale)}</span> : null}
      </div>
    </article>
  );
}

function BestEffortRow({
  best,
  locale,
  units,
}: {
  best: PersonalBest;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  const label = standardLabel(best.distance_m);
  return (
    <div className="best-effort">
      <div className="best-effort__distance">
        <strong>
          {label ? t(label) : formatDistance(best.distance_m, units, locale, { digits: 1 })}
        </strong>
        {best.is_race ? (
          <Badge tone="accent">
            <Flag size={11} aria-hidden="true" />
            {t("progress.pb.race")}
          </Badge>
        ) : null}
      </div>
      <div className="best-effort__time">{formatClock(best.time_s)}</div>
      <div className="best-effort__pace">
        {formatPace(best.pace_s_per_km, units)}
      </div>
      <div className="best-effort__meta">
        <Link to="/activities/$activityId" params={{ activityId: String(best.activity_id) }}>
          {best.activity_name || `#${best.activity_id}`}
        </Link>
        <span>{formatDate(best.date, locale)}</span>
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
  if (highlight.key === "fastest_5k") value = formatClock(highlight.value);
  else if (highlight.key === "most_elevation") {
    value = formatElevation(highlight.value, units, locale);
  } else if (highlight.key === "biggest_week" || highlight.key === "longest_run") {
    value = formatDistance(highlight.value, units, locale, { digits: 1 });
  }

  return (
    <div className="highlight-row">
      <span className="highlight-row__icon">
        {highlight.key === "fastest_5k" ? (
          <Timer size={15} aria-hidden="true" />
        ) : highlight.key === "most_elevation" ? (
          <TrendingUp size={15} aria-hidden="true" />
        ) : (
          <Route size={15} aria-hidden="true" />
        )}
      </span>
      <div>
        <span>{label ? t(label) : highlight.key}</span>
        {highlight.date ? <small>{formatDate(highlight.date, locale)}</small> : null}
      </div>
      <strong>{value}</strong>
    </div>
  );
}

function RaceCard({
  race,
  locale,
  units,
  onEdit,
}: {
  race: PlannedRace;
  locale: Locale;
  units: Units;
  onEdit: () => void;
}) {
  const { t } = useI18n();
  const remove = useDeleteRace();
  const readiness = READINESS_KEYS[race.readiness] ?? READINESS_KEYS.unknown;
  const tone = READINESS_TONE[race.readiness] ?? "neutral";
  const priority = PRIORITY_LABELS[race.priority] ?? PRIORITY_LABELS.B;

  const handleDelete = () => {
    if (window.confirm(t("progress.race.deleteConfirm", { name: race.name }))) {
      remove.mutate(race.id);
    }
  };

  return (
    <article className={cn("race-plan", `race-plan--${race.priority.toLowerCase()}`)}>
      <div className="race-plan__head">
        <div className="race-plan__title">
          <span className="race-plan__priority">{race.priority}</span>
          <div>
            <strong>{race.name}</strong>
            <span>
              {formatDate(race.race_date, locale)} ·{" "}
              {formatDistance(race.distance_m, units, locale, { digits: 1 })}
              {race.location ? (
                <>
                  {" "}
                  · <MapPin size={11} aria-hidden="true" /> {race.location}
                </>
              ) : null}
            </span>
          </div>
        </div>
        <div className="race-plan__badges">
          <Badge tone={tone} dot>
            {t(readiness)}
          </Badge>
          <Badge tone="neutral">{t(priority)}</Badge>
          {race.status !== "planned" ? (
            <Badge tone="info">
              {t(`progress.race.status.${race.status}` as MessageKey)}
            </Badge>
          ) : null}
        </div>
      </div>

      <div className="race-plan__countdown">
        <div>
          {race.days_to_race !== null && race.days_to_race !== undefined && race.days_to_race >= 0 ? (
            <>
              <span>{t("progress.race.daysTo", { days: race.days_to_race })}</span>
              {race.weeks_to_race !== null && race.weeks_to_race !== undefined ? (
                <small>{t("progress.race.weeksTo", { weeks: race.weeks_to_race })}</small>
              ) : null}
            </>
          ) : (
            <span>{t(`progress.race.status.${race.status}` as MessageKey)}</span>
          )}
        </div>
        {race.phase ? (
          <Badge tone="accent">
            {PHASE_KEYS[race.phase] ? t(PHASE_KEYS[race.phase]) : race.phase}
          </Badge>
        ) : null}
      </div>

      <div className="race-plan__grid">
        <RaceMetric
          icon={Target}
          label={t("progress.race.targetPace")}
          value={formatPace(race.target_pace_s_per_km, units)}
        />
        <RaceMetric
          icon={Gauge}
          label={t("progress.race.predicted")}
          value={formatClock(race.predicted_time_s)}
        />
        <RaceMetric
          icon={TrendingUp}
          label={t("progress.race.weeklyTarget")}
          value={
            race.weekly_distance_low_m !== null && race.weekly_distance_high_m !== null
              ? `${formatDistance(race.weekly_distance_low_m, units, locale, {
                  digits: 0,
                })} – ${formatDistance(race.weekly_distance_high_m, units, locale, {
                  digits: 0,
                })}`
              : "—"
          }
        />
        <RaceMetric
          icon={Route}
          label={t("progress.race.longRun")}
          value={
            race.long_run_low_m !== null && race.long_run_high_m !== null
              ? `${formatDistance(race.long_run_low_m, units, locale, {
                  digits: 0,
                })} – ${formatDistance(race.long_run_high_m, units, locale, {
                  digits: 0,
                })}`
              : "—"
          }
        />
      </div>

      {race.goal_time_s ? (
        <div className="race-plan__goal">
          <span>
            {t("progress.goal.target")}: <strong>{formatClock(race.goal_time_s)}</strong>
          </span>
          {race.gap_s !== null && race.gap_s !== undefined ? (
            <span className={race.gap_s >= 0 ? "is-ahead" : "is-behind"}>
              {goalGapLabel(race.gap_s, t)}
            </span>
          ) : null}
        </div>
      ) : null}

      {race.notes ? <p className="race-plan__notes">{race.notes}</p> : null}

      <div className="race-plan__actions">
        {race.activity_id ? (
          <Link
            to="/activities/$activityId"
            params={{ activityId: String(race.activity_id) }}
            className="badge badge--success"
          >
            <CheckCircle2 size={12} aria-hidden="true" />
            {t("calendar.legend.activity")}
          </Link>
        ) : null}
        <Button variant="ghost" size="sm" onClick={onEdit}>
          <Pencil size={14} aria-hidden="true" />
          {t("progress.race.edit")}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          loading={remove.isPending}
          onClick={handleDelete}
        >
          <Trash2 size={14} aria-hidden="true" />
          {t("progress.race.delete")}
        </Button>
      </div>
    </article>
  );
}

function RaceMetric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Target;
  label: string;
  value: string;
}) {
  return (
    <div className="race-metric">
      <Icon size={13} aria-hidden="true" />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RaceForm({ race, onClose }: { race?: PlannedRace; onClose: () => void }) {
  const { t } = useI18n();
  const create = useCreateRace();
  const update = useUpdateRace();
  const [name, setName] = useState(race?.name ?? "");
  const [raceDate, setRaceDate] = useState(
    race?.race_date ?? toISODate(new Date(Date.now() + 42 * 86_400_000)),
  );
  const [preset, setPreset] = useState(race ? presetKey(race.distance_m) : "10k");
  const [customKm, setCustomKm] = useState(
    race && presetKey(race.distance_m) === "custom"
      ? String(Math.round((race.distance_m / 1000) * 100) / 100)
      : "",
  );
  const [goalTime, setGoalTime] = useState(
    race?.goal_time_s ? formatClock(race.goal_time_s) : "",
  );
  const [priority, setPriority] = useState<Priority>((race?.priority as Priority) ?? "B");
  const [location, setLocation] = useState(race?.location ?? "");
  const [notes, setNotes] = useState(race?.notes ?? "");
  const [problem, setProblem] = useState<string | null>(null);
  const pending = create.isPending || update.isPending;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const standard = DISTANCE_PRESETS.find((item) => item.key === preset);
    const distanceM = standard ? standard.meters : Number(customKm) * 1000;
    if (!name.trim() || !raceDate || !Number.isFinite(distanceM) || distanceM <= 0) {
      setProblem(t("progress.race.required"));
      return;
    }
    let goalTimeS: number | null = null;
    if (goalTime.trim()) {
      goalTimeS = parseTimeInput(goalTime);
      if (goalTimeS === null || goalTimeS > 48 * 3600) {
        setProblem(t("progress.race.invalidTime"));
        return;
      }
    }
    setProblem(null);
    const payload: PlannedRaceCreate = {
      name: name.trim(),
      race_date: raceDate,
      distance_m: Math.round(distanceM * 10) / 10,
      goal_time_s: goalTimeS,
      priority,
      location: location.trim() || null,
      notes: notes.trim() || null,
      status: (race?.status as PlannedRaceCreate["status"]) ?? "planned",
    };
    const onError = (error: unknown) => {
      setProblem(error instanceof Error ? error.message : t("progress.race.error"));
    };
    if (race) {
      update.mutate(
        { id: race.id, patch: payload as PlannedRaceUpdate },
        { onSuccess: onClose, onError },
      );
    } else {
      create.mutate(payload, { onSuccess: onClose, onError });
    }
  };

  return (
    <form className="race-form" onSubmit={submit}>
      <div className="race-form__head">
        <strong>{race ? t("progress.race.editTitle") : t("progress.race.formTitle")}</strong>
        <span>{t("progress.race.goalTimeHint")}</span>
      </div>
      <label>
        <span>{t("progress.race.name")}</span>
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Spring half marathon"
          maxLength={255}
          autoFocus
        />
      </label>
      <label>
        <span>{t("progress.race.date")}</span>
        <input
          type="date"
          value={raceDate}
          onChange={(event) => setRaceDate(event.target.value)}
        />
      </label>
      <label>
        <span>{t("progress.race.distance")}</span>
        <select value={preset} onChange={(event) => setPreset(event.target.value)}>
          {DISTANCE_PRESETS.map((item) => (
            <option key={item.key} value={item.key}>
              {t(item.label)}
            </option>
          ))}
          <option value="custom">{t("progress.race.customDistance")}</option>
        </select>
      </label>
      {preset === "custom" ? (
        <label>
          <span>{t("progress.race.customDistance")}</span>
          <input
            value={customKm}
            onChange={(event) => setCustomKm(event.target.value)}
            inputMode="decimal"
            placeholder="15"
          />
        </label>
      ) : null}
      <label>
        <span>{t("progress.race.goalTime")}</span>
        <input
          value={goalTime}
          onChange={(event) => setGoalTime(event.target.value)}
          placeholder="1:35:00"
          inputMode="numeric"
        />
      </label>
      <label>
        <span>{t("progress.race.priority")}</span>
        <select
          value={priority}
          onChange={(event) => setPriority(event.target.value as Priority)}
        >
          <option value="A">{t("progress.race.priority.A")}</option>
          <option value="B">{t("progress.race.priority.B")}</option>
          <option value="C">{t("progress.race.priority.C")}</option>
        </select>
      </label>
      <label>
        <span>{t("progress.race.location")}</span>
        <input
          value={location}
          onChange={(event) => setLocation(event.target.value)}
          maxLength={255}
        />
      </label>
      <label className="race-form__notes">
        <span>{t("progress.race.notes")}</span>
        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          rows={2}
          maxLength={2000}
        />
      </label>
      {problem ? <p className="form-error">{problem}</p> : null}
      <div className="race-form__actions">
        <Button type="submit" variant="primary" size="sm" loading={pending}>
          {pending ? t("progress.race.saving") : t("progress.race.save")}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          {t("progress.race.cancel")}
        </Button>
      </div>
    </form>
  );
}
