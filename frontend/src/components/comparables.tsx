import { useEffect, useState } from "react";
import { HeartPulse, Info } from "lucide-react";

import { usePaceHr } from "@/api/queries";
import { PaceHrChart } from "@/components/Charts";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  SectionHeading,
  Skeleton,
} from "@/components/ui";
import { useI18n, type MessageKey } from "@/i18n";
import { cn } from "@/lib/cn";
import { formatClock, formatNumber, formatPace } from "@/lib/format";

const WARNING_KEYS: Record<string, MessageKey> = {
  no_running_activities: "progress.paceHr.warning.no_running_activities",
  no_hr: "progress.paceHr.warning.no_hr",
  no_comparable_sessions: "progress.paceHr.warning.no_comparable_sessions",
  no_comparable_group: "progress.paceHr.warning.no_comparable_group",
  few_sessions: "progress.paceHr.warning.few_sessions",
  short_span: "progress.paceHr.warning.short_span",
  narrow_hr_range: "progress.paceHr.warning.narrow_hr_range",
  temperature_not_available: "progress.paceHr.warning.temperature_not_available",
};

const NOTE_KEYS: Record<string, MessageKey> = {
  pace_hr_is_observational: "progress.paceHr.note.pace_hr_is_observational",
  same_distance_and_terrain: "progress.paceHr.note.same_distance_and_terrain",
  hr_adjusted_line: "progress.paceHr.note.hr_adjusted_line",
  temperature_not_controlled: "progress.paceHr.note.temperature_not_controlled",
  environment_adjusted_pace: "progress.paceHr.note.environment_adjusted_pace",
  terrain_adjustment_estimated: "progress.paceHr.note.terrain_adjustment_estimated",
  environment_context_only: "progress.paceHr.note.environment_context_only",
  temperature_from_streams: "progress.paceHr.note.temperature_from_streams",
  temperature_not_available: "progress.paceHr.note.temperature_not_available",
  heat_adjustment_applied: "progress.paceHr.note.heat_adjustment_applied",
  load_is_estimated: "progress.paceHr.note.load_is_estimated",
  not_medical_advice: "progress.paceHr.note.not_medical_advice",
  races_excluded: "progress.paceHr.note.races_excluded",
  hard_sessions_excluded: "progress.paceHr.note.hard_sessions_excluded",
};

const REASON_KEYS: Record<string, MessageKey> = {
  few_sessions: "progress.paceHr.reason.few_sessions",
  short_span: "progress.paceHr.reason.short_span",
  narrow_hr_range: "progress.paceHr.reason.narrow_hr_range",
  no_regression: "progress.paceHr.reason.no_regression",
  temperature_not_controlled: "progress.paceHr.reason.temperature_not_controlled",
  temperature_not_available: "progress.paceHr.reason.temperature_not_available",
};

const CONCLUSION_KEYS: Record<string, MessageKey> = {
  faster_same_hr: "progress.paceHr.conclusion.faster",
  slower_same_hr: "progress.paceHr.conclusion.slower",
  stable_same_hr: "progress.paceHr.conclusion.stable",
  provisional_same_hr: "progress.paceHr.conclusion.provisional",
  insufficient_data: "progress.paceHr.conclusion.insufficient",
};

const DISTANCE_KEYS: Record<string, MessageKey> = {
  short: "progress.paceHr.distance.short",
  medium: "progress.paceHr.distance.medium",
  long: "progress.paceHr.distance.long",
  very_long: "progress.paceHr.distance.very_long",
};

const TERRAIN_KEYS: Record<string, MessageKey> = {
  flat: "progress.paceHr.terrain.flat",
  rolling: "progress.paceHr.terrain.rolling",
  hilly: "progress.paceHr.terrain.hilly",
  unknown: "progress.paceHr.terrain.unknown",
};

export function PaceHrPanel({ days }: { days: number }) {
  const { t, locale, units } = useI18n();
  const analysis = usePaceHr(days);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    if (!analysis.data) return;
    const keys = new Set((analysis.data.groups ?? []).map((group) => group.key));
    if (!selected || !keys.has(selected)) {
      setSelected(analysis.data.primary_group ?? analysis.data.groups?.[0]?.key ?? null);
    }
  }, [analysis.data, selected]);

  if (analysis.isLoading) {
    return (
      <Card className="panel">
        <SectionHeading
          title={t("progress.paceHr.title")}
          subtitle={t("progress.paceHr.subtitle")}
          icon={HeartPulse}
        />
        <Skeleton className="skeleton--chart" />
      </Card>
    );
  }

  if (analysis.isError || !analysis.data) {
    return (
      <Card className="panel">
        <SectionHeading
          title={t("progress.paceHr.title")}
          subtitle={t("progress.paceHr.subtitle")}
          icon={HeartPulse}
        />
        <ErrorState
          message={
            analysis.error instanceof Error ? analysis.error.message : t("progress.paceHr.error")
          }
          onRetry={() => void analysis.refetch()}
        />
      </Card>
    );
  }

  const data = analysis.data;
  const groups = data.groups ?? [];
  const group =
    groups.find((item) => item.key === selected) ??
    groups.find((item) => item.key === data.primary_group) ??
    groups[0];
  const warnings = data.warnings ?? [];
  const params = data.conclusion_params ?? {};
  const delta = params.delta_s;
  const deltaLabel =
    typeof delta === "number" && Math.abs(delta) >= 0.5
      ? formatPace(Math.abs(delta), units)
      : `${formatClock(0)} /km`;
  const conclusion = t(CONCLUSION_KEYS[data.conclusion] ?? "progress.paceHr.conclusion.insufficient", {
    delta: deltaLabel,
    sessions: typeof params.sessions === "number" ? params.sessions : data.sessions,
    hr: typeof params.reference_hr === "number" ? formatNumber(params.reference_hr, locale) : "—",
    weeks: Math.round(data.window_days / 7),
  });

  return (
    <Card className="panel pace-hr-panel">
      <SectionHeading
        title={t("progress.paceHr.title")}
        subtitle={t("progress.paceHr.subtitle")}
        icon={HeartPulse}
        action={
          group ? (
            <Badge tone={group.status === "improving" ? "success" : group.status === "worsening" ? "danger" : "neutral"}>
              {t(`progress.paceHr.status.${group.status}` as MessageKey)}
            </Badge>
          ) : null
        }
      />

      {warnings.length ? (
        <div className="pace-hr-warnings">
          {warnings.map((warning) => (
            <Badge key={warning} tone="warning" dot>
              {WARNING_KEYS[warning] ? t(WARNING_KEYS[warning]) : warning}
            </Badge>
          ))}
        </div>
      ) : null}

      {!group || data.status === "insufficient" ? (
        <EmptyState
          icon={HeartPulse}
          title={t("progress.paceHr.empty.title")}
          description={t("progress.paceHr.empty.body")}
        />
      ) : (
        <>
          <p className="pace-hr-conclusion">{conclusion}</p>

          <div className="pace-hr-stats">
            <PaceHrStat
              label={t("progress.paceHr.sessions")}
              value={formatNumber(group.sessions, locale)}
            />
            <PaceHrStat
              label={t("progress.paceHr.referenceHr")}
              value={`${formatNumber(group.reference_hr, locale)} bpm`}
            />
            <PaceHrStat
              label={t("progress.paceHr.early")}
              value={formatPace(group.early_pace_s_per_km, units)}
            />
            <PaceHrStat
              label={t("progress.paceHr.recent")}
              value={formatPace(group.recent_pace_s_per_km, units)}
            />
            <PaceHrStat
              label={t("progress.paceHr.change")}
              value={
                group.change_s_per_km == null
                  ? "—"
                  : `${group.change_s_per_km < 0 ? "−" : "+"}${formatClock(
                      Math.abs(group.change_s_per_km),
                    )} /km`
              }
              tone={
                group.change_s_per_km == null
                  ? undefined
                  : group.change_s_per_km < 0
                    ? "is-ahead"
                    : "is-behind"
              }
            />
            <PaceHrStat
              label={t("progress.paceHr.confidence")}
              value={t(`analysis.confidence.${group.confidence}` as MessageKey)}
            />
          </div>

          <div className="pace-hr-environment">
            <div className="pace-hr-environment-head">
              <span className="pace-hr-environment-title">
                {t("progress.paceHr.environment.title")}
              </span>
              <Badge
                tone={
                  group.temperature_adjusted || group.terrain_adjusted ? "warning" : "neutral"
                }
                dot
              >
                {group.temperature_adjusted
                  ? t("progress.paceHr.environment.applied")
                  : group.terrain_adjusted
                    ? t("progress.paceHr.environment.estimated")
                    : t("progress.paceHr.environment.none")}
              </Badge>
            </div>
            <div className="pace-hr-environment-stats">
              <PaceHrStat
                label={t("progress.paceHr.environment.terrainPerKm")}
                value={
                  group.avg_elevation_per_km_m == null
                    ? "—"
                    : `${formatNumber(group.avg_elevation_per_km_m, locale, 1)} m/km`
                }
              />
              <PaceHrStat
                label={t("progress.paceHr.environment.temperature")}
                value={
                  group.temperature_c == null
                    ? t("progress.paceHr.environment.noTemperature")
                    : `${formatNumber(group.temperature_c, locale, 1)} °C`
                }
              />
              <PaceHrStat
                label={t("progress.paceHr.environment.temperatureSessions")}
                value={t("progress.paceHr.environment.sessionsValue", {
                  withTemperature: group.temperature_sessions,
                  sessions: group.sessions,
                })}
              />
              <PaceHrStat
                label={t("progress.paceHr.environment.terrainAdjustment")}
                value={
                  group.avg_terrain_adjustment_s_per_km == null
                    ? "—"
                    : `${formatNumber(group.avg_terrain_adjustment_s_per_km, locale, 1)} s/km`
                }
              />
              <PaceHrStat
                label={t("progress.paceHr.environment.heatAdjustment")}
                value={
                  group.temperature_sessions === 0
                    ? "—"
                    : `${formatNumber(group.avg_heat_adjustment_s_per_km ?? 0, locale, 1)} s/km`
                }
              />
            </div>
            <p className="pace-hr-environment-note">
              {t("progress.paceHr.environment.explanation")}
            </p>
          </div>

          <PaceHrChart group={group} />

          <div className="pace-hr-reasons">
            {(group.reasons ?? []).map((reason) => (
              <span className="reason-chip" key={reason}>
                {REASON_KEYS[reason] ? t(REASON_KEYS[reason]) : reason}
              </span>
            ))}
          </div>

          <div className="pace-hr-groups" role="group" aria-label={t("progress.paceHr.groups")}>
            {groups.map((item) => (
              <button
                key={item.key}
                type="button"
                className={cn(item.key === group.key && "is-active")}
                aria-pressed={item.key === group.key}
                onClick={() => setSelected(item.key)}
              >
                <strong>{t(DISTANCE_KEYS[item.distance_band] ?? "progress.paceHr.distance.medium")}</strong>
                <span>{t(TERRAIN_KEYS[item.terrain_band] ?? "progress.paceHr.terrain.unknown")}</span>
                <small>
                  {t("progress.paceHr.sessions")} {item.sessions}
                </small>
              </button>
            ))}
          </div>

          <div className="pace-hr-legend">
            <span>
              <i className="pace-hr-dot pace-hr-dot--early" /> {t("progress.paceHr.early")}
            </span>
            <span>
              <i className="pace-hr-dot pace-hr-dot--recent" /> {t("progress.paceHr.recent")}
            </span>
            <span>{t("progress.paceHr.chartNote")}</span>
            <span>{t("progress.paceHr.environment.chartHint")}</span>
          </div>

          <div className="pace-hr-exclusions">
            {t("progress.paceHr.excluded", {
              races: data.excluded_races,
              hard: data.excluded_hard,
              missingHr: data.excluded_missing_hr,
            })}
          </div>

          <ul className="pace-hr-notes">
            {(data.notes ?? [])
              .filter((note) => NOTE_KEYS[note])
              .map((note) => (
                <li key={note}>{t(NOTE_KEYS[note])}</li>
              ))}
          </ul>
        </>
      )}

      <p className="pace-hr-footnote">
        <Info size={13} aria-hidden="true" />
        {t("progress.paceHr.footnote")}
      </p>
    </Card>
  );
}

function PaceHrStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="pace-hr-stat">
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
    </div>
  );
}
