import { Link } from "@tanstack/react-router";
import { AlertTriangle, ArrowRight, HeartPulse, Settings2 } from "lucide-react";

import type { ActivityDetail, HrZone } from "@/api/client";
import { useActivityZones } from "@/api/queries";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  SectionHeading,
  Skeleton,
} from "@/components/ui";
import { useI18n, type MessageKey } from "@/i18n";
import { formatDuration, formatNumber } from "@/lib/format";

const WARNING_KEYS: Partial<Record<string, MessageKey>> = {
  low_coverage: "detail.zones.warning.low_coverage",
  sparse_samples: "detail.zones.warning.sparse_samples",
  estimated_max_hr: "detail.zones.warning.estimated_max_hr",
  hr_filtered: "detail.zones.warning.hr_filtered",
  not_running: "detail.zones.warning.not_running",
  no_timed_samples: "detail.zones.warning.no_timed_samples",
  no_hr_time: "detail.zones.warning.no_hr_time",
};

const ZONE_NAMES: Record<string, MessageKey> = {
  z1: "detail.zones.zone.z1",
  z2: "detail.zones.zone.z2",
  z3: "detail.zones.zone.z3",
  z4: "detail.zones.zone.z4",
  z5: "detail.zones.zone.z5",
};

export function ActivityHrZonesCard({ activity }: { activity: ActivityDetail }) {
  const { t, locale } = useI18n();
  const zones = useActivityZones(activity.id, activity.sport === "running");

  if (activity.sport !== "running") return null;

  const data = zones.data;
  const lowCoverage = data?.warnings?.includes("low_coverage") ?? false;
  const warnings = (data?.warnings ?? []).filter((code) => WARNING_KEYS[code]);
  const showThresholdNote = data?.notes?.includes("threshold_reference") ?? false;
  const showFallbackNote =
    data?.status === "ok" && data.source === "activity_fallback" && data.max_hr_source === "stream";

  return (
    <Card className="panel hr-zones-card">
      <SectionHeading
        title={t("detail.zones.title")}
        subtitle={t("detail.zones.subtitle")}
        icon={HeartPulse}
        action={
          data?.status === "ok" ? (
            lowCoverage ? (
              <Badge tone="warning" dot>
                {t("detail.zones.badgeLowCoverage")}
              </Badge>
            ) : (
              <Badge tone="info">
                {t("detail.zones.coverage")} {formatNumber(data.coverage * 100, locale, 0)}%
              </Badge>
            )
          ) : null
        }
      />

      {zones.isLoading ? (
        <Skeleton className="skeleton--chart" />
      ) : zones.isError ? (
        <ErrorState
          message={zones.error instanceof Error ? zones.error.message : t("common.error")}
          onRetry={() => void zones.refetch()}
        />
      ) : !data ? null : data.status === "insufficient" ? (
        <EmptyState
          compact
          icon={HeartPulse}
          title={t("detail.zones.emptyTitle")}
          description={t(emptyDescription(data.warnings ?? []))}
        />
      ) : (
        <>
          <div className="hr-zones-card__summary">
            <div>
              <span className="hr-zones-card__label">{t("detail.zones.reference")}</span>
              <strong>{data.reference_bpm ? `${data.reference_bpm} bpm` : "—"}</strong>
            </div>
            <div>
              <span className="hr-zones-card__label">{t("detail.zones.method")}</span>
              <strong>
                {data.method ? t(`detail.zones.method.${data.method}` as MessageKey) : "—"}
              </strong>
            </div>
            <div>
              <span className="hr-zones-card__label">{t("detail.zones.source")}</span>
              <strong>
                {data.source ? t(`detail.zones.source.${data.source}` as MessageKey) : "—"}
              </strong>
            </div>
            <div>
              <span className="hr-zones-card__label">{t("detail.zones.totalHr")}</span>
              <strong>{formatDuration(data.total_hr_s, locale, true)}</strong>
            </div>
            <div>
              <span className="hr-zones-card__label">{t("detail.zones.coverage")}</span>
              <strong>
                {t("detail.zones.coverageValue", {
                  pct: formatNumber(data.coverage * 100, locale, 0),
                  withHr: data.samples_with_hr,
                  timed: data.samples_timed,
                })}
              </strong>
            </div>
          </div>

          <div
            className="hr-zones"
            role="list"
            aria-label={t("detail.zones.title")}
          >
            {data.zones?.map((zone) => (
              <HrZoneRow key={zone.key} zone={zone} />
            ))}
          </div>

          {warnings.length ? (
            <ul className="hr-zones-card__warnings">
              {warnings.map((code) => (
                <li key={code}>
                  <AlertTriangle size={13} aria-hidden="true" />
                  {t(WARNING_KEYS[code] as MessageKey)}
                </li>
              ))}
            </ul>
          ) : null}

          {showThresholdNote ? (
            <p className="hr-zones-card__note">{t("detail.zones.note.threshold")}</p>
          ) : null}
          {showFallbackNote ? (
            <p className="hr-zones-card__note">{t("detail.zones.note.activityFallback")}</p>
          ) : null}
          <p className="hr-zones-card__note">{t("detail.zones.note.delta")}</p>
        </>
      )}

      <footer className="hr-zones-card__footer">
        <span>{t("detail.zones.note.settings")}</span>
        <Link to="/settings" className="inline-link">
          <Settings2 size={13} aria-hidden="true" />
          {t("detail.zones.settingsLink")}
          <ArrowRight size={13} aria-hidden="true" />
        </Link>
      </footer>
    </Card>
  );
}

function HrZoneRow({ zone }: { zone: HrZone }) {
  const { t, locale } = useI18n();
  const name = ZONE_NAMES[zone.key];
  const bpm =
    zone.lower_pct === null
      ? t("detail.zones.bpmBelow", { high: zone.upper_bpm })
      : zone.upper_pct === null
        ? t("detail.zones.bpmAbove", { low: zone.lower_bpm })
        : t("detail.zones.bpmRange", { low: zone.lower_bpm, high: zone.upper_bpm });
  const pct =
    zone.lower_pct === null
      ? t("detail.zones.pctBelow", { high: zone.upper_pct ?? 0 })
      : zone.upper_pct === null
        ? t("detail.zones.pctAbove", { low: zone.lower_pct ?? 0 })
        : t("detail.zones.pctRange", { low: zone.lower_pct ?? 0, high: zone.upper_pct ?? 0 });

  return (
    <div className="hr-zone" role="listitem">
      <div className="hr-zone__head">
        <span className={`hr-zone__key hr-zone__key--${zone.key}`}>
          {zone.key.toUpperCase()}
        </span>
        <span className="hr-zone__name">{name ? t(name) : zone.key}</span>
        <span className="hr-zone__bpm">
          {bpm}
          <small>{pct}</small>
        </span>
        <span className="hr-zone__time">
          <strong>{formatDuration(zone.seconds, locale, true)}</strong>
          <small>{formatNumber(zone.percentage, locale, 1)}%</small>
        </span>
      </div>
      <div className="hr-zone__track" aria-hidden="true">
        <span
          className={`hr-zone__fill hr-zone__fill--${zone.key}`}
          style={{ width: `${Math.min(100, Math.max(0, zone.percentage))}%` }}
        />
      </div>
    </div>
  );
}

function emptyDescription(warnings: string[]): MessageKey {
  if (warnings.includes("no_streams")) return "detail.zones.emptyNoStreams";
  if (warnings.includes("no_hr") || warnings.includes("no_timed_samples")) {
    return "detail.zones.emptyNoHr";
  }
  if (warnings.includes("no_hr_reference")) return "detail.zones.emptyNoReference";
  return "detail.zones.emptyOther";
}
