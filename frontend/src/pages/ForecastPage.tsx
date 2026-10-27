import { useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  ArrowRight,
  CircleAlert,
  Gauge,
  Info,
  RefreshCw,
  Route,
  Sparkles,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

import type {
  ForecastGoal,
  ForecastScenario,
  ScenarioProjection,
} from "@/api/client";
import { useForecast } from "@/api/queries";
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
  formatPercent,
} from "@/lib/format";

const DISTANCE_KEYS: Record<string, MessageKey> = {
  "5k": "distance.5k",
  "10k": "distance.10k",
  half_marathon: "distance.half_marathon",
  marathon: "distance.marathon",
};

const SCENARIO_KEYS: Record<string, MessageKey> = {
  maintain: "forecast.scenario.maintain",
  consistency: "forecast.scenario.consistency",
  specificity: "forecast.scenario.specificity",
  recovery: "forecast.scenario.recovery",
};

const SOURCE_KEYS: Record<string, MessageKey> = {
  goal: "forecast.baseline.source.goal",
  race: "forecast.baseline.source.race",
  default: "forecast.baseline.source.default",
};

const WARNING_KEYS: Record<string, MessageKey> = {
  no_anchor: "forecast.warning.no_anchor",
  no_recent_volume: "forecast.warning.no_recent_volume",
  no_consistency_data: "forecast.warning.no_consistency_data",
  no_load_data: "forecast.warning.no_load_data",
  no_goal: "forecast.warning.no_goal",
  horizon_before_goal: "forecast.warning.horizon_before_goal",
};

const GOAL_STATUS_KEYS: Record<string, MessageKey> = {
  ahead: "forecast.goal.status.ahead",
  close: "forecast.goal.status.close",
  behind: "forecast.goal.status.behind",
  unknown: "forecast.goal.status.unknown",
};

const GOAL_STATUS_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  ahead: "success",
  close: "warning",
  behind: "danger",
  unknown: "neutral",
};

const CONFIDENCE_KEYS: Record<string, MessageKey> = {
  simulation_not_forecast: "forecast.confidence.simulation_not_forecast",
  no_consistency_data: "forecast.confidence.no_consistency_data",
  already_consistent: "forecast.confidence.already_consistent",
  spillover_from_focus: "forecast.confidence.spillover_from_focus",
  no_specificity_data: "forecast.confidence.no_specificity_data",
  no_load_data: "forecast.confidence.no_load_data",
  no_fatigue_to_recover: "forecast.confidence.no_fatigue_to_recover",
  current_training_only: "forecast.confidence.current_training_only",
};

const NOTE_KEYS: Record<string, MessageKey> = {
  simulation_not_forecast: "forecast.notes.simulation_not_forecast",
  effects_are_capped: "forecast.notes.effects_are_capped",
  training_assumptions_explicit: "forecast.notes.training_assumptions_explicit",
  not_medical_advice: "forecast.notes.not_medical_advice",
  focus_defaults_to_10k: "forecast.notes.focus_defaults_to_10k",
  capped_effect: "forecast.notes.capped_effect",
  uncertainty_grows_with_horizon: "forecast.notes.uncertainty_grows_with_horizon",
  horizon_8_weeks: "forecast.notes.horizon_8_weeks",
  horizon_12_weeks: "forecast.notes.horizon_12_weeks",
  deload_can_reduce_fitness: "forecast.notes.deload_can_reduce_fitness",
  specificity_is_distance_dependent: "forecast.notes.specificity_is_distance_dependent",
};

const EVIDENCE_KEYS: Record<string, MessageKey> = {
  consistency_score: "forecast.evidence.consistency_score",
  active_weeks: "forecast.evidence.active_weeks",
  weeks: "forecast.evidence.weeks",
  runs_per_week: "forecast.evidence.runs_per_week",
  specificity_score: "forecast.evidence.specificity_score",
  longest_28_m: "forecast.evidence.longest_28_m",
  target_long_m: "forecast.evidence.target_long_m",
  hard_sessions: "forecast.evidence.hard_sessions",
  weekly_avg_m: "forecast.evidence.weekly_avg_m",
  load_ratio: "forecast.evidence.load_ratio",
  load_status: "forecast.evidence.load_status",
  recovery_score: "forecast.evidence.recovery_score",
};

const METHOD_ITEMS = [
  {
    icon: Gauge,
    title: "forecast.method.capped.title" as MessageKey,
    body: "forecast.method.capped.body" as MessageKey,
  },
  {
    icon: Route,
    title: "forecast.method.assumptions.title" as MessageKey,
    body: "forecast.method.assumptions.body" as MessageKey,
  },
  {
    icon: TrendingUp,
    title: "forecast.method.uncertainty.title" as MessageKey,
    body: "forecast.method.uncertainty.body" as MessageKey,
  },
  {
    icon: Info,
    title: "forecast.method.noPromise.title" as MessageKey,
    body: "forecast.method.noPromise.body" as MessageKey,
  },
];

function scenarioTone(key: string): "accent" | "info" | "warning" | "neutral" {
  if (key === "specificity") return "warning";
  if (key === "recovery") return "info";
  if (key === "consistency") return "accent";
  return "neutral";
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

function evidenceValue(
  key: string,
  value: number | string | boolean | null,
  units: Units,
  locale: Locale,
  t: (key: MessageKey) => string,
): string {
  if (value === null || value === undefined) return "—";
  if (key === "load_status") {
    const statusKey = `analysis.status.${String(value)}` as MessageKey;
    return t(statusKey);
  }
  if (key.endsWith("_m")) return formatDistance(Number(value), units, locale, { digits: 1 });
  if (key.endsWith("_score")) return formatNumber(Number(value), locale, 0);
  if (key === "load_ratio") return formatNumber(Number(value), locale, 2);
  if (key === "runs_per_week") return formatNumber(Number(value), locale, 1);
  return String(value);
}

export function ForecastPage() {
  const { t, locale, units } = useI18n();
  const [weeks, setWeeks] = useState<8 | 12>(8);
  const forecast = useForecast(weeks);

  if (forecast.isLoading) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow={t("forecast.page.eyebrow")} title={t("forecast.page.title")} />
        <div className="analysis-skeleton">
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
        </div>
      </div>
    );
  }

  if (forecast.isError || !forecast.data) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow={t("forecast.page.eyebrow")}
          title={t("forecast.page.title")}
          description={t("forecast.page.subtitle")}
        />
        <ErrorState
          message={
            forecast.error instanceof Error ? forecast.error.message : t("forecast.error")
          }
          onRetry={() => void forecast.refetch()}
        />
      </div>
    );
  }

  const data = forecast.data;
  const training = data.training ?? {};
  const scenarios = data.scenarios ?? [];
  const warnings = data.warnings ?? [];
  const insufficient = data.status === "insufficient" || data.baseline.anchor_time_s == null;
  const focusLabel = DISTANCE_KEYS[data.focus_distance_key] ?? data.focus_distance_key;
  const focusBaseline = (data.baseline.distances ?? []).find(
    (item) => item.distance_key === data.focus_distance_key,
  );

  return (
    <div className="page-stack forecast-page">
      <PageHeader
        eyebrow={t("forecast.page.eyebrow")}
        title={t("forecast.page.title")}
        description={t("forecast.page.subtitle")}
        actions={
          <div className="forecast-actions">
            <div className="segmented" role="group" aria-label={t("forecast.horizon.label")}>
              {([8, 12] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  className={cn(weeks === value && "is-active")}
                  aria-pressed={weeks === value}
                  onClick={() => setWeeks(value)}
                >
                  {t(`forecast.horizon.${value}` as MessageKey)}
                </button>
              ))}
            </div>
            <Button
              variant="secondary"
              size="sm"
              loading={forecast.isFetching}
              onClick={() => void forecast.refetch()}
            >
              <RefreshCw size={15} aria-hidden="true" />
              {t("forecast.actions.refresh")}
            </Button>
            <Link to="/tracking" className="button button--secondary button--sm">
              <ArrowRight size={15} aria-hidden="true" />
              {t("forecast.actions.tracking")}
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

      {insufficient ? (
        <Card className="panel">
          <EmptyState
            icon={Sparkles}
            title={t("forecast.empty.title")}
            description={t("forecast.empty.body")}
            action={
              <Link to="/imports" className="button button--primary button--sm">
                <ArrowRight size={15} aria-hidden="true" />
                {t("forecast.empty.action")}
              </Link>
            }
          />
        </Card>
      ) : (
        <section className="forecast-baseline">
          <Card className="panel forecast-focus">
            <div className="forecast-focus__head">
              <div>
                <span className="eyebrow">{t("forecast.baseline.eyebrow")}</span>
                <h2>{t("forecast.baseline.title")}</h2>
              </div>
              <Badge tone="info">{t(SOURCE_KEYS[data.focus_source] ?? "forecast.baseline.source.default")}</Badge>
            </div>

            <div className="forecast-focus__distance">
              <span>{t("forecast.baseline.focus")}</span>
              <strong>{t(focusLabel)}</strong>
              <small>{formatDistance(data.focus_distance_m, units, locale, { digits: 1 })}</small>
            </div>

            <div className="forecast-focus__value">
              <strong>{formatClock(data.baseline.anchor_time_s)}</strong>
              <span>
                {focusBaseline?.pace_s_per_km
                  ? formatPace(focusBaseline.pace_s_per_km, units)
                  : t("common.noData")}
              </span>
            </div>

            <div className="forecast-focus__range">
              <span>{t("forecast.baseline.range")}</span>
              <strong>
                {formatClock(data.baseline.anchor_low_s)} –{" "}
                {formatClock(data.baseline.anchor_high_s)}
              </strong>
            </div>

            <div className="forecast-focus__confidence">
              <div className="forecast-focus__confidence-head">
                <span>{t("forecast.baseline.confidence")}</span>
                <strong>{Math.round(data.baseline.confidence_score * 100)}%</strong>
              </div>
              <ProgressBar
                value={data.baseline.confidence_score * 100}
                tone={progressTone(data.baseline.confidence)}
              />
            </div>

            {data.goal ? (
              <div className="forecast-goal">
                <div className="forecast-goal__head">
                  <span>{t("forecast.goal.title")}</span>
                  <Badge tone={GOAL_STATUS_TONE[data.goal.baseline_status] ?? "neutral"}>
                    {t(
                      GOAL_STATUS_KEYS[data.goal.baseline_status] ??
                        "forecast.goal.status.unknown",
                    )}
                  </Badge>
                </div>
                <div className="forecast-goal__grid">
                  <GoalValue
                    label={t("forecast.goal.target")}
                    value={formatClock(data.goal.target_time_s)}
                  />
                  <GoalValue
                    label={t("forecast.goal.date")}
                    value={
                      data.goal.target_date
                        ? formatDate(data.goal.target_date, locale)
                        : t("common.noData")
                    }
                  />
                  <GoalValue
                    label={t("forecast.goal.baselineGap")}
                    value={formatGap(data.goal.baseline_gap_s)}
                    tone={
                      data.goal.baseline_gap_s != null && data.goal.baseline_gap_s > 0
                        ? "is-ahead"
                        : data.goal.baseline_gap_s != null && data.goal.baseline_gap_s < 0
                          ? "is-behind"
                          : undefined
                    }
                  />
                </div>
                <p>{t("forecast.goal.note")}</p>
              </div>
            ) : null}
          </Card>

          <Card className="panel forecast-training">
            <SectionHeading
              title={t("forecast.training.title")}
              subtitle={t("forecast.training.subtitle")}
              icon={Route}
            />
            <div className="forecast-training__grid">
              <TrainingStat
                label={t("forecast.training.weekly")}
                value={formatDistance(training.weekly_avg_m, units, locale, { digits: 1 })}
              />
              <TrainingStat
                label={t("forecast.training.longest")}
                value={formatDistance(training.longest_28_m, units, locale, { digits: 1 })}
              />
              <TrainingStat
                label={t("forecast.training.activeWeeks")}
                value={`${training.active_weeks ?? 0} / ${training.weeks ?? 0}`}
              />
              <TrainingStat
                label={t("forecast.training.runsPerWeek")}
                value={formatNumber(training.runs_per_week, locale, 1)}
              />
              <TrainingStat
                label={t("forecast.training.sessions")}
                value={formatNumber(training.sessions_28, locale)}
              />
              <TrainingStat
                label={t("forecast.training.loadRatio")}
                value={
                  training.load_ratio == null
                    ? "—"
                    : formatNumber(training.load_ratio, locale, 2)
                }
              />
            </div>
            <div className="forecast-dimensions">
              <DimensionBar
                label={t("forecast.training.consistency")}
                value={training.consistency_score}
              />
              <DimensionBar
                label={t("forecast.training.specificity")}
                value={training.specificity_score}
              />
              <DimensionBar
                label={t("forecast.training.recovery")}
                value={training.recovery_score}
              />
            </div>
            {data.focus_source === "default" ? (
              <p className="analysis-note">{t("forecast.notes.focus_defaults_to_10k")}</p>
            ) : null}
          </Card>
        </section>
      )}

      {!insufficient ? (
        <section className="forecast-scenarios">
          <SectionHeading
            title={t("forecast.scenarios.title")}
            subtitle={t("forecast.scenarios.subtitle")}
            icon={Sparkles}
            action={<Badge tone="info">{t(`forecast.horizon.${data.weeks}` as MessageKey)}</Badge>}
          />
          <div className="forecast-scenario-grid">
            {scenarios.map((scenario) => (
              <ScenarioCard
                key={scenario.key}
                scenario={scenario}
                goal={data.goal ?? null}
                locale={locale}
                units={units}
              />
            ))}
          </div>
        </section>
      ) : null}

      <Card className="panel forecast-method">
        <SectionHeading
          title={t("forecast.method.title")}
          subtitle={t("forecast.method.subtitle")}
          icon={Info}
        />
        <div className="method-grid">
          {METHOD_ITEMS.map((item) => (
            <MethodItem key={item.title} icon={item.icon} title={t(item.title)}>
              {t(item.body)}
            </MethodItem>
          ))}
        </div>
        <ul className="forecast-notes">
          {(data.notes ?? [])
            .filter((note) => NOTE_KEYS[note])
            .map((note) => (
              <li key={note}>{t(NOTE_KEYS[note])}</li>
            ))}
        </ul>
      </Card>
    </div>
  );
}

function ScenarioCard({
  scenario,
  goal,
  locale,
  units,
}: {
  scenario: ForecastScenario;
  goal: ForecastGoal | null;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const delta = scenario.delta_s;
  const faster = delta !== null && delta !== undefined && delta < -0.5;
  const slower = delta !== null && delta !== undefined && delta > 0.5;
  const tone = scenarioTone(scenario.key);
  const scenarioDistances = scenario.distances ?? [];
  const pace = scenarioDistances.find((item) => item.pace_s_per_km)?.pace_s_per_km;

  return (
    <Card className={cn("panel scenario-card", `scenario-card--${scenario.key}`)}>
      <div className="scenario-card__head">
        <Badge tone={tone}>{t(SCENARIO_KEYS[scenario.key] ?? "forecast.scenario.maintain")}</Badge>
        <Badge tone={confidenceTone(scenario.confidence)}>
          {t("forecast.scenario.confidence", {
            score: Math.round(scenario.confidence_score * 100),
          })}
        </Badge>
      </div>

      <div className="scenario-card__value">
        <strong>{formatClock(scenario.anchor_time_s)}</strong>
        <span>{pace ? formatPace(pace, units) : t("common.noData")}</span>
      </div>

      <p className={cn("scenario-card__delta", faster && "is-faster", slower && "is-slower")}>
        {delta === null || delta === undefined || Math.abs(delta) < 0.5
          ? t("forecast.scenario.delta.same")
          : faster
            ? t("forecast.scenario.delta.faster", { delta: formatClock(Math.abs(delta)) })
            : t("forecast.scenario.delta.slower", { delta: formatClock(delta) })}
      </p>

      <div className="scenario-card__ranges">
        <div>
          <span>{t("forecast.scenario.range")}</span>
          <strong>
            {formatClock(scenario.anchor_low_s)} – {formatClock(scenario.anchor_high_s)}
          </strong>
        </div>
        <div>
          <span>{t("forecast.scenario.effect")}</span>
          <strong>{formatPercent(scenario.effect_pct, locale, 1)}</strong>
        </div>
      </div>

      {goal && scenario.goal_gap_s != null ? (
        <div className="scenario-card__goal">
          <div>
            <span>{t("forecast.goal.scenarioGap")}</span>
            <strong
              className={cn(
                scenario.goal_gap_s > 0 && "is-ahead",
                scenario.goal_gap_s < 0 && "is-behind",
              )}
            >
              {formatGap(scenario.goal_gap_s)}
            </strong>
          </div>
          <Badge tone={GOAL_STATUS_TONE[scenario.goal_status] ?? "neutral"}>
            {t(
              GOAL_STATUS_KEYS[scenario.goal_status] ?? "forecast.goal.status.unknown",
            )}
          </Badge>
          <small>
            {t("forecast.goal.target")} {formatClock(goal.target_time_s)}
          </small>
        </div>
      ) : null}

      <div className="scenario-card__block">
        <h3>{t("forecast.scenario.assumptions")}</h3>
        <div className="scenario-chips">
          {(scenario.assumptions ?? []).map((assumption) => (
            <span className="reason-chip" key={assumption}>
              {t(`forecast.assumption.${assumption}` as MessageKey)}
            </span>
          ))}
        </div>
      </div>

      <div className="scenario-card__block">
        <h3>{t("forecast.scenario.evidence")}</h3>
        <div className="scenario-evidence">
          {Object.entries(scenario.evidence ?? {})
            .filter(([key, value]) => EVIDENCE_KEYS[key] && value !== null)
            .map(([key, value]) => (
              <div className="scenario-evidence__row" key={key}>
                <span>{t(EVIDENCE_KEYS[key])}</span>
                <strong>{evidenceValue(key, value, units, locale, t)}</strong>
              </div>
            ))}
        </div>
      </div>

      <div className="scenario-card__reasons">
        {(scenario.confidence_reasons ?? []).map((reason) => (
          <span className="reason-chip" key={reason}>
            {CONFIDENCE_KEYS[reason] ? t(CONFIDENCE_KEYS[reason]) : reason}
          </span>
        ))}
      </div>

      <button
        type="button"
        className="scenario-card__toggle"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        {t("forecast.scenario.distances")}
        <ArrowRight size={13} className={cn(open && "is-open")} aria-hidden="true" />
      </button>

      {open ? (
        <div className="scenario-distances">
          {scenarioDistances.map((item) => (
            <ScenarioDistance
              key={item.distance_key}
              item={item}
              locale={locale}
              units={units}
            />
          ))}
        </div>
      ) : null}

      <ul className="scenario-card__notes">
        {(scenario.notes ?? [])
          .filter((note) => NOTE_KEYS[note])
          .map((note) => (
            <li key={note}>{t(NOTE_KEYS[note])}</li>
          ))}
      </ul>
    </Card>
  );
}

function ScenarioDistance({
  item,
  locale,
  units,
}: {
  item: ScenarioProjection;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  const delta = item.delta_s;
  return (
    <div className="scenario-distance">
      <span>
        {t(DISTANCE_KEYS[item.distance_key] ?? "distance.10k")}
        <small>{formatDistance(item.distance_m, units, locale, { digits: 1 })}</small>
      </span>
      <strong>{formatClock(item.time_s)}</strong>
      <small>
        {item.pace_s_per_km ? formatPace(item.pace_s_per_km, units) : t("common.noData")}
      </small>
      <small>
        {delta === null || delta === undefined || Math.abs(delta) < 0.5
          ? t("forecast.scenario.delta.same")
          : delta < 0
            ? t("forecast.scenario.delta.faster", { delta: formatClock(Math.abs(delta)) })
            : t("forecast.scenario.delta.slower", { delta: formatClock(delta) })}
      </small>
      <small className="scenario-distance__range">
        {formatClock(item.low_s)} – {formatClock(item.high_s)}
      </small>
    </div>
  );
}

function formatGap(gap: number | null | undefined): string {
  if (gap == null) return "—";
  return formatClock(Math.abs(gap));
}

function GoalValue({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="forecast-goal__value">
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
    </div>
  );
}

function TrainingStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="forecast-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DimensionBar({ label, value }: { label: string; value: number | null | undefined }) {
  return (
    <div className="forecast-dimension">
      <div className="forecast-dimension__head">
        <span>{label}</span>
        <strong>
          {value === null || value === undefined ? "—" : Math.min(100, Math.round(value))}
        </strong>
      </div>
      <ProgressBar
        value={value ?? 0}
        tone={value !== null && value !== undefined && value < 50 ? "danger" : "accent"}
      />
    </div>
  );
}

function MethodItem({
  icon: Icon,
  title,
  children,
}: {
  icon: LucideIcon;
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
