import { Link } from "@tanstack/react-router";
import {
  Activity,
  ArrowRight,
  CalendarRange,
  Dumbbell,
  Gauge,
  HeartPulse,
  Info,
  Moon,
  RefreshCw,
  ShieldCheck,
  Target,
  Timer,
  Upload,
  Zap,
} from "lucide-react";

import type {
  TrainingFocus,
  TrainingPlan,
  TrainingSession,
} from "@/api/client";
import { useTraining } from "@/api/queries";
import {
  AnalysisConfidence,
  AnalysisMethodCard,
  AnalysisWarnings,
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
  formatNumber,
  formatPace,
  weekdayKeys,
} from "@/lib/format";

const PHASE_KEYS: Record<string, MessageKey> = {
  maintenance: "training.phase.maintenance",
  base: "training.phase.base",
  build: "training.phase.build",
  peak: "training.phase.peak",
  taper: "training.phase.taper",
  recovery: "training.phase.recovery",
};

const PHASE_REASON_KEYS: Record<string, MessageKey> = {
  no_goal: "training.phase.reason.no_goal",
  goal_taper: "training.phase.reason.goal_taper",
  goal_peak: "training.phase.reason.goal_peak",
  goal_build: "training.phase.reason.goal_build",
  goal_base: "training.phase.reason.goal_base",
  recent_race: "training.phase.reason.recent_race",
};

const ACTION_KEYS: Record<string, MessageKey> = {
  increase_volume: "training.focus.action.increase_volume",
  build_consistency: "training.focus.action.build_consistency",
  polarize_intensity: "training.focus.action.polarize_intensity",
  stabilize_load: "training.focus.action.stabilize_load",
  prioritize_recovery: "training.focus.action.prioritize_recovery",
  add_specific_work: "training.focus.action.add_specific_work",
  maintain_balance: "training.focus.action.maintain_balance",
};

const SESSION_TYPE_KEYS: Record<string, MessageKey> = {
  easy: "training.session.type.easy",
  recovery: "training.session.type.recovery",
  strides: "training.session.type.strides",
  long: "training.session.type.long",
  threshold: "training.session.type.threshold",
  race_pace: "training.session.type.race_pace",
  rest: "training.session.type.rest",
};

const PURPOSE_KEYS: Record<string, MessageKey> = {
  aerobic_base: "training.session.purpose.aerobic_base",
  recovery: "training.session.purpose.recovery",
  neuromuscular: "training.session.purpose.neuromuscular",
  long_endurance: "training.session.purpose.long_endurance",
  threshold: "training.session.purpose.threshold",
  race_specific: "training.session.purpose.race_specific",
  rest: "training.session.purpose.rest",
};

const INTENSITY_KEYS: Record<string, MessageKey> = {
  easy: "training.session.intensity.easy",
  moderate: "training.session.intensity.moderate",
  hard: "training.session.intensity.hard",
  rest: "training.session.intensity.rest",
};

const PRIORITY_KEYS: Record<string, MessageKey> = {
  key: "training.session.priority.key",
  support: "training.session.priority.support",
  optional: "training.session.priority.optional",
};

const NOTE_KEYS: Record<string, MessageKey> = {
  intensity_from_pace: "training.notes.intensity_from_pace",
  load_is_estimated: "training.notes.load_is_estimated",
  not_medical_advice: "training.notes.not_medical_advice",
  readiness_reference_only: "training.notes.readiness_reference_only",
  goal_missing: "training.notes.goal_missing",
  goal_without_date: "training.notes.goal_without_date",
  insufficient_data: "training.notes.insufficient_data",
};

const DISTANCE_LABELS: Array<[number, MessageKey]> = [
  [5000, "distance.5k"],
  [10000, "distance.10k"],
  [21097.5, "distance.half_marathon"],
  [42195, "distance.marathon"],
];

export function TrainingPage() {
  const { t, locale, units } = useI18n();
  const training = useTraining();

  if (training.isLoading) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow={t("training.page.eyebrow")} title={t("training.page.title")} />
        <div className="analysis-skeleton">
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
        </div>
      </div>
    );
  }

  if (training.isError || !training.data) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow={t("training.page.eyebrow")}
          title={t("training.page.title")}
          description={t("training.page.subtitle")}
        />
        <ErrorState
          message={
            training.error instanceof Error ? training.error.message : t("training.error")
          }
          onRetry={() => void training.refetch()}
        />
      </div>
    );
  }

  const plan = training.data;
  const insufficient = plan.status === "insufficient" || plan.sessions.length === 0;
  const warnings = plan.warnings ?? [];
  const notes = plan.notes ?? [];

  return (
    <div className="page-stack training-page">
      <PageHeader
        eyebrow={t("training.page.eyebrow")}
        title={t("training.page.title")}
        description={t("training.page.subtitle")}
        actions={
          <div className="analysis-actions">
            <Button
              variant="secondary"
              size="sm"
              loading={training.isFetching}
              onClick={() => void training.refetch()}
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
            icon={Dumbbell}
            title={t("training.empty.title")}
            description={t("training.empty.body")}
            action={
              <div className="analysis-empty__actions">
                <Link to="/imports" className="button button--primary button--sm">
                  <Upload size={15} aria-hidden="true" />
                  {t("training.empty.import")}
                </Link>
                <Link to="/diagnostics" className="button button--secondary button--sm">
                  <ArrowRight size={15} aria-hidden="true" />
                  {t("training.empty.diagnostics")}
                </Link>
              </div>
            }
          />
        </Card>
      ) : (
        <>
          <section className="training-hero">
            <Card className="panel training-phase-card">
              <div className="training-phase-card__head">
                <div>
                  <span className="eyebrow">{t("training.hero.phase")}</span>
                  <h2>{phaseLabel(plan, t)}</h2>
                </div>
              </div>
              <p className="training-phase-card__reason">
                {PHASE_REASON_KEYS[plan.phase_reason]
                  ? t(PHASE_REASON_KEYS[plan.phase_reason])
                  : plan.phase_reason}
              </p>
              <div className="training-phase-card__meta">
                <AnalysisConfidence
                  confidence={plan.confidence}
                  score={plan.confidence_score}
                />
                {plan.weeks_to_goal !== null && plan.weeks_to_goal !== undefined ? (
                  <Badge tone="info">
                    {t("training.hero.weeksToGoal", { weeks: plan.weeks_to_goal })}
                  </Badge>
                ) : null}
              </div>
              <TrainingGoal plan={plan} locale={locale} units={units} />
            </Card>

            <Card className="panel training-target-card">
              <SectionHeading
                title={t("training.loadTarget.title")}
                subtitle={t("training.loadTarget.subtitle")}
                icon={Gauge}
              />
              <div className="training-target-card__value">
                <strong>
                  {distanceRange(
                    plan.load_target.weekly_distance_low_m,
                    plan.load_target.weekly_distance_high_m,
                    units,
                    locale,
                  )}
                </strong>
                <span>{t("training.loadTarget.perWeek")}</span>
              </div>
              <ProgressBar
                value={targetProgress(
                  plan.load_target.current_weekly_distance_m,
                  plan.load_target.weekly_distance_high_m,
                )}
                tone={targetTone(
                  plan.load_target.current_weekly_distance_m,
                  plan.load_target.weekly_distance_low_m,
                  plan.load_target.weekly_distance_high_m,
                )}
                label={t("training.loadTarget.title")}
              />
              <p className="training-target-card__current">
                {t("training.loadTarget.current")}:{" "}
                <strong>
                  {formatDistance(
                    plan.load_target.current_weekly_distance_m,
                    units,
                    locale,
                    { digits: 1 },
                  )}
                </strong>
              </p>
              <div className="training-target-grid">
                <TargetMetric
                  label={t("training.loadTarget.longRun")}
                  value={distanceRange(
                    plan.load_target.long_run_low_m,
                    plan.load_target.long_run_high_m,
                    units,
                    locale,
                  )}
                />
                <TargetMetric
                  label={t("training.loadTarget.quality")}
                  value={
                    plan.load_target.quality_sessions_high === 0
                      ? t("training.loadTarget.qualityNone")
                      : t("training.loadTarget.qualityValue", {
                          low: plan.load_target.quality_sessions_low,
                          high: plan.load_target.quality_sessions_high,
                        })
                  }
                />
              </div>
              <p className="analysis-note">{t("training.loadTarget.note")}</p>
            </Card>
          </section>

          <Card className="panel training-focus-panel">
            <SectionHeading
              title={t("training.focus.title")}
              subtitle={t("training.focus.subtitle")}
              icon={Target}
            />
            <div className="focus-grid">
              {plan.focus.map((focus) => (
                <FocusCard key={`${focus.priority}-${focus.dimension_key}`} focus={focus} />
              ))}
            </div>
          </Card>

          <Card className="panel training-sessions-panel">
            <SectionHeading
              title={t("training.sessions.title")}
              subtitle={t("training.sessions.subtitle")}
              icon={CalendarRange}
              action={
                <Badge tone="info">
                  {t("training.sessions.count", { count: plan.sessions.length })}
                </Badge>
              }
            />
            <div className="session-grid">
              {plan.sessions.map((session, index) => (
                <SessionCard
                  key={`${session.type}-${index}`}
                  session={session}
                  day={weekdayKeys()[index % 7]}
                  locale={locale}
                  units={units}
                />
              ))}
            </div>
            <p className="analysis-note">{t("training.sessions.note")}</p>
          </Card>

          <section className="analysis-duo">
            <Card className="panel">
              <IntensityPanel intensity={plan.intensity} />
            </Card>
            <Card className="panel">
              <LoadPanel load={plan.load} />
            </Card>
          </section>
        </>
      )}

      <Card className="panel training-notes">
        <SectionHeading title={t("training.notes.title")} icon={Info} />
        <ul className="notes-list">
          {notes.map((note) => (
            <li key={note}>
              <Info size={14} aria-hidden="true" />
              <span>{NOTE_KEYS[note] ? t(NOTE_KEYS[note]) : note}</span>
            </li>
          ))}
        </ul>
      </Card>

      <AnalysisMethodCard
        title={t("training.method.title")}
        subtitle={t("training.method.subtitle")}
        items={[
          {
            icon: CalendarRange,
            title: t("training.method.phase.title"),
            body: t("training.method.phase.body"),
          },
          {
            icon: Dumbbell,
            title: t("training.method.sessions.title"),
            body: t("training.method.sessions.body"),
          },
          {
            icon: ShieldCheck,
            title: t("training.method.safety.title"),
            body: t("training.method.safety.body"),
          },
        ]}
      />
    </div>
  );
}

function FocusCard({ focus }: { focus: TrainingFocus }) {
  const { t, locale } = useI18n();
  const meta = DIMENSION_META[focus.dimension_key];
  const action = ACTION_KEYS[focus.action];
  return (
    <div className="focus-card">
      <span className="focus-card__rank">{formatNumber(focus.priority, locale)}</span>
      <div className="focus-card__body">
        <div className="focus-card__head">
          <strong>{meta ? t(meta.label) : t("training.focus.balance")}</strong>
          <Badge tone="warning">{action ? t(action) : focus.action}</Badge>
        </div>
        {focus.score !== null && focus.score !== undefined ? (
          <span className="focus-card__score">
            {t("training.focus.score", { score: Math.round(focus.score) })}
          </span>
        ) : null}
        <ReasonChips reasons={focus.reasons} />
      </div>
    </div>
  );
}

function SessionCard({
  session,
  day,
  locale,
  units,
}: {
  session: TrainingSession;
  day: MessageKey;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  const typeLabel = SESSION_TYPE_KEYS[session.type];
  const purpose = PURPOSE_KEYS[session.purpose];
  const intensity = INTENSITY_KEYS[session.intensity];
  const priority = PRIORITY_KEYS[session.priority];
  const isRest = session.type === "rest";
  const distance = distanceRangeOrNull(
    session.distance_low_m,
    session.distance_high_m,
    units,
    locale,
  );
  const duration = durationRange(session.duration_low_s, session.duration_high_s, locale);

  return (
    <article
      className={cn(
        "session-card",
        `session-card--${isRest ? "rest" : session.intensity}`,
        isRest && "is-rest",
      )}
    >
      <div className="session-card__head">
        <span className="session-card__day">{t(day)}</span>
        {priority ? <Badge tone={isRest ? "neutral" : "accent"}>{t(priority)}</Badge> : null}
      </div>
      <div className="session-card__title">
        <span className="session-card__icon">
          {isRest ? (
            <Moon size={16} aria-hidden="true" />
          ) : session.type === "long" ? (
            <Activity size={16} aria-hidden="true" />
          ) : session.intensity === "hard" ? (
            <Zap size={16} aria-hidden="true" />
          ) : session.intensity === "moderate" ? (
            <Timer size={16} aria-hidden="true" />
          ) : (
            <HeartPulse size={16} aria-hidden="true" />
          )}
        </span>
        <strong>{typeLabel ? t(typeLabel) : session.type}</strong>
      </div>
      <span className={cn("session-card__intensity", `is-${session.intensity}`)}>
        {intensity ? t(intensity) : session.intensity}
      </span>
      <p className="session-card__purpose">{purpose ? t(purpose) : session.purpose}</p>
      <div className="session-card__meta">
        {isRest ? (
          <span>{t("training.session.restDay")}</span>
        ) : (
          <>
            {distance ? <span>{distance}</span> : null}
            {duration ? <span>{duration}</span> : null}
          </>
        )}
      </div>
    </article>
  );
}

function TrainingGoal({
  plan,
  locale,
  units,
}: {
  plan: TrainingPlan;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  const goal = plan.goal;
  if (!goal) {
    return (
      <div className="training-goal training-goal--empty">
        <Target size={15} aria-hidden="true" />
        <span>{t("training.hero.noGoal")}</span>
        <Link to="/performance" className="text-link">
          {t("training.hero.setGoal")}
          <ArrowRight size={13} aria-hidden="true" />
        </Link>
      </div>
    );
  }

  const label = goalDistanceLabel(goal.distance_m);
  return (
    <div className="training-goal">
      <Target size={15} aria-hidden="true" />
      <div>
        <span>{t("training.hero.goal")}</span>
        <strong>
          {label ? t(label) : formatDistance(goal.distance_m, units, locale, { digits: 1 })}
          <span className="dot-sep" aria-hidden="true" />
          {formatClock(goal.target_time_s)}
          <span className="dot-sep" aria-hidden="true" />
          {formatPace(goal.target_time_s / (goal.distance_m / 1000), units)}
        </strong>
        <small>
          {goal.race_name ? `${goal.race_name} · ` : ""}
          {goal.target_date ? formatDate(goal.target_date, locale) : t("diagnostics.goal.noDate")}
        </small>
      </div>
      <Link to="/performance" className="text-link">
        {t("diagnostics.goal.edit")}
        <ArrowRight size={13} aria-hidden="true" />
      </Link>
    </div>
  );
}

function TargetMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="target-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function phaseLabel(
  plan: TrainingPlan,
  t: (key: MessageKey) => string,
): string {
  return PHASE_KEYS[plan.phase] ? t(PHASE_KEYS[plan.phase]) : plan.phase;
}

function goalDistanceLabel(distance: number): MessageKey | null {
  const match = DISTANCE_LABELS.find(([meters]) => Math.abs(meters - distance) < 1);
  return match ? match[1] : null;
}

function distanceRange(
  low: number,
  high: number,
  units: Units,
  locale: Locale,
): string {
  return distanceRangeOrNull(low, high, units, locale) ?? "—";
}

function distanceRangeOrNull(
  low: number | null | undefined,
  high: number | null | undefined,
  units: Units,
  locale: Locale,
): string | null {
  if (low === null || low === undefined) return null;
  const unit = units === "imperial" ? "mi" : "km";
  const format = (meters: number) =>
    formatDistance(meters, units, locale, { digits: 1, unit: false });
  const upper = high ?? low;
  return `${format(low)}–${format(upper)} ${unit}`;
}

function durationRange(
  low: number | null | undefined,
  high: number | null | undefined,
  locale: Locale,
): string | null {
  if (low === null || low === undefined) return null;
  const format = (seconds: number) =>
    `${formatNumber(Math.round(seconds / 60), locale)} ${locale === "es" ? "min" : "min"}`;
  return `${format(low)}–${format(high ?? low)}`;
}

function targetProgress(current: number, high: number): number {
  if (high <= 0) return 0;
  return Math.max(0, Math.min(100, (current / high) * 100));
}

function targetTone(
  current: number,
  low: number,
  high: number,
): "accent" | "warning" | "danger" {
  if (current <= 0) return "danger";
  if (current < low * 0.85) return "warning";
  if (current > high * 1.1) return "danger";
  return "accent";
}
