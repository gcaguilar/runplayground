import { useState, type FormEvent } from "react";
import { Link } from "@tanstack/react-router";
import {
  Activity,
  Archive,
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Database,
  Gauge,
  HeartPulse,
  Info,
  RefreshCw,
  Target,
  Timer,
  TrendingUp,
  Upload,
  XCircle,
  Zap,
} from "lucide-react";

import type {
  DistancePrediction,
  GoalArchive,
  PerformanceEffort,
  PerformanceGoal,
} from "@/api/client";
import {
  useActivities,
  useCloseGoal,
  useDeleteGoal,
  useGoalArchive,
  usePerformance,
  usePerformanceHistory,
  useRecomputePerformance,
  useUpsertGoal,
} from "@/api/queries";
import { PerformanceHistoryChart, Vo2MaxChart } from "@/components/Charts";
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
  formatDateTime,
  formatDistance,
  formatNumber,
  formatPace,
  parseTimeInput,
} from "@/lib/format";

const REASON_KEYS: Record<string, MessageKey> = {
  no_data: "performance.reason.no_data",
  single_effort: "performance.reason.single_effort",
  few_efforts: "performance.reason.few_efforts",
  extrapolated: "performance.reason.extrapolated",
  weak_distance_coverage: "performance.reason.weak_distance_coverage",
  stale_efforts: "performance.reason.stale_efforts",
  aging_efforts: "performance.reason.aging_efforts",
  low_quality_streams: "performance.reason.low_quality_streams",
  model_disagreement: "performance.reason.model_disagreement",
  model_gap: "performance.reason.model_gap",
  no_long_run: "performance.reason.no_long_run",
  short_long_run: "performance.reason.short_long_run",
  no_race_at_distance: "performance.reason.no_race_at_distance",
  race_at_distance: "performance.reason.race_at_distance",
  consistent_models: "performance.reason.consistent_models",
};

const WARNING_KEYS: Record<string, MessageKey> = {
  no_activities: "performance.warning.no_activities",
  no_running_activities: "performance.warning.no_running_activities",
  no_streams: "performance.warning.no_streams",
  no_efforts: "performance.warning.no_efforts",
  few_efforts: "performance.warning.few_efforts",
  no_races: "performance.warning.no_races",
  no_goals: "performance.warning.no_goals",
  no_garmin_export: "performance.warning.no_garmin_export",
  garmin_export_stale: "performance.warning.garmin_export_stale",
  stale_efforts: "performance.warning.stale_efforts",
};

const METHOD_KEYS: Record<string, MessageKey> = {
  stream: "performance.effortMethod.stream",
  activity: "performance.effortMethod.activity",
  race: "performance.effortMethod.race",
};

const DISTANCE_KEYS: Record<string, MessageKey> = {
  "5k": "distance.5k",
  "10k": "distance.10k",
  half_marathon: "distance.half_marathon",
  marathon: "distance.marathon",
};

export function PerformancePage() {
  const { t, locale, units } = useI18n();
  const overview = usePerformance();
  const history = usePerformanceHistory(180);
  const archive = useGoalArchive();
  const recompute = useRecomputePerformance();
  const [editingGoal, setEditingGoal] = useState<string | null>(null);

  if (overview.isLoading) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow={t("performance.page.eyebrow")} title={t("performance.page.title")} />
        <div className="performance-skeleton">
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
        </div>
      </div>
    );
  }

  if (overview.isError || !overview.data) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow={t("performance.page.eyebrow")}
          title={t("performance.page.title")}
          description={t("performance.page.subtitle")}
        />
        <ErrorState
          message={overview.error instanceof Error ? overview.error.message : t("performance.error")}
          onRetry={() => void overview.refetch()}
        />
      </div>
    );
  }

  const data = overview.data;
  const warnings = data.warnings ?? [];
  const anchor = data.fitness_anchor;
  const insufficient = data.status === "insufficient" || !anchor;

  return (
    <div className="page-stack performance-page">
      <PageHeader
        eyebrow={t("performance.page.eyebrow")}
        title={t("performance.page.title")}
        description={t("performance.page.subtitle")}
        actions={
          <div className="performance-actions">
            <Button
              variant="secondary"
              size="sm"
              loading={recompute.isPending}
              onClick={() => recompute.mutate()}
            >
              <RefreshCw size={15} aria-hidden="true" />
              {recompute.isPending
                ? t("performance.actions.recomputing")
                : t("performance.actions.recompute")}
            </Button>
            <Link to="/imports" className="button button--primary button--sm">
              <Upload size={15} aria-hidden="true" />
              {t("performance.actions.import")}
            </Link>
          </div>
        }
      />

      {warnings.length ? (
        <div className="performance-warnings" role="status">
          <span className="performance-warnings__icon">
            <CircleAlert size={16} aria-hidden="true" />
          </span>
          <div className="performance-warnings__list">
            {warnings.map((warning) => (
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
            icon={Gauge}
            title={t("performance.empty.title")}
            description={t("performance.empty.body")}
            action={
              <Link to="/imports" className="button button--primary button--sm">
                <Upload size={15} aria-hidden="true" />
                {t("performance.empty.import")}
              </Link>
            }
          />
        </Card>
      ) : null}

      {!insufficient && anchor ? (
        <>
          <section className="performance-hero">
            <Card className="panel anchor-card">
              <div className="anchor-card__head">
                <div>
                  <span className="eyebrow">{t("performance.anchor.eyebrow")}</span>
                  <h2>{t("performance.anchor.title")}</h2>
                </div>
                <ConfidenceBadge confidence={anchor.confidence} score={anchor.confidence_score} />
              </div>

              <div className="anchor-card__value">
                <strong>{formatClock(anchor.time_s)}</strong>
                <span>
                  {t("performance.anchor.pace")} · {formatPace(anchor.pace_s_per_km, units)}
                </span>
              </div>

              <div className="anchor-card__range">
                <span>{t("performance.anchor.range")}</span>
                <strong>
                  {formatClock(anchor.low_s)} – {formatClock(anchor.high_s)}
                </strong>
              </div>

              <ProgressBar
                value={anchor.confidence_score * 100}
                tone={progressTone(anchor.confidence)}
                label={t("performance.confidence.label")}
              />
              <p className="anchor-card__copy">{t("performance.anchor.description")}</p>
              <span className="anchor-card__asof">
                <Clock3 size={13} aria-hidden="true" />
                {t("performance.anchor.asOf")} {formatDateTime(anchor.as_of, locale)}
              </span>
            </Card>

            <Card className="panel performance-data-card">
              <SectionHeading
                title={t("performance.data.title")}
                subtitle={t("performance.data.subtitle")}
                icon={Database}
              />
              <div className="performance-data-grid">
                <DataStat
                  label={t("performance.data.activities")}
                  value={formatNumber(data.data.running_activities, locale)}
                />
                <DataStat
                  label={t("performance.data.streams")}
                  value={formatNumber(data.data.activities_with_streams, locale)}
                />
                <DataStat
                  label={t("performance.data.efforts")}
                  value={formatNumber(data.data.efforts, locale)}
                />
                <DataStat
                  label={t("performance.data.races")}
                  value={formatNumber(data.data.races, locale)}
                />
              </div>
              <div className="performance-prep">
                <h3>{t("performance.prep.title")}</h3>
                <div className="performance-prep__rows">
                  <PrepRow
                    icon={TrendingUp}
                    label={t("performance.prep.longest90")}
                    value={formatDistance(data.preparation.longest_run_90d_m, units, locale)}
                  />
                  <PrepRow
                    icon={Activity}
                    label={t("performance.prep.weekly28")}
                    value={formatDistance(data.preparation.weekly_distance_28d_m, units, locale)}
                  />
                  <PrepRow
                    icon={Target}
                    label={t("performance.prep.races365")}
                    value={formatNumber(data.preparation.races_365d, locale)}
                  />
                </div>
              </div>
            </Card>
          </section>

          <section className="performance-distances">
            <SectionHeading
              title={t("performance.distances.title")}
              subtitle={t("performance.distances.subtitle")}
              icon={Gauge}
            />
            <div className="distance-grid">
              {data.distances.map((prediction) => (
                <DistanceCard
                  key={prediction.distance_key}
                  prediction={prediction}
                  locale={locale}
                  units={units}
                  editing={editingGoal === prediction.distance_key}
                  onEdit={() =>
                    setEditingGoal((current) =>
                      current === prediction.distance_key ? null : prediction.distance_key,
                    )
                  }
                  onClose={() => setEditingGoal(null)}
                />
              ))}
            </div>
          </section>

          <section className="performance-lower">
            <Card className="panel performance-history">
              <SectionHeading
                title={t("performance.history.title")}
                subtitle={t("performance.history.subtitle")}
                icon={TrendingUp}
              />
              {history.isLoading ? (
                <Skeleton className="skeleton--chart" />
              ) : (
                <PerformanceHistoryChart items={history.data?.items ?? []} />
              )}
              <p className="performance-note">{t("performance.history.note")}</p>
            </Card>

            <Card className="panel performance-garmin">
              <SectionHeading
                title={t("performance.garmin.title")}
                subtitle={t("performance.garmin.subtitle")}
                icon={HeartPulse}
                action={
                  data.garmin.imported_at ? (
                    <Badge tone="info">
                      {t("performance.garmin.imported", {
                        date: formatDate(data.garmin.imported_at, locale),
                      })}
                    </Badge>
                  ) : null
                }
              />
              <GarminReferencePanel reference={data.garmin} locale={locale} units={units} />
            </Card>
          </section>
        </>
      ) : (
        <GarminOnlyCard reference={data.garmin} locale={locale} units={units} />
      )}

      <ClosedGoalsSection
        goals={archive.data ?? []}
        loading={archive.isLoading}
        locale={locale}
      />

      <Card className="panel performance-method">
        <SectionHeading
          title={t("performance.method.title")}
          subtitle={t("performance.method.subtitle")}
          icon={Info}
        />
        <div className="method-grid">
          <MethodItem icon={Zap} title={t("performance.method.ceiling.title")}>
            {t("performance.method.ceiling.body")}
          </MethodItem>
          <MethodItem icon={Gauge} title={t("performance.method.planning.title")}>
            {t("performance.method.planning.body")}
          </MethodItem>
          <MethodItem icon={Timer} title={t("performance.method.gap.title")}>
            {t("performance.method.gap.body")}
          </MethodItem>
          <MethodItem icon={Database} title={t("performance.method.quality.title")}>
            {t("performance.method.quality.body")}
          </MethodItem>
        </div>
      </Card>
    </div>
  );
}

function DistanceCard({
  prediction,
  locale,
  units,
  editing,
  onEdit,
  onClose,
}: {
  prediction: DistancePrediction;
  locale: Locale;
  units: Units;
  editing: boolean;
  onEdit: () => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const label = DISTANCE_KEYS[prediction.distance_key] ?? prediction.distance_key;
  const planning = prediction.planning;
  const ceiling = prediction.ceiling;
  const gap = prediction.gap_s;
  const gapPct = prediction.gap_pct;
  const confidenceReason = prediction.confidence_reasons ?? [];
  const goalGap = prediction.goal_gap_s;

  return (
    <Card className={cn("panel distance-card", `distance-card--${prediction.distance_key}`)}>
      <div className="distance-card__head">
        <div>
          <span className="distance-card__key">{t(label)}</span>
          <span className="distance-card__distance">
            {formatDistance(prediction.distance_m, units, locale, { digits: 1 })}
          </span>
        </div>
        <ConfidenceBadge
          confidence={prediction.confidence}
          score={prediction.confidence_score}
        />
      </div>

      <div className="distance-card__primary">
        <span className="eyebrow">{t("performance.estimate.planning")}</span>
        <div className="distance-card__value">
          <strong>{planning ? formatClock(planning.time_s) : "—"}</strong>
          <span>{planning ? formatPace(planning.pace_s_per_km, units) : t("common.noData")}</span>
        </div>
        {planning ? (
          <span className="distance-card__range">
            {t("performance.estimate.range")} {formatClock(planning.low_s)} –{" "}
            {formatClock(planning.high_s)}
          </span>
        ) : null}
      </div>

      <div className="distance-card__split">
        <div>
          <span>{t("performance.estimate.ceiling")}</span>
          <strong>{ceiling ? formatClock(ceiling.time_s) : "—"}</strong>
        </div>
        <div>
          <span>{t("performance.gap.title")}</span>
          <strong className={cn(gapTone(gapPct))}>
            {gap === null || gap === undefined
              ? "—"
              : `${gap > 0 ? "+" : gap < 0 ? "−" : ""}${formatClock(Math.abs(gap))}`}
          </strong>
        </div>
      </div>

      <p className={cn("distance-card__gap-copy", gapTone(gapPct))}>
        {gap === null || gap === undefined || gapPct === null || gapPct === undefined
          ? t("performance.gap.none")
          : gap > 0
            ? t("performance.gap.fast", { gap: formatClock(gap) })
            : gap < 0
              ? t("performance.gap.behind", { gap: formatClock(Math.abs(gap)) })
              : t("performance.gap.close", { gap: "0:00" })}
      </p>

      <div className="distance-card__marks">
        <MarkRow
          label={t("performance.mark.officialPr")}
          effort={prediction.official_pr ?? null}
          locale={locale}
        />
        <MarkRow
          label={t("performance.mark.recentBest")}
          effort={prediction.recent_best ?? null}
          locale={locale}
        />
        <MarkRow
          label={t("performance.mark.goal")}
          effort={null}
          goal={prediction.goal ?? null}
          locale={locale}
        />
      </div>

      {prediction.goal && goalGap !== null && goalGap !== undefined ? (
        <p className={cn("distance-card__goal-gap", goalGap < -1 && "is-ahead")}>
          {goalGap < -1
            ? t("performance.goal.ahead", { gap: formatClock(Math.abs(goalGap)) })
            : goalGap > 1
              ? t("performance.goal.behind", { gap: formatClock(goalGap) })
              : t("performance.goal.match")}
        </p>
      ) : null}

      <div className="distance-card__confidence">
        <div className="distance-card__confidence-head">
          <span>{t("performance.confidence.label")}</span>
          <strong>{t("performance.confidence.score", { score: Math.round(prediction.confidence_score * 100) })}</strong>
        </div>
        <ProgressBar
          value={prediction.confidence_score * 100}
          tone={progressTone(prediction.confidence)}
        />
        <div className="reason-list">
          {confidenceReason.map((reason) => (
            <span className="reason-chip" key={reason}>
              {REASON_KEYS[reason] ? t(REASON_KEYS[reason]) : reason}
            </span>
          ))}
        </div>
      </div>

      <div className="distance-card__actions">
        <Button variant="ghost" size="sm" onClick={onEdit}>
          <Target size={14} aria-hidden="true" />
          {prediction.goal
            ? t("performance.actions.editGoal")
            : t("performance.actions.setGoal")}
        </Button>
        {prediction.official_pr || prediction.recent_best ? (
          <Link
            to="/activities/$activityId"
            params={{
              activityId: String(
                (prediction.official_pr ?? prediction.recent_best)?.activity_id,
              ),
            }}
            className="text-link"
          >
            {t("performance.actions.openActivity")}
            <ArrowRight size={13} aria-hidden="true" />
          </Link>
        ) : null}
      </div>

      {editing ? (
        <GoalEditor
          distanceKey={prediction.distance_key}
          distanceLabel={t(label)}
          goal={prediction.goal ?? null}
          onClose={onClose}
        />
      ) : null}
    </Card>
  );
}

function MarkRow({
  label,
  effort,
  goal,
  locale,
}: {
  label: string;
  effort: PerformanceEffort | null;
  goal?: PerformanceGoal | null;
  locale: Locale;
}) {
  const { t } = useI18n();
  if (goal) {
    return (
      <div className="mark-row">
        <span className="mark-row__label">{label}</span>
        <strong>{formatClock(goal.target_time_s)}</strong>
        <span className="mark-row__meta">
          {goal.race_name ? `${goal.race_name} · ` : ""}
          {goal.target_date ? formatDate(goal.target_date, locale) : t("common.noData")}
        </span>
      </div>
    );
  }
  if (!effort) {
    return (
      <div className="mark-row mark-row--empty">
        <span className="mark-row__label">{label}</span>
        <strong>—</strong>
        <span className="mark-row__meta">{t("performance.mark.none")}</span>
      </div>
    );
  }
  return (
    <div className="mark-row">
      <span className="mark-row__label">{label}</span>
      <strong>{formatClock(effort.duration_s)}</strong>
      <span className="mark-row__meta">
        {formatDate(effort.start_time_utc, locale)}
        <span className="dot-sep" aria-hidden="true" />
        {METHOD_KEYS[effort.method] ? t(METHOD_KEYS[effort.method]) : effort.method}
      </span>
    </div>
  );
}

function GoalEditor({
  distanceKey,
  distanceLabel,
  goal,
  onClose,
}: {
  distanceKey: string;
  distanceLabel: string;
  goal: PerformanceGoal | null;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const upsert = useUpsertGoal();
  const remove = useDeleteGoal();
  const close = useCloseGoal();
  const [time, setTime] = useState(goal ? formatClock(goal.target_time_s) : "");
  const [date, setDate] = useState(goal?.target_date ?? "");
  const [name, setName] = useState(goal?.race_name ?? "");
  const [notes, setNotes] = useState(goal?.notes ?? "");
  const [problem, setProblem] = useState<string | null>(null);
  const [closeStatus, setCloseStatus] = useState<"achieved" | "missed" | "cancelled">("achieved");
  const [outcomeTime, setOutcomeTime] = useState("");
  const [activityId, setActivityId] = useState<number | null>(null);
  const [closeDate, setCloseDate] = useState(goal?.target_date ?? new Date().toISOString().slice(0, 10));
  const [closeNote, setCloseNote] = useState("");
  const activities = useActivities({
    from: closeDate,
    to: closeDate,
    limit: 100,
    sport: "running",
  });
  const activityItems = activities.data?.items ?? [];

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const seconds = parseTimeInput(time);
    if (seconds === null) {
      setProblem(t("performance.goal.invalidTime"));
      return;
    }
    setProblem(null);
    upsert.mutate(
      {
        distanceKey,
        goal: {
          target_time_s: seconds,
          target_date: date || null,
          race_name: name.trim() || null,
          notes: notes.trim() || null,
        },
      },
      {
        onSuccess: onClose,
        onError: (error) =>
          setProblem(error instanceof Error ? error.message : t("performance.goal.error")),
      },
    );
  };

  const submitClose = () => {
    let outcomeSeconds: number | null = null;
    if (outcomeTime.trim()) {
      outcomeSeconds = parseTimeInput(outcomeTime);
      if (outcomeSeconds === null) {
        setProblem(t("performance.goal.invalidTime"));
        return;
      }
    }
    setProblem(null);
    close.mutate(
      {
        distanceKey,
        payload: {
          status: closeStatus,
          outcome_time_s: outcomeSeconds,
          activity_id: activityId,
          note: closeNote.trim() || null,
        },
      },
      {
        onSuccess: onClose,
        onError: (error) =>
          setProblem(error instanceof Error ? error.message : t("performance.goal.closeError")),
      },
    );
  };

  return (
    <form className="goal-editor" onSubmit={submit}>
      <div className="goal-editor__head">
        <strong>{t("performance.goal.title", { distance: distanceLabel })}</strong>
        <span>{t("performance.goal.timeHint")}</span>
      </div>
      <label>
        <span>{t("performance.goal.time")}</span>
        <input
          value={time}
          onChange={(event) => setTime(event.target.value)}
          placeholder="20:00"
          inputMode="numeric"
          autoFocus
        />
      </label>
      <label>
        <span>{t("performance.goal.date")}</span>
        <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
      </label>
      <label>
        <span>{t("performance.goal.name")}</span>
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Spring 5K"
          maxLength={255}
        />
      </label>
      <label>
        <span>{t("performance.goal.notes")}</span>
        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          rows={2}
          maxLength={2000}
        />
      </label>
      {problem ? <p className="goal-editor__problem">{problem}</p> : null}
      <div className="goal-editor__actions">
        <Button type="submit" variant="primary" size="sm" loading={upsert.isPending}>
          {t("performance.actions.saveGoal")}
        </Button>
        {goal ? (
          <Button
            type="button"
            variant="danger"
            size="sm"
            loading={remove.isPending}
            onClick={() =>
              remove.mutate(distanceKey, {
                onSuccess: onClose,
                onError: (error) =>
                  setProblem(
                    error instanceof Error ? error.message : t("performance.goal.error"),
                  ),
              })
            }
          >
            {t("performance.actions.deleteGoal")}
          </Button>
        ) : null}
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          {t("performance.actions.cancel")}
        </Button>
      </div>

      {goal ? (
        <div className="goal-editor__close">
          <div className="goal-editor__close-head">
            <strong>{t("performance.goal.closeTitle")}</strong>
            <span>{t("performance.goal.closeHint")}</span>
          </div>
          <label>
            <span>{t("performance.goal.outcome")}</span>
            <select
              value={closeStatus}
              onChange={(event) =>
                setCloseStatus(event.target.value as "achieved" | "missed" | "cancelled")
              }
            >
              <option value="achieved">{t("performance.archive.status.achieved")}</option>
              <option value="missed">{t("performance.archive.status.missed")}</option>
              <option value="cancelled">{t("performance.archive.status.cancelled")}</option>
            </select>
          </label>
          <label>
            <span>{t("performance.goal.outcomeTime")}</span>
            <input
              value={outcomeTime}
              onChange={(event) => setOutcomeTime(event.target.value)}
              placeholder="20:00"
              inputMode="numeric"
            />
          </label>
          <label>
            <span>{t("performance.goal.activityDate")}</span>
            <input
              type="date"
              value={closeDate}
              onChange={(event) => {
                setCloseDate(event.target.value);
                setActivityId(null);
              }}
            />
          </label>
          <label>
            <span>{t("performance.goal.activity")}</span>
            <select
              value={activityId ?? ""}
              onChange={(event) => {
                const next = event.target.value ? Number(event.target.value) : null;
                setActivityId(next);
                const selected = activityItems.find((item) => item.id === next);
                if (selected && !outcomeTime.trim()) {
                  setOutcomeTime(formatClock(selected.duration_s));
                }
              }}
            >
              <option value="">{t("performance.goal.noActivity")}</option>
              {activityItems.map((activity) => (
                <option key={activity.id} value={activity.id}>
                  {activity.name || t("calendar.legend.activity")} ·{" "}
                  {formatClock(activity.duration_s)}
                </option>
              ))}
            </select>
          </label>
          <label className="goal-editor__wide">
            <span>{t("performance.goal.closeNote")}</span>
            <textarea
              value={closeNote}
              onChange={(event) => setCloseNote(event.target.value)}
              rows={2}
              maxLength={2000}
            />
          </label>
          <div className="goal-editor__actions">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              loading={close.isPending}
              onClick={submitClose}
            >
              <Archive size={14} aria-hidden="true" />
              {t("performance.actions.closeGoal")}
            </Button>
          </div>
        </div>
      ) : null}
    </form>
  );
}

function ClosedGoalsSection({
  goals,
  loading,
  locale,
}: {
  goals: GoalArchive[];
  loading: boolean;
  locale: Locale;
}) {
  const { t } = useI18n();
  return (
    <Card className="panel performance-archive">
      <SectionHeading
        title={t("performance.archive.title")}
        subtitle={t("performance.archive.subtitle")}
        icon={Archive}
      />
      {loading ? (
        <Skeleton className="skeleton--line" />
      ) : goals.length === 0 ? (
        <p className="performance-note">{t("performance.archive.empty")}</p>
      ) : (
        <div className="goal-archive-list">
          {goals.map((goal) => {
            const label = DISTANCE_KEYS[goal.distance_key] ?? goal.distance_key;
            const tone =
              goal.status === "achieved"
                ? "success"
                : goal.status === "missed"
                  ? "danger"
                  : "warning";
            const Icon =
              goal.status === "achieved"
                ? CheckCircle2
                : goal.status === "missed"
                  ? XCircle
                  : CircleAlert;
            return (
              <article className="goal-archive-row" key={`${goal.distance_key}-${goal.closed_at}`}>
                <div className="goal-archive-row__head">
                  <div>
                    <strong>{t(label)}</strong>
                    <span>
                      {goal.race_name ? `${goal.race_name} · ` : ""}
                      {formatDate(goal.closed_at, locale)}
                    </span>
                  </div>
                  <Badge tone={tone}>
                    <Icon size={12} aria-hidden="true" />
                    {t(`performance.archive.status.${goal.status}` as MessageKey)}
                  </Badge>
                </div>
                <div className="goal-archive-row__times">
                  <span>
                    {t("performance.archive.target")} <strong>{formatClock(goal.target_time_s)}</strong>
                  </span>
                  <span>
                    {t("performance.archive.outcome")}{" "}
                    <strong>
                      {goal.outcome_time_s !== null
                        ? formatClock(goal.outcome_time_s)
                        : t("performance.archive.noOutcome")}
                    </strong>
                  </span>
                  <span>
                    {t("performance.archive.vsTarget")}{" "}
                    <strong>{signedClock(goal.outcome_vs_target_s)}</strong>
                  </span>
                  <span>
                    {t("performance.archive.vsPrediction")}{" "}
                    <strong>{signedClock(goal.outcome_vs_prediction_s)}</strong>
                  </span>
                </div>
                {goal.note ? <p className="goal-archive-row__note">{goal.note}</p> : null}
                {goal.activity_id ? (
                  <Link
                    to="/activities/$activityId"
                    params={{ activityId: String(goal.activity_id) }}
                    className="text-link"
                  >
                    {goal.activity_name || t("performance.archive.openActivity")}
                    <ArrowRight size={13} aria-hidden="true" />
                  </Link>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
      <p className="performance-note">{t("performance.archive.note")}</p>
    </Card>
  );
}

function signedClock(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value === 0) return formatClock(0);
  return `${value > 0 ? "+" : "−"}${formatClock(Math.abs(value))}`;
}

function GarminReferencePanel({
  reference,
  locale,
  units,
}: {
  reference: {
    imported_at?: string | null;
    vo2max?: { date: string; value: number } | null;
    vo2max_series?: { date: string; value: number }[];
    readiness?: { date: string; value: number } | null;
    acute_training_load?: { date: string; value: number } | null;
    chronic_training_load?: { date: string; value: number } | null;
    race_predictions?: { date: string; distance_m: number; time_s: number }[];
  };
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  if (!reference.imported_at) {
    return (
      <div className="garmin-empty">
        <p>{t("performance.garmin.none")}</p>
        <Link to="/imports" className="button button--secondary button--sm">
          <Upload size={15} aria-hidden="true" />
          {t("performance.garmin.import")}
        </Link>
      </div>
    );
  }

  const metrics = [
    { key: "vo2max", label: t("performance.garmin.vo2max"), point: reference.vo2max, digits: 1 },
    { key: "readiness", label: t("performance.garmin.readiness"), point: reference.readiness, digits: 0 },
    { key: "acute", label: t("performance.garmin.acute"), point: reference.acute_training_load, digits: 0 },
    { key: "chronic", label: t("performance.garmin.chronic"), point: reference.chronic_training_load, digits: 0 },
  ];

  return (
    <div className="garmin-reference">
      <div className="garmin-metrics">
        {metrics.map((metric) => (
          <div className="garmin-metric" key={metric.key}>
            <span>{metric.label}</span>
            <strong>
              {metric.point ? formatNumber(metric.point.value, locale, metric.digits) : "—"}
            </strong>
            <small>{metric.point ? formatDate(metric.point.date, locale) : "—"}</small>
          </div>
        ))}
      </div>

      {reference.vo2max_series?.length ? (
        <div className="garmin-chart">
          <span className="eyebrow">{t("performance.garmin.vo2max")}</span>
          <Vo2MaxChart points={reference.vo2max_series} />
        </div>
      ) : null}

      <div className="garmin-predictions">
        <h3>{t("performance.garmin.races")}</h3>
        {reference.race_predictions?.length ? (
          <div className="garmin-predictions__list">
            {reference.race_predictions.map((prediction) => (
              <div className="garmin-prediction" key={`${prediction.date}-${prediction.distance_m}`}>
                <span>{formatDistance(prediction.distance_m, units, locale, { digits: 1 })}</span>
                <strong>{formatClock(prediction.time_s)}</strong>
                <small>{formatDate(prediction.date, locale)}</small>
              </div>
            ))}
          </div>
        ) : (
          <p className="garmin-predictions__empty">{t("common.noData")}</p>
        )}
      </div>
      <p className="performance-note">{t("performance.garmin.disclaimer")}</p>
    </div>
  );
}

function GarminOnlyCard({
  reference,
  locale,
  units,
}: {
  reference: Parameters<typeof GarminReferencePanel>[0]["reference"];
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  return (
    <Card className="panel performance-garmin">
      <SectionHeading
        title={t("performance.garmin.title")}
        subtitle={t("performance.garmin.subtitle")}
        icon={HeartPulse}
      />
      <GarminReferencePanel reference={reference} locale={locale} units={units} />
    </Card>
  );
}

function ConfidenceBadge({ confidence, score }: { confidence: string; score: number }) {
  const { t } = useI18n();
  const labelKey =
    confidence === "high"
      ? "performance.confidence.high"
      : confidence === "medium"
        ? "performance.confidence.medium"
        : "performance.confidence.low";
  return (
    <Badge tone={confidenceTone(confidence)}>
      {t(labelKey)} · {t("performance.confidence.score", { score: Math.round(score * 100) })}
    </Badge>
  );
}

function DataStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="data-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PrepRow({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Activity;
  label: string;
  value: string;
}) {
  return (
    <div className="prep-row">
      <Icon size={15} aria-hidden="true" />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function MethodItem({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof Activity;
  title: string;
  children: string;
}) {
  return (
    <div className="method-item">
      <span className="method-item__icon">
        <Icon size={17} aria-hidden="true" />
      </span>
      <div>
        <h3>{title}</h3>
        <p>{children}</p>
      </div>
    </div>
  );
}

function confidenceTone(confidence: string): "success" | "warning" | "danger" {
  if (confidence === "high") return "success";
  if (confidence === "medium") return "warning";
  return "danger";
}

function progressTone(confidence: string): "accent" | "warning" | "danger" {
  if (confidence === "high") return "accent";
  if (confidence === "medium") return "warning";
  return "danger";
}

function gapTone(gapPct: number | null | undefined): string {
  if (gapPct === null || gapPct === undefined) return "";
  const absolute = Math.abs(gapPct);
  if (absolute >= 4) return "is-wide";
  if (absolute >= 1.5) return "is-moderate";
  return "is-close";
}
