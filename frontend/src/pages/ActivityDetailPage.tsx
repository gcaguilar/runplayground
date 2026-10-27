import { useEffect, useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import {
  Activity as ActivityIcon,
  ArrowLeft,
  ArrowLeftRight,
  Check,
  Clock3,
  Flame,
  Flag,
  Gauge,
  HeartPulse,
  Map as MapIcon,
  Pencil,
  Route as RouteIcon,
  X,
} from "lucide-react";

import { ApiError } from "@/api/client";
import type { Lap, SourceOut } from "@/api/client";
import { useActivity, usePatchActivity, useStreams } from "@/api/queries";
import { ActivityStreamChart } from "@/components/Charts";
import { RouteMap } from "@/components/RouteMap";
import { SportGlyph } from "@/components/SportGlyph";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  InlineLink,
  SectionHeading,
  Skeleton,
} from "@/components/ui";
import { useI18n, type Locale, type MessageKey, type Units } from "@/i18n";
import { cn } from "@/lib/cn";
import {
  formatBytes,
  formatDate,
  formatDateTime,
  formatDistance,
  formatDuration,
  formatElevation,
  formatNumber,
  formatPace,
  formatTimeOfDay,
  sportKey,
  titleCase,
} from "@/lib/format";

const KNOWN_FLAGS = new Set<MessageKey>([
  "flag.no_gps",
  "flag.no_hr",
  "flag.no_streams",
  "flag.no_laps",
  "flag.zero_distance",
  "flag.zero_duration",
  "flag.sport_inferred",
]);

export function ActivityDetailPage() {
  const { t, locale, units } = useI18n();
  const params = useParams({ strict: false }) as { activityId?: string };
  const activityId = params.activityId;
  const activity = useActivity(activityId);
  const streams = useStreams(activityId);
  const patch = usePatchActivity();
  const [editing, setEditing] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [savedFlash, setSavedFlash] = useState(false);

  useEffect(() => {
    if (!savedFlash) return;
    const timer = window.setTimeout(() => setSavedFlash(false), 2200);
    return () => window.clearTimeout(timer);
  }, [savedFlash]);

  if (activity.isLoading) {
    return <DetailSkeleton />;
  }

  if (activity.isError) {
    const notFound = activity.error instanceof ApiError && activity.error.status === 404;
    return (
      <div className="page-stack">
        <Link to="/activities" className="back-link">
          <ArrowLeft size={15} aria-hidden="true" />
          {t("detail.back")}
        </Link>
        <Card className="panel">
          {notFound ? (
            <EmptyState
              icon={ActivityIcon}
              title={t("detail.notFound.title")}
              description={t("detail.notFound.desc")}
              action={
                <Link to="/activities" className="button button--secondary button--md">
                  {t("detail.back")}
                </Link>
              }
            />
          ) : (
            <ErrorState
              message={activity.error instanceof Error ? activity.error.message : t("detail.error")}
              onRetry={() => void activity.refetch()}
            />
          )}
        </Card>
      </div>
    );
  }

  const data = activity.data;
  if (!data) return null;

  const name = data.name?.trim() || t(sportKey(data.sub_sport || data.sport));
  const points = streams.data?.points ?? [];
  const flags = data.quality_flag_list ?? [];
  const sources = data.sources ?? [];
  const laps = data.laps ?? [];

  const startEditing = () => {
    setNameDraft(data.name ?? "");
    setEditing(true);
  };

  const saveName = () => {
    const next = nameDraft.trim();
    if (!next) return;
    patch.mutate(
      { id: data.id, patch: { name: next } },
      {
        onSuccess: () => {
          setEditing(false);
          setSavedFlash(true);
        },
      },
    );
  };

  return (
    <div className="page-stack">
      <div className="detail-topline">
        <Link to="/activities" className="back-link">
          <ArrowLeft size={15} aria-hidden="true" />
          {t("detail.back")}
        </Link>
        {savedFlash ? (
          <span className="saved-flash">
            <Check size={13} aria-hidden="true" />
            {t("common.save")}
          </span>
        ) : null}
      </div>

      <header className="detail-hero">
        <div className="detail-hero__identity">
          <SportGlyph sport={data.sub_sport || data.sport} size="lg" />
          <div className="detail-hero__copy">
            <div className="eyebrow">
              {formatDateTime(data.start_time_utc, locale, {
                weekday: "long",
                day: "numeric",
                month: "long",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              })}
              <span className="eyebrow-sep" aria-hidden="true" />
              {t(sportKey(data.sub_sport || data.sport))}
            </div>

            {editing ? (
              <form
                className="detail-name-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  saveName();
                }}
              >
                <input
                  value={nameDraft}
                  onChange={(event) => setNameDraft(event.target.value)}
                  placeholder={t("detail.namePlaceholder")}
                  maxLength={255}
                  autoFocus
                  aria-label={t("detail.namePlaceholder")}
                />
                <Button type="submit" size="sm" variant="primary" loading={patch.isPending} disabled={!nameDraft.trim()}>
                  <Check size={14} aria-hidden="true" />
                  {t("detail.saveName")}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setEditing(false)}
                  aria-label={t("common.cancel")}
                >
                  <X size={14} aria-hidden="true" />
                </Button>
              </form>
            ) : (
              <h1>{name}</h1>
            )}

            <div className="detail-badges">
              {data.is_race ? (
                <Badge tone="accent" dot>
                  <Flag size={12} aria-hidden="true" />
                  {t("detail.race")}
                </Badge>
              ) : null}
              {(data.source_names ?? []).map((source) => (
                <Badge key={source} tone={source === "garmin_api" ? "info" : "neutral"}>
                  {source === "garmin_api" ? t("activities.source.garmin_api") : t("activities.source.upload")}
                </Badge>
              ))}
              {flags.map((flag) => (
                <Badge key={flag} tone="warning">
                  {flagLabel(flag, t)}
                </Badge>
              ))}
            </div>
          </div>
        </div>

        <div className="detail-hero__actions">
          <Link
            to="/compare"
            search={{ left: data.id }}
            className="button button--secondary button--sm"
          >
            <ArrowLeftRight size={14} aria-hidden="true" />
            {t("nav.compare")}
          </Link>
          {!editing ? (
            <Button variant="secondary" size="sm" onClick={startEditing}>
              <Pencil size={14} aria-hidden="true" />
              {t("detail.editName")}
            </Button>
          ) : null}
          <Button
            variant={data.is_race ? "secondary" : "primary"}
            size="sm"
            loading={patch.isPending}
            onClick={() =>
              patch.mutate({ id: data.id, patch: { is_race: !data.is_race } })
            }
          >
            <Flag size={14} aria-hidden="true" />
            {data.is_race ? t("detail.unmarkRace") : t("detail.markRace")}
          </Button>
        </div>
      </header>

      {patch.isError ? (
        <p className="form-error" role="alert">
          {patch.error instanceof Error ? patch.error.message : t("common.error")}
        </p>
      ) : null}

      <section className="detail-stats">
        <DetailStat icon={RouteIcon} label={t("detail.distance")} value={formatDistance(data.distance_m, units, locale, { digits: 2 })} />
        <DetailStat icon={Clock3} label={t("detail.duration")} value={formatDuration(data.duration_s, locale)} />
        <DetailStat
          icon={Gauge}
          label={t("detail.pace")}
          value={formatPace(data.avg_pace_s_per_km, units)}
          accent
        />
        <DetailStat
          icon={HeartPulse}
          label={t("detail.avgHr")}
          value={data.avg_hr ? `${formatNumber(data.avg_hr, locale)} bpm` : "—"}
        />
        <DetailStat
          icon={HeartPulse}
          label={t("detail.maxHr")}
          value={data.max_hr ? `${formatNumber(data.max_hr, locale)} bpm` : "—"}
        />
        <DetailStat
          icon={ActivityIcon}
          label={t("detail.cadence")}
          value={data.avg_cadence_spm ? `${formatNumber(data.avg_cadence_spm, locale)} spm` : "—"}
        />
        <DetailStat
          icon={RouteIcon}
          label={t("detail.elevation")}
          value={formatElevation(data.elevation_gain_m, units, locale)}
        />
        <DetailStat
          icon={Flame}
          label={t("detail.calories")}
          value={data.calories ? `${formatNumber(data.calories, locale)} kcal` : "—"}
        />
      </section>

      <Card className="panel">
        <SectionHeading
          title={t("detail.chart.title")}
          subtitle={t("detail.chart.subtitle")}
          icon={ActivityIcon}
          action={
            <div className="chart-legend-inline">
              <span className="legend-swatch legend-swatch--pace" />
              {t("detail.chart.pace")}
              <span className="legend-swatch legend-swatch--hr" />
              {t("detail.chart.hr")}
            </div>
          }
        />
        {streams.isLoading ? (
          <Skeleton className="skeleton--chart" />
        ) : streams.isError ? (
          <ErrorState
            message={streams.error instanceof Error ? streams.error.message : t("common.error")}
            onRetry={() => void streams.refetch()}
          />
        ) : points.length ? (
          <>
            <ActivityStreamChart points={points} />
            <p className="chart-footnote">
              {t("detail.chart.points", { count: streams.data?.total_points ?? points.length })}
              {streams.data?.downsampled ? ` · ${t("detail.chart.subtitle")}` : ""}
            </p>
          </>
        ) : (
          <EmptyState compact icon={HeartPulse} title={t("detail.chart.noStreams")} />
        )}
      </Card>

      <div className="detail-grid">
        <Card className="panel detail-route">
          <SectionHeading title={t("detail.route.title")} icon={MapIcon} />
          {streams.isLoading ? (
            <Skeleton className="skeleton--chart" />
          ) : (
            <RouteMap points={points} />
          )}
        </Card>

        <Card className="panel detail-provenance">
          <SectionHeading title={t("detail.provenance.title")} subtitle={t("detail.provenance.localNote")} />
          {sources.length ? (
            <div className="provenance-list">
              {sources.map((source) => (
                <ProvenanceBlock key={`${source.source}-${source.external_id}`} source={source} locale={locale} />
              ))}
            </div>
          ) : (
            <EmptyState compact title={t("detail.provenance.noWarnings")} />
          )}
          <div className="provenance-flags">
            <span>{t("detail.provenance.quality")}</span>
            {flags.length ? (
              <div className="badge-row">
                {flags.map((flag) => (
                  <Badge key={flag} tone="warning">
                    {flagLabel(flag, t)}
                  </Badge>
                ))}
              </div>
            ) : (
              <strong>{t("detail.provenance.noWarnings")}</strong>
            )}
          </div>
        </Card>
      </div>

      <Card className="panel">
        <SectionHeading
          title={t("detail.laps.title")}
          subtitle={t("detail.laps.count", { count: laps.length })}
          icon={RouteIcon}
        />
        {laps.length ? (
          <LapTable laps={laps} locale={locale} units={units} />
        ) : (
          <EmptyState compact icon={RouteIcon} title={t("detail.laps.empty")} />
        )}
      </Card>

      <div className="detail-footer-note">
        <InlineLink>{t("detail.provenance.localNote")}</InlineLink>
      </div>
    </div>
  );
}

function DetailStat({
  icon: Icon,
  label,
  value,
  accent = false,
}: {
  icon: typeof RouteIcon;
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <Card className={cn("detail-stat", accent && "detail-stat--accent")}>
      <span className="detail-stat__icon">
        <Icon size={16} aria-hidden="true" />
      </span>
      <span className="detail-stat__label">{label}</span>
      <strong className="detail-stat__value">{value}</strong>
    </Card>
  );
}

function ProvenanceBlock({ source, locale }: { source: SourceOut; locale: Locale }) {
  const { t } = useI18n();
  const rows: Array<{ label: string; value: string }> = [
    {
      label: t("detail.provenance.source"),
      value: source.source === "garmin_api" ? t("activities.source.garmin_api") : t("activities.source.upload"),
    },
    { label: t("detail.provenance.imported"), value: formatDate(source.imported_at, locale) },
    { label: t("detail.provenance.externalId"), value: source.external_id },
  ];
  if (source.original_filename) {
    rows.push({ label: t("detail.provenance.file"), value: source.original_filename });
  }
  if (source.parser_version) {
    rows.push({ label: t("detail.provenance.parser"), value: source.parser_version });
  }
  if (source.raw_size_bytes) {
    rows.push({ label: t("detail.provenance.size"), value: formatBytes(source.raw_size_bytes) });
  }
  if (source.raw_sha256) {
    rows.push({ label: t("detail.provenance.hash"), value: `${source.raw_sha256.slice(0, 16)}…` });
  }

  return (
    <div className="provenance-block">
      {rows.map((row) => (
        <div className="definition-row" key={row.label}>
          <span>{row.label}</span>
          <strong title={row.value}>{row.value}</strong>
        </div>
      ))}
    </div>
  );
}

function LapTable({ laps, locale, units }: { laps: Lap[]; locale: Locale; units: Units }) {
  const { t } = useI18n();
  return (
    <div className="lap-table" role="table" aria-label={t("detail.laps.title")}>
      <div className="lap-table__row lap-table__row--head" role="row">
        <span role="columnheader">{t("detail.laps.lap")}</span>
        <span role="columnheader">{t("detail.laps.distance")}</span>
        <span role="columnheader">{t("detail.laps.time")}</span>
        <span role="columnheader">{t("detail.laps.pace")}</span>
        <span role="columnheader">{t("detail.laps.hr")}</span>
        <span role="columnheader">{t("detail.laps.elevation")}</span>
      </div>
      {laps.map((lap) => {
        const pace =
          lap.avg_speed_mps && lap.avg_speed_mps > 0
            ? 1000 / lap.avg_speed_mps
            : lap.distance_m && lap.timer_s
              ? (lap.timer_s / lap.distance_m) * 1000
              : null;
        const start = lap.start_time_utc
          ? formatTimeOfDay(lap.start_time_utc, locale)
          : null;
        return (
          <div className="lap-table__row" role="row" key={lap.lap_index}>
            <span role="cell" className="lap-table__index">
              <strong>{lap.lap_index + 1}</strong>
              {start ? <small>{start}</small> : null}
            </span>
            <span role="cell" className="num">
              {formatDistance(lap.distance_m, units, locale)}
            </span>
            <span role="cell" className="num">
              {formatDuration(lap.timer_s ?? lap.elapsed_s, locale, true)}
            </span>
            <span role="cell" className="num num--accent">
              {formatPace(pace, units)}
            </span>
            <span role="cell" className="num">
              {lap.avg_hr ? `${formatNumber(lap.avg_hr, locale)} bpm` : "—"}
            </span>
            <span role="cell" className="num">
              {lap.ascent_m ? formatElevation(lap.ascent_m, units, locale) : "—"}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function flagLabel(flag: string, t: (key: MessageKey) => string): string {
  const key = `flag.${flag}` as MessageKey;
  return KNOWN_FLAGS.has(key) ? t(key) : titleCase(flag);
}

function DetailSkeleton() {
  return (
    <div className="page-stack">
      <Skeleton className="skeleton--line skeleton--short" />
      <Card className="panel">
        <div className="detail-skeleton-head">
          <Skeleton className="skeleton--avatar" />
          <div>
            <Skeleton className="skeleton--line skeleton--short" />
            <Skeleton className="skeleton--title" />
          </div>
        </div>
      </Card>
      <section className="detail-stats">
        {Array.from({ length: 8 }).map((_, index) => (
          <Card className="detail-stat" key={index}>
            <Skeleton className="skeleton--line skeleton--short" />
            <Skeleton className="skeleton--line" />
          </Card>
        ))}
      </section>
      <Card className="panel">
        <Skeleton className="skeleton--chart" />
      </Card>
    </div>
  );
}
