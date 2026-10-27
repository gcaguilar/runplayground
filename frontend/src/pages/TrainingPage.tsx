import { useState } from "react";
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
  AdherenceOverview,
  AdherenceWeek,
  TrainingFocus,
  TrainingPlan,
  TrainingSession,
} from "@/api/client";
import { useAdherence, useTraining } from "@/api/queries";
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
  strength: "plan.session.type.strength",
  cross_training: "plan.session.type.cross_training",
  other: "plan.session.type.other",
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

const ADHERENCE_STATUS_KEYS: Record<string, MessageKey> = {
  ok: "training.adherence.status.ok",
  partial: "training.adherence.status.partial",
  low: "training.adherence.status.low",
  in_progress: "training.adherence.status.in_progress",
  insufficient: "training.adherence.status.insufficient",
};

const ADHERENCE_STATUS_TONE: Record<
  string,
  "success" | "warning" | "danger" | "info" | "neutral"
> = {
  ok: "success",
  partial: "warning",
  low: "danger",
  in_progress: "info",
  insufficient: "neutral",
};

const ADHERENCE_TREND_KEYS: Record<string, MessageKey> = {
  improving: "training.adherence.trend.improving",
  stable: "training.adherence.trend.stable",
  worsening: "training.adherence.trend.worsening",
  unknown: "training.adherence.trend.unknown",
};

const ADHERENCE_WARNING_KEYS: Record<string, MessageKey> = {
  no_activities: "training.adherence.warning.no_activities",
  short_history: "training.adherence.warning.short_history",
  no_completed_weeks: "training.adherence.warning.no_completed_weeks",
  no_goal: "training.adherence.warning.no_goal",
  current_week_in_progress: "training.adherence.warning.current_week_in_progress",
};

const ADHERENCE_NOTE_KEYS: Record<string, MessageKey> = {
  suggested_plan_not_registered: "training.adherence.notes.suggested_plan_not_registered",
  registered_plan_used: "training.adherence.notes.registered_plan_used",
  mixed_registered_and_suggested: "training.adherence.notes.mixed_registered_and_suggested",
  adherence_is_heuristic: "training.adherence.notes.adherence_is_heuristic",
  current_week_excluded: "training.adherence.notes.current_week_excluded",
  rest_days_derived: "training.adherence.notes.rest_days_derived",
  classification_uses_current_anchor:
    "training.adherence.notes.classification_uses_current_anchor",
  not_medical_advice: "training.adherence.notes.not_medical_advice",
};

const ADHERENCE_BASIS_KEYS: Record<string, MessageKey> = {
  registered: "training.adherence.basis.registered",
  suggested: "training.adherence.basis.suggested",
  mixed: "training.adherence.basis.mixed",
};

const ADHERENCE_BASIS_TONE: Record<
  string,
  "success" | "warning" | "danger" | "info" | "neutral"
> = {
  registered: "success",
  suggested: "info",
  mixed: "warning",
};

const ADHERENCE_OUTCOME_KEYS: Record<string, MessageKey> = {
  completed: "training.adherence.outcome.completed",
  skipped: "training.adherence.outcome.skipped",
  missed: "training.adherence.outcome.missed",
  pending: "training.adherence.outcome.pending",
};

const ADHERENCE_OUTCOME_TONE: Record<
  string,
  "success" | "warning" | "danger" | "info" | "neutral"
> = {
  completed: "success",
  skipped: "neutral",
  missed: "danger",
  pending: "info",
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

          <AdherenceCard />

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

function AdherenceCard() {
  const { t, locale, units } = useI18n();
  const [weeks, setWeeks] = useState<4 | 8 | 12>(8);
  const adherence = useAdherence(weeks);

  if (adherence.isLoading) {
    return (
      <Card className="panel training-adherence">
        <Skeleton className="skeleton--line" />
        <Skeleton className="skeleton--block" />
      </Card>
    );
  }

  if (adherence.isError || !adherence.data) {
    return (
      <Card className="panel training-adherence">
        <ErrorState
          message={
            adherence.error instanceof Error ? adherence.error.message : t("common.error")
          }
          onRetry={() => void adherence.refetch()}
        />
      </Card>
    );
  }

  const data = adherence.data;
  return (
    <Card className="panel training-adherence">
      <SectionHeading
        title={t("training.adherence.title")}
        subtitle={t("training.adherence.subtitle")}
        icon={CalendarRange}
        action={
          <div className="segmented" role="group" aria-label={t("training.adherence.title")}>
            {([4, 8, 12] as const).map((value) => (
              <button
                key={value}
                type="button"
                className={cn(weeks === value && "is-active")}
                aria-pressed={weeks === value}
                onClick={() => setWeeks(value)}
              >
                {t("training.adherence.window", { weeks: value })}
              </button>
            ))}
          </div>
        }
      />

      {(data.warnings ?? []).length ? (
        <div className="analysis-warnings" role="status">
          <div className="analysis-warnings__list">
            {(data.warnings ?? []).map((warning) => (
              <Badge key={warning} tone="warning" dot>
                {ADHERENCE_WARNING_KEYS[warning] ? t(ADHERENCE_WARNING_KEYS[warning]) : warning}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}

      <div className="adherence-basis">
        <div>
          <span>{t("training.adherence.plan")}</span>
          <strong>{data.plan_name ?? t("training.adherence.noPlan")}</strong>
        </div>
        <div>
          <span>{t("training.adherence.basis")}</span>
          <Badge tone={ADHERENCE_BASIS_TONE[data.basis] ?? "neutral"}>
            {t(ADHERENCE_BASIS_KEYS[data.basis] ?? "training.adherence.basis.suggested")}
          </Badge>
        </div>
        <div>
          <span>{t("training.adherence.registeredWeeks")}</span>
          <strong>{data.registered_weeks}</strong>
        </div>
        <div>
          <span>{t("training.adherence.suggestedWeeks")}</span>
          <strong>{data.suggested_weeks}</strong>
        </div>
      </div>

      <div className="adherence-summary">
        <div className="adherence-score">
          <span>{data.summary.average_score == null ? "—" : Math.round(data.summary.average_score)}</span>
          <small>{t("training.adherence.average")}</small>
        </div>
        <div className="adherence-summary__meta">
          <div>
            <span>{t("training.adherence.current")}</span>
            <AdherenceStatusBadge status={currentWeekStatus(data)} />
          </div>
          <div>
            <span>{t("training.adherence.trend")}</span>
            <Badge tone={trendTone(data.summary.trend)}>
              {t(ADHERENCE_TREND_KEYS[data.summary.trend] ?? "training.adherence.trend.unknown")}
            </Badge>
          </div>
        </div>
        <div className="adherence-ratios">
          <Ratio label={t("training.adherence.volume")} value={data.summary.volume_ratio} />
          <Ratio label={t("training.adherence.longRun")} value={data.summary.long_run_ratio} />
          <Ratio label={t("training.adherence.quality")} value={data.summary.quality_ratio} />
          <Ratio label={t("training.adherence.rest")} value={data.summary.rest_ratio} />
        </div>
      </div>

      <div className="adherence-counts">
        <span>
          {t("training.adherence.completedCount", {
            count: data.summary.sessions_completed,
          })}
        </span>
        <span>
          {t("training.adherence.skippedCount", { count: data.summary.sessions_skipped })}
        </span>
        <span>
          {t("training.adherence.missedCount", { count: data.summary.sessions_missed })}
        </span>
        <strong>
          {t("training.adherence.completion", {
            value:
              data.summary.completion_rate == null
                ? "—"
                : `${Math.round(data.summary.completion_rate * 100)}%`,
          })}
        </strong>
      </div>

      <div className="adherence-weeks">
        {(data.items ?? []).map((item) => (
          <AdherenceRow key={item.week_start} item={item} locale={locale} units={units} />
        ))}
      </div>

      <ul className="adherence-notes">
        {(data.notes ?? [])
          .filter((note) => ADHERENCE_NOTE_KEYS[note])
          .map((note) => (
            <li key={note}>
              <Info size={13} aria-hidden="true" />
              <span>{t(ADHERENCE_NOTE_KEYS[note])}</span>
            </li>
          ))}
      </ul>
    </Card>
  );
}

function currentWeekStatus(data: AdherenceOverview): string {
  const item = (data.items ?? []).find((entry) => entry.week_start === data.current_week_start);
  return item?.status ?? "insufficient";
}

function AdherenceStatusBadge({ status }: { status: string }) {
  const { t } = useI18n();
  return (
    <Badge tone={ADHERENCE_STATUS_TONE[status] ?? "neutral"}>
      {t(ADHERENCE_STATUS_KEYS[status] ?? "training.adherence.status.insufficient")}
    </Badge>
  );
}

function trendTone(trend: string): "success" | "warning" | "danger" | "neutral" {
  if (trend === "improving") return "success";
  if (trend === "worsening") return "danger";
  return "neutral";
}

function Ratio({ label, value }: { label: string; value: number | null | undefined }) {
  const { t } = useI18n();
  return (
    <div className="adherence-ratio">
      <span>{label}</span>
      <strong>{value == null ? "—" : `${Math.round(value * 100)}%`}</strong>
      <small>{t("training.adherence.ratio")}</small>
    </div>
  );
}

function AdherenceRow({
  item,
  locale,
  units,
}: {
  item: AdherenceWeek;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  const score = item.score;
  const tone = score == null ? "info" : score >= 80 ? "accent" : score >= 50 ? "warning" : "danger";
  return (
    <div className={cn("adherence-week", item.status === "in_progress" && "is-current")}>
      <div className="adherence-week__head">
        <div>
          <strong>
            {t("training.adherence.week", {
              date: formatDate(item.week_start, locale),
            })}
          </strong>
          <small>{PHASE_KEYS[item.phase] ? t(PHASE_KEYS[item.phase]) : item.phase}</small>
        </div>
        <div className="adherence-week__badges">
          {item.basis === "registered" ? (
            <Badge tone="success">{t("training.adherence.basis.registered")}</Badge>
          ) : null}
          <AdherenceStatusBadge status={item.status} />
          <span className="adherence-week__score">{score == null ? "—" : Math.round(score)}</span>
        </div>
      </div>

      <div className="adherence-week__grid">
        <AdherenceMetric
          label={t("training.adherence.volume")}
          actual={formatDistance(item.volume_actual_m, units, locale, { digits: 1 })}
          planned={`${formatDistance(item.volume_low_m, units, locale, { digits: 1 })} – ${formatDistance(
            item.volume_high_m,
            units,
            locale,
            { digits: 1 },
          )}`}
          status={item.volume_status}
        />
        <AdherenceMetric
          label={t("training.adherence.longRun")}
          actual={formatDistance(item.longest_actual_m, units, locale, { digits: 1 })}
          planned={`${formatDistance(item.long_run_low_m, units, locale, { digits: 1 })} – ${formatDistance(
            item.long_run_high_m,
            units,
            locale,
            { digits: 1 },
          )}`}
          status={item.long_run_status}
        />
        <AdherenceMetric
          label={t("training.adherence.quality")}
          actual={String(item.quality_actual)}
          planned={`${item.quality_low} – ${item.quality_high}`}
          status={item.quality_status}
        />
        <AdherenceMetric
          label={t("training.adherence.rest")}
          actual={String(item.rest_actual)}
          planned={String(item.rest_planned)}
          status={item.rest_status}
        />
      </div>

      <div className="adherence-week__foot">
        <span>
          {t("training.adherence.sessions", {
            actual: item.sessions_actual,
            planned: item.sessions_planned,
          })}
          {item.basis === "registered"
            ? ` · ${t("training.adherence.completedCount", {
                count: item.sessions_completed,
              })} · ${t("training.adherence.skippedCount", {
                count: item.sessions_skipped,
              })} · ${t("training.adherence.missedCount", {
                count: item.sessions_missed,
              })}`
            : ""}
        </span>
        {score != null ? (
          <ProgressBar value={score} tone={tone} label={t("training.adherence.score")} />
        ) : null}
      </div>

      {(item.session_items ?? []).length ? (
        <div className="adherence-sessions">
          <span className="adherence-sessions__title">
            {t("training.adherence.sessionBreakdown")}
          </span>
          {(item.session_items ?? []).map((session) => (
            <div key={session.session_id ?? `${session.date}-${session.type}`} className="adherence-session">
              <span className="adherence-session__date">
                {formatDate(session.date, locale)}
              </span>
              <span className="adherence-session__type">
                {SESSION_TYPE_KEYS[session.type] ? t(SESSION_TYPE_KEYS[session.type]) : session.type}
              </span>
              <Badge tone={ADHERENCE_OUTCOME_TONE[session.outcome] ?? "neutral"}>
                {t(
                  ADHERENCE_OUTCOME_KEYS[session.outcome] ??
                    "training.adherence.outcome.pending",
                )}
              </Badge>
              <span className="adherence-session__target">
                {session.distance_low_m
                  ? formatDistance(session.distance_low_m, units, locale, { digits: 1 })
                  : session.duration_low_s
                    ? `${Math.round(session.duration_low_s / 60)} min`
                    : "—"}
              </span>
              <span className="adherence-session__actual">
                {session.actual_distance_m
                  ? formatDistance(session.actual_distance_m, units, locale, { digits: 1 })
                  : session.actual_duration_s
                    ? `${Math.round(session.actual_duration_s / 60)} min`
                    : "—"}
              </span>
              {session.compliance_pct != null ? (
                <span className="adherence-session__compliance">
                  {Math.round(session.compliance_pct)}%
                </span>
              ) : null}
              {session.activity_id ? (
                <Link
                  to="/activities/$activityId"
                  params={{ activityId: String(session.activity_id) }}
                  className="text-link"
                >
                  <Activity size={12} aria-hidden="true" />
                  {t("training.adherence.sessionActivity")}
                </Link>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function AdherenceMetric({
  label,
  actual,
  planned,
  status,
}: {
  label: string;
  actual: string;
  planned: string;
  status: string;
}) {
  const { t } = useI18n();
  return (
    <div className={cn("adherence-metric", `is-${status}`)}>
      <span>{label}</span>
      <strong>{actual}</strong>
      <small>
        {t("training.adherence.planned")}: {planned}
      </small>
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
