import { useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  Activity,
  ArrowRight,
  CalendarDays,
  ChevronLeft,
  ClipboardList,
  ChevronRight,
  Dumbbell,
  Flag,
  RefreshCw,
  Timer,
} from "lucide-react";

import type { CalendarDay, CalendarEntry, CalendarWeek } from "@/api/client";
import { useCalendar } from "@/api/queries";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  SectionHeading,
  Skeleton,
} from "@/components/ui";
import { useI18n, type Locale, type MessageKey, type Units } from "@/i18n";
import { cn } from "@/lib/cn";
import {
  formatDate,
  formatDistance,
  formatDuration,
  formatWeekRange,
  parseUtc,
  weekdayKeys,
} from "@/lib/format";

const SESSION_KEYS: Record<string, MessageKey> = {
  easy: "calendar.session.easy",
  recovery: "calendar.session.recovery",
  strides: "calendar.session.strides",
  long: "calendar.session.long",
  threshold: "calendar.session.threshold",
  race_pace: "calendar.session.race_pace",
  strength: "plan.session.type.strength",
  cross_training: "plan.session.type.cross_training",
  other: "plan.session.type.other",
};

const INTENSITY_TONE: Record<string, "accent" | "warning" | "danger" | "neutral"> = {
  easy: "accent",
  moderate: "warning",
  hard: "danger",
  rest: "neutral",
};

const INTENSITY_KEYS: Record<string, MessageKey> = {
  easy: "training.session.intensity.easy",
  moderate: "training.session.intensity.moderate",
  hard: "training.session.intensity.hard",
  rest: "training.session.intensity.rest",
};

function mondayOf(value: Date): string {
  const copy = new Date(value.getFullYear(), value.getMonth(), value.getDate());
  const weekday = (copy.getDay() + 6) % 7;
  copy.setDate(copy.getDate() - weekday);
  return `${copy.getFullYear()}-${String(copy.getMonth() + 1).padStart(2, "0")}-${String(
    copy.getDate(),
  ).padStart(2, "0")}`;
}

function addDays(value: string, days: number): string {
  const date = parseUtc(value);
  date.setDate(date.getDate() + days);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate(),
  ).padStart(2, "0")}`;
}

export function CalendarPage() {
  const { t, locale, units } = useI18n();
  const [anchor, setAnchor] = useState(() => mondayOf(new Date()));
  const [weeks, setWeeks] = useState(6);
  const calendar = useCalendar(anchor, weeks);

  if (calendar.isLoading) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow={t("calendar.page.eyebrow")} title={t("calendar.page.title")} />
        <div className="analysis-skeleton">
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
        </div>
      </div>
    );
  }

  if (calendar.isError || !calendar.data) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow={t("calendar.page.eyebrow")}
          title={t("calendar.page.title")}
          description={t("calendar.page.subtitle")}
        />
        <ErrorState
          message={
            calendar.error instanceof Error ? calendar.error.message : t("calendar.error")
          }
          onRetry={() => void calendar.refetch()}
        />
      </div>
    );
  }

  const data = calendar.data;
  const actual = data.weeks.reduce((total, week) => total + week.actual_distance_m, 0);
  const planned = data.weeks.reduce((total, week) => total + week.planned_distance_m, 0);
  const sessions = data.weeks.reduce(
    (total, week) =>
      total +
      week.days.reduce(
        (dayTotal, day) =>
          dayTotal +
          (day.entries ?? []).filter(
            (entry) => entry.kind === "session" || entry.kind === "plan",
          ).length,
        0,
      ),
    0,
  );

  return (
    <div className="page-stack calendar-page">
      <PageHeader
        eyebrow={t("calendar.page.eyebrow")}
        title={t("calendar.page.title")}
        description={t("calendar.page.subtitle")}
        actions={
          <div className="calendar-actions">
            <div className="calendar-nav" role="group" aria-label={t("calendar.actions.prev")}>
              <Button
                variant="secondary"
                size="icon"
                aria-label={t("calendar.actions.prev")}
                onClick={() => setAnchor(addDays(anchor, -weeks * 7))}
              >
                <ChevronLeft size={17} aria-hidden="true" />
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setAnchor(mondayOf(new Date()))}>
                {t("calendar.actions.today")}
              </Button>
              <Button
                variant="secondary"
                size="icon"
                aria-label={t("calendar.actions.next")}
                onClick={() => setAnchor(addDays(anchor, weeks * 7))}
              >
                <ChevronRight size={17} aria-hidden="true" />
              </Button>
            </div>
            <div className="segmented" role="group" aria-label={t("calendar.weeks.label")}>
              {[4, 6, 8].map((value) => (
                <button
                  key={value}
                  type="button"
                  className={cn(weeks === value && "is-active")}
                  aria-pressed={weeks === value}
                  onClick={() => setWeeks(value)}
                >
                  {t(`calendar.weeks.${value}` as MessageKey)}
                </button>
              ))}
            </div>
            <Button
              variant="secondary"
              size="sm"
              loading={calendar.isFetching}
              onClick={() => void calendar.refetch()}
            >
              <RefreshCw size={15} aria-hidden="true" />
              {t("calendar.actions.refresh")}
            </Button>
            <Link to="/progress" className="button button--secondary button--sm">
              <ArrowRight size={15} aria-hidden="true" />
              {t("calendar.actions.progress")}
            </Link>
          </div>
        }
      />

      <section className="calendar-summary">
        <Card className="calendar-summary__card">
          <span className="eyebrow">{t("calendar.range", {
            start: formatDate(data.start, locale, { day: "numeric", month: "short" }),
            end: formatDate(data.end, locale, { day: "numeric", month: "short", year: "numeric" }),
          })}</span>
          <div className="calendar-summary__metrics">
            <div>
              <span>{t("calendar.actual")}</span>
              <strong>{formatDistance(actual, units, locale, { digits: 1 })}</strong>
            </div>
            <div>
              <span>{t("calendar.planned")}</span>
              <strong>{formatDistance(planned, units, locale, { digits: 1 })}</strong>
            </div>
            <div>
              <span>{t("calendar.sessions")}</span>
              <strong>{sessions}</strong>
            </div>
          </div>
          {data.active_plan ? (
            <Link to="/plan" className="calendar-plan-chip">
              <ClipboardList size={14} aria-hidden="true" />
              <span>
                {t("calendar.plan.active", { name: data.active_plan.name })}
                <small>
                  {formatDate(data.active_plan.start_date, locale)} –{" "}
                  {formatDate(data.active_plan.end_date, locale)}
                </small>
              </span>
            </Link>
          ) : null}
        </Card>
        <Card className="calendar-summary__legend">
          <LegendItem icon={Activity} label={t("calendar.legend.activity")} tone="activity" />
          <LegendItem icon={Flag} label={t("calendar.legend.race")} tone="race" />
          <LegendItem icon={Dumbbell} label={t("calendar.legend.session")} tone="session" />
          <LegendItem icon={ClipboardList} label={t("calendar.legend.plan")} tone="plan" />
        </Card>
      </section>

      <Card className="panel calendar-board">
        <SectionHeading
          title={t("calendar.page.title")}
          subtitle={t("calendar.page.subtitle")}
          icon={CalendarDays}
          action={
            <Badge tone="info">
              {t("calendar.weeks.label")} · {weeks}
            </Badge>
          }
        />
        <div className="calendar-grid">
          <div className="calendar-grid__head">
            {weekdayKeys().map((key) => (
              <span key={key}>{t(key)}</span>
            ))}
          </div>
          {data.weeks.map((week) => (
            <CalendarWeekRow
              key={week.week_start}
              week={week}
              today={data.today}
              locale={locale}
              units={units}
            />
          ))}
        </div>
        {actual === 0 && planned === 0 ? (
          <EmptyState
            compact
            icon={CalendarDays}
            title={t("calendar.empty.title")}
            description={t("calendar.empty.body")}
            action={
              <Link to="/imports" className="button button--secondary button--sm">
                {t("analysis.actions.import")}
              </Link>
            }
          />
        ) : null}
        <p className="analysis-note">{t("calendar.note")}</p>
      </Card>
    </div>
  );
}

function CalendarWeekRow({
  week,
  today,
  locale,
  units,
}: {
  week: CalendarWeek;
  today: string;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  return (
    <div className="calendar-week">
      <div className="calendar-week__summary">
        <span>
          {formatWeekRange(week.week_start, week.days[week.days.length - 1].date, locale)}
        </span>
        <strong>
          {t("calendar.week.actual")}{" "}
          {formatDistance(week.actual_distance_m, units, locale, { digits: 1 })}
          <small>
            {t("calendar.week.planned")}{" "}
            {formatDistance(week.planned_distance_m, units, locale, { digits: 1 })}
          </small>
        </strong>
      </div>
      <div className="calendar-week__days">
        {week.days.map((day) => (
          <CalendarDayCell
            key={day.date}
            day={day}
            today={today}
            locale={locale}
            units={units}
          />
        ))}
      </div>
    </div>
  );
}

function CalendarDayCell({
  day,
  today,
  locale,
  units,
}: {
  day: CalendarDay;
  today: string;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  const date = parseUtc(day.date);
  const isToday = day.date === today;
  const weekday = (date.getDay() + 6) % 7;
  const entries = day.entries ?? [];

  return (
    <div className={cn("calendar-day", isToday && "is-today")}>
      <div className="calendar-day__head">
        <span className="calendar-day__weekday">{t(weekdayKeys()[weekday])}</span>
        <span className="calendar-day__number">{date.getDate()}</span>
        {isToday ? <span className="calendar-day__today">{t("calendar.today")}</span> : null}
      </div>
      <div className="calendar-day__entries">
        {entries.length === 0 ? <span className="calendar-day__empty">—</span> : null}
        {entries.map((entry) => (
          <CalendarEntryItem
            key={entry.id}
            entry={entry}
            locale={locale}
            units={units}
          />
        ))}
      </div>
      {day.actual_distance_m > 0 ? (
        <span className="calendar-day__total">
          {formatDistance(day.actual_distance_m, units, locale, { digits: 1 })}
        </span>
      ) : null}
    </div>
  );
}

function CalendarEntryItem({
  entry,
  locale,
  units,
}: {
  entry: CalendarEntry;
  locale: Locale;
  units: Units;
}) {
  const { t } = useI18n();
  const isSession = entry.kind === "session";
  const isPlan = entry.kind === "plan";
  const isPlanned = isSession || isPlan;
  const title = isPlanned
    ? t(SESSION_KEYS[entry.title] ?? (isPlan ? "calendar.legend.plan" : "calendar.legend.session"))
    : entry.title;
  const content = (
    <>
      <span className="calendar-entry__head">
        {entry.kind === "activity" ? (
          entry.is_race ? (
            <Flag size={12} aria-hidden="true" />
          ) : (
            <Activity size={12} aria-hidden="true" />
          )
        ) : entry.kind === "race" ? (
          <Flag size={12} aria-hidden="true" />
        ) : isPlan ? (
          <ClipboardList size={12} aria-hidden="true" />
        ) : (
          <Dumbbell size={12} aria-hidden="true" />
        )}
        <span>{title}</span>
      </span>
      <span className="calendar-entry__meta">
        {entry.distance_m ? (
          <span>{formatDistance(entry.distance_m, units, locale, { digits: 1 })}</span>
        ) : null}
        {entry.duration_s ? (
          <span>
            <Timer size={10} aria-hidden="true" />
            {formatDuration(entry.duration_s, locale, true)}
          </span>
        ) : null}
        {isPlanned && entry.intensity ? (
          <Badge tone={INTENSITY_TONE[entry.intensity] ?? "neutral"}>
            {INTENSITY_KEYS[entry.intensity] ? t(INTENSITY_KEYS[entry.intensity]) : entry.intensity}
          </Badge>
        ) : null}
        {isPlan && entry.status ? (
          <Badge tone="neutral">{t(calendarStatusKey(entry.status))}</Badge>
        ) : null}
        {entry.kind === "race" && entry.status ? (
          <Badge
            tone={
              entry.status === "completed"
                ? "success"
                : entry.status === "cancelled"
                  ? "warning"
                  : "neutral"
            }
          >
            {t(`progress.race.status.${entry.status}` as MessageKey)}
          </Badge>
        ) : null}
      </span>
    </>
  );

  const className = cn(
    "calendar-entry",
    `calendar-entry--${entry.kind}`,
    entry.is_race && "is-race",
  );

  if (entry.kind === "activity" && entry.activity_id) {
    return (
      <Link
        to="/activities/$activityId"
        params={{ activityId: String(entry.activity_id) }}
        className={className}
      >
        {content}
      </Link>
    );
  }
  if (entry.kind === "race") {
    return (
      <Link to="/progress" className={className}>
        {content}
      </Link>
    );
  }
  if (entry.kind === "plan") {
    return (
      <Link to="/plan" className={className}>
        {content}
      </Link>
    );
  }
  return <div className={className}>{content}</div>;
}

function calendarStatusKey(status: string): MessageKey {
  if (status === "completed") return "plan.session.status.completed";
  if (status === "skipped") return "plan.session.status.skipped";
  return "plan.session.status.planned";
}

function LegendItem({
  icon: Icon,
  label,
  tone,
}: {
  icon: typeof Activity;
  label: string;
  tone: "activity" | "race" | "session" | "plan";
}) {
  return (
    <span className={cn("calendar-legend-item", `calendar-legend-item--${tone}`)}>
      <Icon size={14} aria-hidden="true" />
      {label}
    </span>
  );
}
