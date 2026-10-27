import { useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  Gauge,
  History,
  Info,
  RefreshCw,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

import type {
  AccuracySample,
  ActionSuggestion,
  GoalTracking,
  TrackedAction,
} from "@/api/client";
import {
  useDeleteTrackingAction,
  useTracking,
  useUpsertTrackingAction,
} from "@/api/queries";
import { GoalTrendChart } from "@/components/Charts";
import { DIMENSION_META, ReasonChips } from "@/components/analysis";
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
  formatPercent,
} from "@/lib/format";

const WINDOWS = [90, 180, 365] as const;

const DISTANCE_KEYS: Record<string, MessageKey> = {
  "5k": "distance.5k",
  "10k": "distance.10k",
  half_marathon: "distance.half_marathon",
  marathon: "distance.marathon",
};

const WARNING_KEYS: Record<string, MessageKey> = {
  no_goals: "tracking.warning.no_goals",
  no_snapshots: "tracking.warning.no_snapshots",
  no_accuracy_samples: "tracking.warning.no_accuracy_samples",
  small_accuracy_sample: "tracking.warning.small_accuracy_sample",
  short_history: "tracking.warning.short_history",
};

const ACCURACY_NOTE_KEYS: Record<string, MessageKey> = {
  no_accuracy_samples: "tracking.accuracy.notes.no_accuracy_samples",
  predictions_from_daily_snapshots: "tracking.accuracy.notes.predictions_from_daily_snapshots",
  training_efforts_counted: "tracking.accuracy.notes.training_efforts_counted",
  accuracy_is_observational: "tracking.accuracy.notes.accuracy_is_observational",
  non_race_results_included: "tracking.accuracy.notes.non_race_results_included",
  small_sample: "tracking.accuracy.notes.small_sample",
};

const TREND_KEYS: Record<string, MessageKey> = {
  improving: "tracking.goal.trend.improving",
  stable: "tracking.goal.trend.stable",
  worsening: "tracking.goal.trend.worsening",
  unknown: "tracking.goal.trend.unknown",
};

const GOAL_STATUS_KEYS: Record<string, MessageKey> = {
  ahead: "tracking.goal.status.ahead",
  close: "tracking.goal.status.close",
  behind: "tracking.goal.status.behind",
  unknown: "tracking.goal.status.unknown",
};

const GOAL_STATUS_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  ahead: "success",
  close: "warning",
  behind: "danger",
  unknown: "neutral",
};

const TREND_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  improving: "success",
  stable: "neutral",
  worsening: "danger",
  unknown: "neutral",
};

const ACTION_STATUS_KEYS: Record<string, MessageKey> = {
  pending: "tracking.actions.status.pending",
  in_progress: "tracking.actions.status.in_progress",
  completed: "tracking.actions.status.completed",
};

const VERDICT_KEYS: Record<string, MessageKey> = {
  improved: "tracking.actions.verdict.improved",
  stable: "tracking.actions.verdict.stable",
  worse: "tracking.actions.verdict.worse",
  unknown: "tracking.actions.verdict.unknown",
};

const VERDICT_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  improved: "success",
  stable: "neutral",
  worse: "danger",
  unknown: "neutral",
};

const TRACKING_NOTES = [
  "tracking.notes.snapshots_are_daily",
  "tracking.notes.accuracy_is_observational",
  "tracking.notes.actions_do_not_claim_causality",
  "tracking.notes.not_medical_advice",
] as const satisfies readonly MessageKey[];

function distanceLabel(key: string): MessageKey {
  return DISTANCE_KEYS[key] ?? "distance.10k";
}

function trendIcon(trend: string): LucideIcon {
  if (trend === "improving") return TrendingUp;
  if (trend === "worsening") return TrendingDown;
  return History;
}

export function TrackingPage() {
  const { t, locale, units } = useI18n();
  const [days, setDays] = useState<number>(180);
  const tracking = useTracking(days);

  if (tracking.isLoading) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow={t("tracking.page.eyebrow")} title={t("tracking.page.title")} />
        <div className="analysis-skeleton">
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
        </div>
      </div>
    );
  }

  if (tracking.isError || !tracking.data) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow={t("tracking.page.eyebrow")}
          title={t("tracking.page.title")}
          description={t("tracking.page.subtitle")}
        />
        <ErrorState
          message={
            tracking.error instanceof Error ? tracking.error.message : t("tracking.error")
          }
          onRetry={() => void tracking.refetch()}
        />
      </div>
    );
  }

  const data = tracking.data;
  const accuracy = data.accuracy;
  const accuracySamples = accuracy.samples ?? [];
  const accuracyByDistance = accuracy.by_distance ?? [];
  const accuracyByHorizon = accuracy.by_horizon ?? [];
  const goals = data.goals ?? [];
  const actions = data.actions ?? [];
  const suggestions = data.suggestions ?? [];
  const warnings = data.warnings ?? [];

  return (
    <div className="page-stack tracking-page">
      <PageHeader
        eyebrow={t("tracking.page.eyebrow")}
        title={t("tracking.page.title")}
        description={t("tracking.page.subtitle")}
        actions={
          <div className="tracking-actions">
            <div className="segmented" role="group" aria-label={t("tracking.page.title")}>
              {WINDOWS.map((value) => (
                <button
                  key={value}
                  type="button"
                  className={cn(days === value && "is-active")}
                  aria-pressed={days === value}
                  onClick={() => setDays(value)}
                >
                  {t(`tracking.window.${value}` as MessageKey)}
                </button>
              ))}
            </div>
            <Button
              variant="secondary"
              size="sm"
              loading={tracking.isFetching}
              onClick={() => void tracking.refetch()}
            >
              <RefreshCw size={15} aria-hidden="true" />
              {t("tracking.actions.refresh")}
            </Button>
            <Link to="/forecast" className="button button--secondary button--sm">
              <Sparkles size={15} aria-hidden="true" />
              {t("tracking.actions.forecast")}
            </Link>
          </div>
        }
      />

      {warnings.length ? (
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
      ) : null}

      <section className="tracking-section">
        <SectionHeading
          title={t("tracking.accuracy.title")}
          subtitle={t("tracking.accuracy.subtitle")}
          icon={Gauge}
        />

        {accuracy.overall ? (
          <>
            <div className="tracking-stats">
              <TrackingStat
                label={t("tracking.accuracy.samples")}
                value={formatNumber(accuracy.overall.samples, locale)}
              />
              <TrackingStat
                label={t("tracking.accuracy.mape")}
                value={formatPercent(accuracy.overall.mape_pct, locale, 1)}
              />
              <TrackingStat
                label={t("tracking.accuracy.bias")}
                value={formatPercent(accuracy.overall.mean_bias_pct, locale, 1)}
              />
              <TrackingStat
                label={t("tracking.accuracy.withinRange")}
                value={formatPercent(accuracy.overall.within_range_pct, locale, 0)}
              />
            </div>

            <div className="tracking-duo">
              <Card className="panel tracking-table-card">
                <SectionHeading title={t("tracking.accuracy.byDistance")} icon={Target} />
                <div className="accuracy-table">
                  <div className="accuracy-table__head">
                    <span>{t("tracking.accuracy.sample.distance")}</span>
                    <span>{t("tracking.accuracy.samples")}</span>
                    <span>{t("tracking.accuracy.mape")}</span>
                    <span>{t("tracking.accuracy.withinRange")}</span>
                  </div>
                  {accuracyByDistance.map((item) => (
                    <div className="accuracy-table__row" key={`${item.scope}-${item.key}`}>
                      <span>{t(distanceLabel(item.key))}</span>
                      <strong>{formatNumber(item.samples, locale)}</strong>
                      <strong>{formatPercent(item.mape_pct, locale, 1)}</strong>
                      <strong>{formatPercent(item.within_range_pct, locale, 0)}</strong>
                    </div>
                  ))}
                </div>
              </Card>

              <Card className="panel tracking-table-card">
                <SectionHeading title={t("tracking.accuracy.byHorizon")} icon={History} />
                <div className="accuracy-table accuracy-table--horizon">
                  <div className="accuracy-table__head">
                    <span>{t("tracking.accuracy.byHorizon")}</span>
                    <span>{t("tracking.accuracy.samples")}</span>
                    <span>{t("tracking.accuracy.bias")}</span>
                    <span>{t("tracking.accuracy.withinRange")}</span>
                  </div>
                  {accuracyByHorizon.map((item) => (
                    <div className="accuracy-table__row" key={`${item.scope}-${item.key}`}>
                      <span>
                        {t(`tracking.accuracy.horizon.${item.key}` as MessageKey)}
                      </span>
                      <strong>{formatNumber(item.samples, locale)}</strong>
                      <strong>{formatPercent(item.mean_bias_pct, locale, 1)}</strong>
                      <strong>{formatPercent(item.within_range_pct, locale, 0)}</strong>
                    </div>
                  ))}
                </div>
              </Card>
            </div>

            <Card className="panel tracking-samples">
              <SectionHeading
                title={t("tracking.accuracy.sample.title")}
                subtitle={t("tracking.accuracy.subtitle")}
                icon={CheckCircle2}
              />
              <div className="sample-table">
                <div className="sample-table__head">
                  <span>{t("tracking.accuracy.sample.predictedOn")}</span>
                  <span>{t("tracking.accuracy.sample.distance")}</span>
                  <span>{t("tracking.accuracy.sample.predicted")}</span>
                  <span>{t("tracking.accuracy.sample.actual")}</span>
                  <span>{t("tracking.accuracy.sample.error")}</span>
                  <span>{t("tracking.accuracy.sample.actualOn")}</span>
                  <span />
                </div>
                {accuracySamples.slice(0, 20).map((sample) => (
                  <AccuracyRow key={`${sample.actual_on}-${sample.distance_key}-${sample.activity_id}`} sample={sample} locale={locale} />
                ))}
              </div>
              <ul className="tracking-notes">
                {(accuracy.notes ?? [])
                  .filter((note) => ACCURACY_NOTE_KEYS[note])
                  .map((note) => (
                    <li key={note}>{t(ACCURACY_NOTE_KEYS[note])}</li>
                  ))}
              </ul>
            </Card>
          </>
        ) : (
          <Card className="panel">
            <EmptyState
              icon={Gauge}
              title={t("tracking.accuracy.empty.title")}
              description={t("tracking.accuracy.empty.body")}
            />
          </Card>
        )}
      </section>

      <section className="tracking-section">
        <SectionHeading
          title={t("tracking.goals.title")}
          subtitle={t("tracking.goals.subtitle")}
          icon={Target}
        />
        {goals.length ? (
          <div className="tracking-goal-grid">
            {goals.map((goal) => (
              <GoalCard key={goal.distance_key} goal={goal} locale={locale} units={units} />
            ))}
          </div>
        ) : (
          <Card className="panel">
            <EmptyState
              icon={Target}
              title={t("tracking.goals.empty.title")}
              description={t("tracking.goals.empty.body")}
              action={
                <Link to="/performance" className="button button--secondary button--sm">
                  {t("tracking.goals.empty.action")}
                  <ArrowRight size={14} aria-hidden="true" />
                </Link>
              }
            />
          </Card>
        )}
      </section>

      <section className="tracking-section">
        <SectionHeading
          title={t("tracking.actions.title")}
          subtitle={t("tracking.actions.subtitle")}
          icon={CheckCircle2}
        />

        {actions.length ? (
          <div className="tracked-action-list">
            {actions.map((action) => (
              <TrackedActionCard key={action.dimension_key} action={action} />
            ))}
          </div>
        ) : (
          <Card className="panel">
            <EmptyState
              compact
              icon={CheckCircle2}
              title={t("tracking.actions.empty.title")}
              description={t("tracking.actions.empty.body")}
            />
          </Card>
        )}

        <Card className="panel tracking-suggestions">
          <SectionHeading
            title={t("tracking.actions.suggestions")}
            subtitle={t("tracking.actions.suggestions.subtitle")}
            icon={Info}
          />
          {suggestions.length ? (
            <div className="suggestion-list">
              {suggestions.map((suggestion) => (
                <SuggestionRow
                  key={suggestion.dimension_key}
                  suggestion={suggestion}
                />
              ))}
            </div>
          ) : (
            <p className="tracking-empty-copy">{t("tracking.actions.none")}</p>
          )}
        </Card>
      </section>

      <Card className="panel tracking-method">
        <SectionHeading title={t("tracking.page.title")} icon={Info} />
        <ul className="tracking-notes">
          {TRACKING_NOTES.map((note) => (
            <li key={note}>{t(note)}</li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function TrackingStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="tracking-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function AccuracyRow({ sample, locale }: { sample: AccuracySample; locale: Locale }) {
  const { t } = useI18n();
  return (
    <div className="sample-table__row">
      <span>{formatDate(sample.predicted_on, locale)}</span>
      <span>
        {t(distanceLabel(sample.distance_key))}
        <small>{t("tracking.accuracy.sample.horizon", { days: sample.horizon_days })}</small>
      </span>
      <strong>{formatClock(sample.predicted_s)}</strong>
      <strong>{formatClock(sample.actual_s)}</strong>
      <strong className={cn(sample.error_s > 0 && "is-slow", sample.error_s < 0 && "is-fast")}>
        {sample.error_s > 0 ? "+" : ""}
        {sample.error_s < 0 ? "−" : ""}
        {formatClock(Math.abs(sample.error_s))}
        <small>{formatPercent(sample.error_pct, locale, 1)}</small>
      </strong>
      <span>
        {formatDate(sample.actual_on, locale)}
        <small>
          {sample.is_race
            ? t("tracking.accuracy.sample.race")
            : t("tracking.accuracy.sample.training")}
        </small>
      </span>
      <Badge tone={sample.within_range ? "success" : "warning"}>
        {sample.within_range
          ? t("tracking.accuracy.sample.within")
          : t("tracking.accuracy.sample.outside")}
      </Badge>
    </div>
  );
}

function GoalCard({
  goal,
  locale,
  units,
}: {
  goal: GoalTracking;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  const TrendIcon = trendIcon(goal.trend);
  const change = goal.change_28d_s;
  return (
    <Card className="panel tracking-goal">
      <div className="tracking-goal__head">
        <div>
          <span className="distance-card__key">{t(distanceLabel(goal.distance_key))}</span>
          <small>
            {goal.race_name ? `${goal.race_name} · ` : ""}
            {goal.target_date ? formatDate(goal.target_date, locale) : t("tracking.goal.noDate")}
          </small>
        </div>
        <Badge tone={GOAL_STATUS_TONE[goal.status] ?? "neutral"}>
          {t(GOAL_STATUS_KEYS[goal.status] ?? "tracking.goal.status.unknown")}
        </Badge>
      </div>

      <div className="tracking-goal__times">
        <div>
          <span>{t("tracking.goal.target")}</span>
          <strong>{formatClock(goal.target_time_s)}</strong>
        </div>
        <div>
          <span>{t("tracking.goal.predicted")}</span>
          <strong>{formatClock(goal.current_time_s)}</strong>
        </div>
        <div>
          <span>{t("tracking.goal.gap")}</span>
          <strong className={cn(goal.gap_s != null && goal.gap_s < 0 && "is-ahead")}>
            {goal.gap_s == null
              ? "—"
              : `${goal.gap_s > 0 ? "+" : "−"}${formatClock(Math.abs(goal.gap_s))}`}
          </strong>
        </div>
        <div>
          <span>{t("tracking.accuracy.sample.distance")}</span>
          <strong>{formatDistance(goal.distance_m, units, locale, { digits: 1 })}</strong>
        </div>
      </div>

      <div className="tracking-goal__trend">
        <Badge tone={TREND_TONE[goal.trend] ?? "neutral"}>
          <TrendIcon size={13} aria-hidden="true" />
          {t(TREND_KEYS[goal.trend] ?? "tracking.goal.trend.unknown")}
        </Badge>
        <span>
          {change == null
            ? t("tracking.goal.trend.unknown")
            : `${change > 0 ? "+" : "−"}${formatClock(Math.abs(change))} · ${formatPercent(
                goal.change_28d_pct,
                locale,
                1,
              )}`}
        </span>
        {goal.days_to_target != null ? (
          <span>{t("tracking.goal.days", { days: goal.days_to_target })}</span>
        ) : null}
      </div>

      <div className="tracking-goal__readiness">
        <div className="tracking-goal__readiness-head">
          <span>{t("tracking.goal.readiness")}</span>
          <strong>{formatPercent(goal.readiness_pct, locale, 0)}</strong>
        </div>
        <ProgressBar
          value={goal.readiness_pct ?? 0}
          tone={goal.status === "ahead" ? "accent" : goal.status === "behind" ? "danger" : "warning"}
        />
      </div>

      <div className="tracking-goal__chart">
        <span className="eyebrow">{t("tracking.goal.history")}</span>
        <GoalTrendChart points={goal.history ?? []} targetTimeS={goal.target_time_s} />
      </div>

      <p className="tracking-goal__review">
        {t("tracking.goal.reviewed", { date: formatDate(goal.last_reviewed_at, locale) })}
        {goal.confidence
          ? ` · ${t("tracking.goal.confidence")}: ${t(
              `performance.confidence.${goal.confidence}` as MessageKey,
            )}`
          : ""}
      </p>

      {(goal.revisions ?? []).length ? (
        <details className="tracking-revisions">
          <summary>{t("tracking.goal.revisions")}</summary>
          <div className="tracking-revisions__list">
            {(goal.revisions ?? [])
              .slice()
              .reverse()
              .map((revision) => (
                <div className="tracking-revision" key={`${revision.created_at}-${revision.target_time_s}`}>
                  <span>{formatDateTime(revision.created_at, locale)}</span>
                  <strong>{formatClock(revision.target_time_s)}</strong>
                  <small>
                    {revision.change_s == null
                      ? t("tracking.goal.reviewed", {
                          date: formatDate(revision.created_at, locale),
                        })
                      : t("tracking.goal.revision.change", {
                          change: `${revision.change_s > 0 ? "+" : "−"}${formatClock(
                            Math.abs(revision.change_s),
                          )}`,
                        })}
                  </small>
                  <small>
                    {revision.prediction_time_s
                      ? t("tracking.goal.revision.atPrediction", {
                          time: formatClock(revision.prediction_time_s),
                        })
                      : t("common.noData")}
                  </small>
                </div>
              ))}
          </div>
        </details>
      ) : null}
    </Card>
  );
}

function SuggestionRow({ suggestion }: { suggestion: ActionSuggestion }) {
  const { t } = useI18n();
  const upsert = useUpsertTrackingAction();
  const meta = DIMENSION_META[suggestion.dimension_key];
  const Icon = meta?.icon ?? Target;
  return (
    <div className="suggestion-row">
      <span className="suggestion-row__icon">
        <Icon size={17} aria-hidden="true" />
      </span>
      <div className="suggestion-row__copy">
        <div className="suggestion-row__head">
          <strong>{meta ? t(meta.label) : suggestion.dimension_key}</strong>
          {suggestion.priority ? (
            <Badge tone="info">
              {t("tracking.actions.priority", { priority: suggestion.priority })}
            </Badge>
          ) : null}
          {suggestion.score != null ? (
            <Badge tone="neutral">{Math.round(suggestion.score)}/100</Badge>
          ) : null}
        </div>
        <ReasonChips
          reasons={(suggestion.reasons ?? []).slice(0, 3)}
          className="suggestion-row__reasons"
        />
      </div>
      {suggestion.tracked ? (
        <Badge tone="success">{t("tracking.actions.tracked")}</Badge>
      ) : (
        <Button
          variant="secondary"
          size="sm"
          loading={upsert.isPending}
          onClick={() =>
            upsert.mutate({
              dimensionKey: suggestion.dimension_key,
              payload: { status: "pending", note: null },
            })
          }
        >
          {t("tracking.actions.track")}
        </Button>
      )}
    </div>
  );
}

function TrackedActionCard({ action }: { action: TrackedAction }) {
  const { t, locale } = useI18n();
  const upsert = useUpsertTrackingAction();
  const remove = useDeleteTrackingAction();
  const [note, setNote] = useState(action.note ?? "");
  const [problem, setProblem] = useState<string | null>(null);
  const meta = DIMENSION_META[action.dimension_key];
  const Icon = meta?.icon ?? Target;

  const save = (status: "pending" | "in_progress" | "completed") => {
    setProblem(null);
    upsert.mutate(
      {
        dimensionKey: action.dimension_key,
        payload: { status, note: note.trim() || null },
      },
      {
        onError: (error) =>
          setProblem(error instanceof Error ? error.message : t("tracking.actions.error")),
      },
    );
  };

  return (
    <Card className="panel tracked-action">
      <div className="tracked-action__head">
        <div className="tracked-action__title">
          <span className="suggestion-row__icon">
            <Icon size={17} aria-hidden="true" />
          </span>
          <div>
            <strong>{meta ? t(meta.label) : action.dimension_key}</strong>
            <small>{formatDate(action.created_at, locale)}</small>
          </div>
        </div>
        <div className="tracked-action__badges">
          <Badge tone={action.status === "completed" ? "success" : "info"}>
            {t(ACTION_STATUS_KEYS[action.status] ?? "tracking.actions.status.pending")}
          </Badge>
          <Badge tone={VERDICT_TONE[action.verdict] ?? "neutral"}>
            {t(VERDICT_KEYS[action.verdict] ?? "tracking.actions.verdict.unknown")}
          </Badge>
        </div>
      </div>

      <div className="tracked-action__metrics">
        <div>
          <span>{t("tracking.actions.baseline")}</span>
          <strong>{action.baseline_score == null ? "—" : Math.round(action.baseline_score)}</strong>
        </div>
        <div>
          <span>{t("tracking.actions.current")}</span>
          <strong>{action.current_score == null ? "—" : Math.round(action.current_score)}</strong>
        </div>
        <div>
          <span>{t("tracking.actions.delta")}</span>
          <strong className={cn(action.delta != null && action.delta > 0 && "is-ahead")}>
            {action.delta == null
              ? "—"
              : `${action.delta > 0 ? "+" : ""}${formatNumber(action.delta, locale, 1)}`}
          </strong>
        </div>
      </div>

      <div className="tracked-action__status" role="group" aria-label={t("tracking.actions.title")}>
        {(["pending", "in_progress", "completed"] as const).map((status) => (
          <button
            key={status}
            type="button"
            className={cn(action.status === status && "is-active")}
            aria-pressed={action.status === status}
            onClick={() => save(status)}
            disabled={upsert.isPending}
          >
            {t(ACTION_STATUS_KEYS[status])}
          </button>
        ))}
      </div>

      <label className="tracked-action__note">
        <span>{t("tracking.actions.note")}</span>
        <textarea
          value={note}
          rows={2}
          maxLength={2000}
          placeholder={t("tracking.actions.notePlaceholder")}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>

      {problem ? <p className="tracked-action__problem">{problem}</p> : null}

      <div className="tracked-action__actions">
        <Button
          variant="primary"
          size="sm"
          loading={upsert.isPending}
          onClick={() => save(action.status as "pending" | "in_progress" | "completed")}
        >
          {t("tracking.actions.save")}
        </Button>
        <Button
          variant="danger"
          size="sm"
          loading={remove.isPending}
          onClick={() =>
            remove.mutate(action.dimension_key, {
              onError: (error) =>
                setProblem(
                  error instanceof Error ? error.message : t("tracking.actions.error"),
                ),
            })
          }
        >
          {t("tracking.actions.remove")}
        </Button>
      </div>
    </Card>
  );
}
