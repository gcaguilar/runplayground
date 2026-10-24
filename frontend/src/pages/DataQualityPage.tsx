import { Link } from "@tanstack/react-router";
import {
  Activity,
  ArrowRight,
  CalendarRange,
  CheckCircle2,
  CircleAlert,
  Database,
  Flag,
  Gauge,
  HeartPulse,
  Info,
  MapPin,
  Route,
  Settings,
  ShieldAlert,
  TriangleAlert,
  Zap,
} from "lucide-react";

import type { AuditFinding, AuditReport, RaceCandidate } from "@/api/client";
import { useAudit, usePatchActivity } from "@/api/queries";
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
import { cn } from "@/lib/cn";
import {
  formatDate,
  formatDateTime,
  formatDistance,
  formatDuration,
  formatPercent,
  scoreBand,
  sportKey,
} from "@/lib/format";

const KNOWN_FINDINGS = new Set<string>([
  "no_garmin_key",
  "no_activities",
  "missing_streams",
  "missing_hr",
  "missing_gps",
  "no_races",
  "implausible_speed",
  "implausible_hr",
  "future_activity",
  "duplicate_candidates",
  "never_synced",
  "stale_sync",
  "last_sync_failed",
  "race_candidates",
]);

export function DataQualityPage() {
  const { locale, t } = useI18n();
  const audit = useAudit();
  const patch = usePatchActivity();

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={t("nav.library")}
        title={t("data.title")}
        description={t("data.subtitle")}
        actions={
          <Link to="/settings" className="button button--secondary button--md">
            <Settings size={15} aria-hidden="true" />
            {t("data.openSettings")}
          </Link>
        }
      />

      {audit.isError ? (
        <ErrorState
          message={audit.error instanceof Error ? audit.error.message : t("common.error")}
          onRetry={() => void audit.refetch()}
        />
      ) : audit.isLoading || !audit.data ? (
        <QualitySkeleton />
      ) : (
        <QualityReport
          report={audit.data}
          locale={locale}
          onConfirmRace={(candidate) =>
            patch.mutate({ id: candidate.id, patch: { is_race: true } })
          }
          confirming={patch.isPending}
        />
      )}
    </div>
  );
}

function QualityReport({
  report,
  locale,
  onConfirmRace,
  confirming,
}: {
  report: AuditReport;
  locale: Locale;
  onConfirmRace: (candidate: RaceCandidate) => void;
  confirming: boolean;
}) {
  const { t } = useI18n();
  const { coverage } = report;
  const band = scoreBand(report.score);
  const bandMessages: Record<ReturnType<typeof scoreBand>, MessageKey> = {
    excellent: "data.score.excellent",
    good: "data.score.good",
    fair: "data.score.fair",
    poor: "data.score.poor",
  };

  const coverageRows = [
    {
      key: "streams",
      label: t("data.coverage.streams"),
      icon: Activity,
      percent: coverage.pct_streams,
      count: coverage.with_streams,
    },
    {
      key: "hr",
      label: t("data.coverage.hr"),
      icon: HeartPulse,
      percent: coverage.pct_hr,
      count: coverage.with_hr,
    },
    {
      key: "gps",
      label: t("data.coverage.gps"),
      icon: MapPin,
      percent: coverage.pct_gps,
      count: coverage.with_gps,
    },
    {
      key: "laps",
      label: t("data.coverage.laps"),
      icon: Route,
      percent: coverage.total_activities ? (coverage.with_laps / coverage.total_activities) * 100 : 0,
      count: coverage.with_laps,
    },
    {
      key: "power",
      label: t("data.coverage.power"),
      icon: Zap,
      percent: coverage.total_activities ? (coverage.with_power / coverage.total_activities) * 100 : 0,
      count: coverage.with_power,
    },
  ];

  const maxYear = Math.max(...(coverage.by_year ?? []).map((row) => Number(row.activities) || 0), 1);
  const lastSync = report.last_sync;

  return (
    <>
      <div className="quality-overview">
        <Card className="panel quality-score-panel">
          <SectionHeading title={t("data.score.title")} icon={ShieldAlert} />
          <div className="quality-score-panel__body">
            <ScoreRing
              score={report.score}
              label={`/ ${t("data.score.outOf")}`}
              caption={t(bandMessages[band])}
            />
            <div className="quality-score-panel__copy">
              <p>{t(bandMessages[band])}</p>
              <div className="quality-facts">
                <span>
                  <strong>
                    {formatDate(coverage.first_activity, locale)} —{" "}
                    {formatDate(coverage.last_activity, locale)}
                  </strong>
                  {t("data.coverage.period")}
                </span>
              </div>
              {lastSync?.last_finished_at ? (
                <p className="quality-last-sync">
                  {t("data.lastSync")}:{" "}
                  {formatDateTime(String(lastSync.last_finished_at), locale)}
                </p>
              ) : null}
            </div>
          </div>
        </Card>

        <Card className="panel coverage-panel">
          <SectionHeading
            title={t("data.coverage.title")}
            subtitle={t("data.coverage.activities", { count: coverage.total_activities })}
            icon={Database}
          />
          <div className="coverage-grid">
            {coverageRows.map((row) => {
              const Icon = row.icon;
              return (
                <div className="coverage-tile" key={row.key}>
                  <div className="coverage-tile__head">
                    <span>
                      <Icon size={15} aria-hidden="true" />
                      {row.label}
                    </span>
                    <strong>{formatPercent(row.percent, locale)}</strong>
                  </div>
                  <ProgressBar
                    value={row.percent}
                    tone={row.percent >= 80 ? "accent" : row.percent >= 50 ? "warning" : "danger"}
                    label={row.label}
                  />
                  <span className="coverage-tile__count">
                    {row.count} / {coverage.total_activities}
                  </span>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      <div className="quality-layout">
        <Card className="panel">
          <SectionHeading
            title={t("data.findings.title")}
            subtitle={`${report.findings.length} ${t("data.findings.title").toLowerCase()}`}
            icon={CircleAlert}
          />
          {report.findings.length ? (
            <div className="findings-list">
              {report.findings.map((finding) => (
                <FindingRow key={finding.code} finding={finding} />
              ))}
            </div>
          ) : (
            <EmptyState compact icon={CheckCircle2} title={t("data.findings.empty")} />
          )}
        </Card>

        <div className="quality-rail">
          <Card className="panel">
            <SectionHeading title={t("data.byYear.title")} icon={CalendarRange} />
            {coverage.by_year?.length ? (
              <div className="year-bars">
                {coverage.by_year.map((row) => {
                  const year = Number(row.year);
                  const count = Number(row.activities) || 0;
                  return (
                    <div className="year-bar" key={year}>
                      <span className="year-bar__label mono">{year}</span>
                      <span className="year-bar__track">
                        <span style={{ width: `${Math.max(4, (count / maxYear) * 100)}%` }} />
                      </span>
                      <strong>{count}</strong>
                    </div>
                  );
                })}
              </div>
            ) : (
              <EmptyState compact title={t("data.byYear.empty")} />
            )}
          </Card>

          <Card className="panel">
            <SectionHeading title={t("data.sources.title")} icon={Database} />
            {coverage.by_source?.length ? (
              <div className="source-breakdown">
                {coverage.by_source.map((row) => (
                  <div className="source-breakdown__row" key={String(row.source)}>
                    <Badge tone={row.source === "garmin_api" ? "info" : "neutral"}>
                      {row.source === "garmin_api"
                        ? t("activities.source.garmin_api")
                        : t("activities.source.upload")}
                    </Badge>
                    <strong>{Number(row.activities)}</strong>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState compact title={t("data.sources.empty")} />
            )}
          </Card>
        </div>
      </div>

      <Card className="panel">
        <SectionHeading title={t("data.races.title")} subtitle={t("data.races.subtitle")} icon={Flag} />
        {report.race_candidates.length ? (
          <div className="race-list">
            {report.race_candidates.map((candidate) => (
              <div className="race-row" key={candidate.id}>
                <span className="race-row__flag">
                  <Flag size={16} aria-hidden="true" />
                </span>
                <div className="race-row__copy">
                  <Link
                    to="/activities/$activityId"
                    params={{ activityId: String(candidate.id) }}
                  >
                    {candidate.name || t(sportKey(candidate.sport))}
                  </Link>
                  <span>
                    {formatDate(candidate.start_time_utc, locale)}
                    <span className="dot-sep" aria-hidden="true" />
                    {formatDistance(candidate.distance_m, "metric", locale)}
                    <span className="dot-sep" aria-hidden="true" />
                    {formatDuration(candidate.duration_s, locale, true)}
                  </span>
                </div>
                <Button
                  size="sm"
                  variant="primary"
                  loading={confirming}
                  onClick={() => onConfirmRace(candidate)}
                >
                  {t("data.races.confirm")}
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState compact icon={Flag} title={t("data.races.empty")} />
        )}
      </Card>

      <Card className="panel">
        <SectionHeading title={t("data.missing.title")} icon={Gauge} />
        {report.recent_missing.length ? (
          <div className="missing-list">
            {report.recent_missing.map((activity) => (
              <div className="missing-row" key={activity.id}>
                <div className="missing-row__copy">
                  <Link
                    to="/activities/$activityId"
                    params={{ activityId: String(activity.id) }}
                  >
                    {activity.name || t(sportKey(activity.sport))}
                  </Link>
                  <span>{formatDate(activity.start_time_utc, locale)}</span>
                </div>
                <div className="badge-row">
                  {activity.missing.map((item) => (
                    <Badge key={item} tone="warning">
                      {item === "streams"
                        ? t("data.missing.streams")
                        : item === "heart_rate"
                          ? t("data.missing.heart_rate")
                          : t("data.missing.gps")}
                    </Badge>
                  ))}
                </div>
                <Link
                  to="/activities/$activityId"
                  params={{ activityId: String(activity.id) }}
                  className="text-link"
                >
                  {t("data.missing.review")}
                  <ArrowRight size={13} aria-hidden="true" />
                </Link>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState compact icon={CheckCircle2} title={t("data.missing.empty")} />
        )}
      </Card>
    </>
  );
}

function FindingRow({ finding }: { finding: AuditFinding }) {
  const { t } = useI18n();
  const known = KNOWN_FINDINGS.has(finding.code);
  const titleKey = `data.findings.${finding.code}.title` as MessageKey;
  const descKey = `data.findings.${finding.code}.desc` as MessageKey;
  const hintKey = `data.findings.${finding.code}.hint` as MessageKey;
  const values = { count: finding.count ?? 0 };
  const Icon =
    finding.severity === "critical"
      ? CircleAlert
      : finding.severity === "warning"
        ? TriangleAlert
        : Info;

  return (
    <div className={cn("finding", `finding--${finding.severity}`)}>
      <span className="finding__icon">
        <Icon size={18} aria-hidden="true" />
      </span>
      <div className="finding__copy">
        <div className="finding__head">
          <strong>{known ? t(titleKey) : finding.message}</strong>
          <Badge
            tone={
              finding.severity === "critical"
                ? "danger"
                : finding.severity === "warning"
                  ? "warning"
                  : "info"
            }
          >
            {finding.severity === "critical"
              ? t("data.findings.critical")
              : finding.severity === "warning"
                ? t("data.findings.warning")
                : t("data.findings.info")}
          </Badge>
          {finding.count ? (
            <span className="finding__count">
              {t("data.findings.cases", { count: finding.count })}
            </span>
          ) : null}
        </div>
        <p>{known ? t(descKey, values) : finding.message}</p>
        {finding.hint || known ? (
          <div className="finding__hint">
            <span>{t("data.findings.hint")}</span>
            <p>{known ? t(hintKey, values) : finding.hint}</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function QualitySkeleton() {
  return (
    <div className="page-stack">
      <div className="quality-overview">
        <Card className="panel">
          <Skeleton className="skeleton--block" />
        </Card>
        <Card className="panel">
          <Skeleton className="skeleton--block" />
        </Card>
      </div>
      <div className="quality-layout">
        <Card className="panel">
          <Skeleton className="skeleton--block" />
        </Card>
        <Card className="panel">
          <Skeleton className="skeleton--block" />
        </Card>
      </div>
    </div>
  );
}
