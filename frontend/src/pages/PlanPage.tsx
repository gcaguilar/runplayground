import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "@tanstack/react-router";
import {
  Activity,
  Archive,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  ListChecks,
  Pencil,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  Unlink,
  Upload,
  X,
} from "lucide-react";

import type {
  RegisteredPlan,
  RegisteredPlanCreate,
  RegisteredPlanDetail,
  RegisteredPlanSession,
  RegisteredPlanSessionCreate,
  RegisteredPlanSessionUpdate,
  RegisteredPlanUpdate,
} from "@/api/client";
import {
  useActivatePlan,
  useArchivePlan,
  useBulkSessions,
  useCreatePlan,
  useCreatePlanFromSuggested,
  useCreateSession,
  useDeletePlan,
  useDeleteSession,
  useLinkActivity,
  usePlan,
  usePlans,
  useUnlinkActivity,
  useUpdatePlan,
  useUpdateSession,
} from "@/api/planQueries";
import { useActivities, useRaces } from "@/api/queries";
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
  formatDate,
  formatDistance,
  formatDuration,
  formatWeekRange,
  parseUtc,
  toISODate,
} from "@/lib/format";

const SESSION_TYPES: Array<{ value: string; key: MessageKey }> = [
  { value: "easy", key: "plan.session.type.easy" },
  { value: "recovery", key: "plan.session.type.recovery" },
  { value: "strides", key: "plan.session.type.strides" },
  { value: "long", key: "plan.session.type.long" },
  { value: "threshold", key: "plan.session.type.threshold" },
  { value: "race_pace", key: "plan.session.type.race_pace" },
  { value: "strength", key: "plan.session.type.strength" },
  { value: "cross_training", key: "plan.session.type.cross_training" },
  { value: "rest", key: "plan.session.type.rest" },
  { value: "other", key: "plan.session.type.other" },
];

const SESSION_TYPE_KEYS = Object.fromEntries(
  SESSION_TYPES.map((item) => [item.value, item.key]),
) as Record<string, MessageKey>;

const INTENSITIES = ["easy", "moderate", "hard", "rest"] as const;
const INTENSITY_KEYS: Record<string, MessageKey> = {
  easy: "plan.session.intensity.easy",
  moderate: "plan.session.intensity.moderate",
  hard: "plan.session.intensity.hard",
  rest: "plan.session.intensity.rest",
};

const STATUS_KEYS: Record<string, MessageKey> = {
  planned: "plan.session.status.planned",
  completed: "plan.session.status.completed",
  skipped: "plan.session.status.skipped",
};

const STATUS_TONE: Record<string, "success" | "warning" | "danger" | "info" | "neutral"> = {
  planned: "info",
  completed: "success",
  skipped: "neutral",
};

function weekdayMonday(value: string): string {
  const date = parseUtc(value);
  date.setDate(date.getDate() - ((date.getDay() + 6) % 7));
  return toISODate(date);
}

function addDays(value: string, days: number): string {
  const date = parseUtc(value);
  date.setDate(date.getDate() + days);
  return toISODate(date);
}

function sessionTarget(
  session: RegisteredPlanSession,
  units: Units,
  locale: Locale,
): string {
  if (session.type === "rest") return "—";
  const parts: string[] = [];
  if (session.distance_m) {
    parts.push(formatDistance(session.distance_m, units, locale, { digits: 1 }));
  }
  if (session.duration_s) {
    parts.push(formatDuration(session.duration_s, locale, true));
  }
  return parts.length ? parts.join(" · ") : "—";
}

export function PlanPage() {
  const { t, locale, units } = useI18n();
  const [includeArchived, setIncludeArchived] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [planForm, setPlanForm] = useState<"new" | "edit" | null>(null);
  const [sessionForm, setSessionForm] = useState<RegisteredPlanSession | "new" | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [suggestedOpen, setSuggestedOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const plans = usePlans(includeArchived);
  const plan = usePlan(selectedId);
  const activate = useActivatePlan();
  const archive = useArchivePlan();
  const remove = useDeletePlan();

  useEffect(() => {
    if (selectedId !== null || !plans.data?.length) return;
    const active = plans.data.find((item) => item.is_active && !item.archived_at);
    setSelectedId(active?.id ?? plans.data[0].id);
  }, [plans.data, selectedId]);

  const grouped = useMemo(() => groupSessions(plan.data?.sessions ?? []), [plan.data]);
  const activePlan = (plans.data ?? []).find((item) => item.is_active && !item.archived_at);

  const handleDelete = () => {
    if (selectedId === null) return;
    if (!window.confirm(t("plan.confirm.delete"))) return;
    remove.mutate(selectedId, {
      onSuccess: () => {
        setSelectedId(null);
        setNotice(t("plan.notice.deleted"));
      },
    });
  };

  return (
    <div className="page-stack plan-page">
      <PageHeader
        eyebrow={t("plan.page.eyebrow")}
        title={t("plan.page.title")}
        description={t("plan.page.subtitle")}
        actions={
          <div className="plan-actions">
            <Button variant="secondary" size="sm" onClick={() => setSuggestedOpen((value) => !value)}>
              <Sparkles size={15} aria-hidden="true" />
              {t("plan.actions.fromSuggested")}
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                setPlanForm("new");
                setSessionForm(null);
              }}
            >
              <Plus size={15} aria-hidden="true" />
              {t("plan.actions.new")}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              loading={plans.isFetching || plan.isFetching}
              onClick={() => {
                void plans.refetch();
                void plan.refetch();
              }}
            >
              <RefreshCw size={15} aria-hidden="true" />
              {t("common.retry")}
            </Button>
          </div>
        }
      />

      {activePlan ? (
        <Card className="plan-active-banner">
          <span className="plan-active-banner__icon">
            <CheckCircle2 size={17} aria-hidden="true" />
          </span>
          <div>
            <span>{t("plan.list.active")}</span>
            <strong>{activePlan.name}</strong>
            <small>
              {formatDate(activePlan.start_date, locale)} –{" "}
              {formatDate(activePlan.end_date, locale)}
            </small>
          </div>
          <Link to="/calendar" className="button button--secondary button--sm">
            <CalendarDays size={14} aria-hidden="true" />
            {t("plan.actions.calendar")}
          </Link>
        </Card>
      ) : null}

      {suggestedOpen ? (
        <SuggestedPlanForm
          onClose={() => setSuggestedOpen(false)}
          onCreated={(created) => {
            setSelectedId(created.id);
            setSuggestedOpen(false);
            setNotice(t("plan.notice.suggested"));
          }}
        />
      ) : null}

      {planForm ? (
        <PlanForm
          plan={planForm === "edit" ? plan.data : undefined}
          onClose={() => setPlanForm(null)}
          onSaved={(saved) => {
            setSelectedId(saved.id);
            setPlanForm(null);
          }}
        />
      ) : null}

      {plans.isLoading ? (
        <div className="analysis-skeleton">
          <Skeleton className="skeleton--panel" />
          <Skeleton className="skeleton--panel" />
        </div>
      ) : plans.isError ? (
        <ErrorState
          message={plans.error instanceof Error ? plans.error.message : t("plan.error")}
          onRetry={() => void plans.refetch()}
        />
      ) : !plans.data?.length ? (
        <Card className="panel">
          <EmptyState
            icon={ClipboardList}
            title={t("plan.empty.title")}
            description={t("plan.empty.body")}
            action={
              <Button variant="primary" size="sm" onClick={() => setPlanForm("new")}>
                <Plus size={15} aria-hidden="true" />
                {t("plan.actions.new")}
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="plan-layout">
          <Card className="panel plan-list">
            <SectionHeading
              title={t("plan.list.title")}
              subtitle={t("plan.list.subtitle")}
              icon={ListChecks}
              action={
                <label className="plan-checkbox">
                  <input
                    type="checkbox"
                    checked={includeArchived}
                    onChange={(event) => setIncludeArchived(event.target.checked)}
                  />
                  {t("plan.list.includeArchived")}
                </label>
              }
            />
            <div className="plan-list__items">
              {plans.data.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={cn("plan-list__item", selectedId === item.id && "is-selected")}
                  onClick={() => {
                    setSelectedId(item.id);
                    setSessionForm(null);
                    setPlanForm(null);
                  }}
                >
                  <span className="plan-list__head">
                    <strong>{item.name}</strong>
                    {item.is_active ? (
                      <Badge tone="success">{t("plan.list.active")}</Badge>
                    ) : item.archived_at ? (
                      <Badge tone="neutral">{t("plan.list.archived")}</Badge>
                    ) : (
                      <Badge tone="info">{t("plan.list.inactive")}</Badge>
                    )}
                  </span>
                  <span className="plan-list__meta">
                    {formatDate(item.start_date, locale)} – {formatDate(item.end_date, locale)}
                  </span>
                  <span className="plan-list__meta">
                    {t("plan.summary.sessions", { count: item.sessions_total })} ·{" "}
                    {formatDistance(item.planned_distance_m, units, locale, { digits: 1 })}
                  </span>
                </button>
              ))}
            </div>
          </Card>

          <div className="plan-detail">
            {plan.isLoading ? (
              <Card className="panel">
                <Skeleton className="skeleton--block" />
              </Card>
            ) : plan.isError || !plan.data ? (
              <Card className="panel">
                <ErrorState
                  message={plan.error instanceof Error ? plan.error.message : t("plan.error")}
                  onRetry={() => void plan.refetch()}
                />
              </Card>
            ) : (
              <>
                <PlanSummary
                  plan={plan.data}
                  units={units}
                  locale={locale}
                  busy={activate.isPending || archive.isPending || remove.isPending}
                  onEdit={() => setPlanForm("edit")}
                  onDelete={handleDelete}
                  onActivate={() => {
                    activate.mutate(plan.data.id, {
                      onSuccess: () => setNotice(t("plan.notice.activated")),
                      onError: (error) =>
                        setNotice(error instanceof Error ? error.message : t("plan.error")),
                    });
                  }}
                  onArchive={() => {
                    archive.mutate(plan.data.id, {
                      onSuccess: () => setNotice(t("plan.notice.archived")),
                      onError: (error) =>
                        setNotice(error instanceof Error ? error.message : t("plan.error")),
                    });
                  }}
                />

                <Card className="panel plan-sessions">
                  <SectionHeading
                    title={t("plan.sessions.title")}
                    subtitle={t("plan.sessions.subtitle")}
                    icon={ClipboardList}
                    action={
                      <div className="plan-actions">
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => {
                            setBulkOpen((value) => !value);
                            setSessionForm(null);
                          }}
                        >
                          <Upload size={14} aria-hidden="true" />
                          {t("plan.bulk.button")}
                        </Button>
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => {
                            setSessionForm("new");
                            setBulkOpen(false);
                          }}
                        >
                          <Plus size={14} aria-hidden="true" />
                          {t("plan.sessions.add")}
                        </Button>
                      </div>
                    }
                  />

                  {bulkOpen ? (
                    <BulkForm plan={plan.data} onClose={() => setBulkOpen(false)} />
                  ) : null}

                  {sessionForm ? (
                    <SessionForm
                      plan={plan.data}
                      session={sessionForm === "new" ? undefined : sessionForm}
                      onClose={() => setSessionForm(null)}
                    />
                  ) : null}

                  {grouped.length === 0 ? (
                    <EmptyState
                      compact
                      icon={ClipboardList}
                      title={t("plan.sessions.emptyTitle")}
                      description={t("plan.sessions.emptyBody")}
                      action={
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => setSessionForm("new")}
                        >
                          <Plus size={14} aria-hidden="true" />
                          {t("plan.sessions.add")}
                        </Button>
                      }
                    />
                  ) : (
                    <div className="plan-weeks">
                      {grouped.map((week) => (
                        <div key={week.week} className="plan-week">
                          <div className="plan-week__head">
                            <strong>
                              {formatWeekRange(week.week, addDays(week.week, 6), locale)}
                            </strong>
                            <span>
                              {t("plan.week.sessions", { count: week.sessions.length })} ·{" "}
                              {formatDistance(
                                week.sessions.reduce(
                                  (total, session) =>
                                    total +
                                    (isRunningSession(session) ? session.distance_m ?? 0 : 0),
                                  0,
                                ),
                                units,
                                locale,
                                { digits: 1 },
                              )}
                            </span>
                          </div>
                          <div className="plan-week__rows">
                            {week.sessions.map((session) => (
                              <SessionRow
                                key={session.id}
                                plan={plan.data}
                                session={session}
                                units={units}
                                locale={locale}
                                onEdit={() => {
                                  setSessionForm(session);
                                  setBulkOpen(false);
                                }}
                              />
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </Card>
              </>
            )}
          </div>
        </div>
      )}

      {notice ? (
        <div className="form-success plan-notice" role="status">
          {notice}
          <button type="button" onClick={() => setNotice(null)} aria-label={t("common.close")}>
            <X size={14} aria-hidden="true" />
          </button>
        </div>
      ) : null}

      <p className="analysis-note">{t("plan.note")}</p>
    </div>
  );
}

function isRunningSession(session: RegisteredPlanSession): boolean {
  return !["rest", "strength", "cross_training"].includes(session.type);
}

function groupSessions(
  sessions: RegisteredPlanSession[],
): Array<{ week: string; sessions: RegisteredPlanSession[] }> {
  const buckets = new Map<string, RegisteredPlanSession[]>();
  for (const session of sessions) {
    const week = weekdayMonday(session.session_date);
    const bucket = buckets.get(week);
    if (bucket) bucket.push(session);
    else buckets.set(week, [session]);
  }
  return [...buckets.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([week, items]) => ({
      week,
      sessions: items.sort((left, right) =>
        `${left.session_date}-${String(left.position).padStart(3, "0")}`.localeCompare(
          `${right.session_date}-${String(right.position).padStart(3, "0")}`,
        ),
      ),
    }));
}

function PlanSummary({
  plan,
  units,
  locale,
  busy,
  onEdit,
  onDelete,
  onActivate,
  onArchive,
}: {
  plan: RegisteredPlanDetail;
  units: Units;
  locale: Locale;
  busy: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onActivate: () => void;
  onArchive: () => void;
}) {
  const { t } = useI18n();
  const decided = plan.sessions_completed + plan.sessions_skipped;
  const completion = decided > 0 ? (plan.sessions_completed / decided) * 100 : 0;
  return (
    <Card className="panel plan-summary">
      <SectionHeading
        title={plan.name}
        subtitle={plan.description ?? t("plan.summary.noDescription")}
        icon={ClipboardList}
        action={
          plan.is_active ? (
            <Badge tone="success" dot>
              {t("plan.list.active")}
            </Badge>
          ) : plan.archived_at ? (
            <Badge tone="neutral">{t("plan.list.archived")}</Badge>
          ) : (
            <Badge tone="info">{t("plan.list.inactive")}</Badge>
          )
        }
      />

      <div className="plan-summary__meta">
        <div>
          <span>{t("plan.summary.range")}</span>
          <strong>
            {formatDate(plan.start_date, locale)} – {formatDate(plan.end_date, locale)}
          </strong>
        </div>
        <div>
          <span>{t("plan.summary.goalRace")}</span>
          <strong>{plan.goal_race_name ?? t("plan.summary.noGoalRace")}</strong>
        </div>
        <div>
          <span>{t("plan.summary.source")}</span>
          <strong>{t(`plan.source.${plan.source}` as MessageKey)}</strong>
        </div>
        <div>
          <span>{t("plan.summary.version")}</span>
          <strong>v{plan.version}</strong>
        </div>
      </div>

      <div className="plan-summary__metrics">
        <div>
          <span>{t("plan.summary.sessionsLabel")}</span>
          <strong>{plan.sessions_total}</strong>
        </div>
        <div>
          <span>{t("plan.summary.completed")}</span>
          <strong>{plan.sessions_completed}</strong>
        </div>
        <div>
          <span>{t("plan.summary.skipped")}</span>
          <strong>{plan.sessions_skipped}</strong>
        </div>
        <div>
          <span>{t("plan.summary.distance")}</span>
          <strong>{formatDistance(plan.planned_distance_m, units, locale, { digits: 1 })}</strong>
        </div>
      </div>

      <div className="plan-summary__progress">
        <ProgressBar value={completion} label={t("plan.summary.completion")} />
        <span>
          {t("plan.summary.completionValue", { value: Math.round(completion) })}
        </span>
      </div>

      <div className="plan-summary__actions">
        <Button variant="secondary" size="sm" onClick={onEdit} disabled={busy}>
          <Pencil size={14} aria-hidden="true" />
          {t("plan.actions.edit")}
        </Button>
        {plan.is_active ? (
          <Button variant="secondary" size="sm" onClick={onArchive} loading={busy}>
            <Archive size={14} aria-hidden="true" />
            {t("plan.actions.archive")}
          </Button>
        ) : (
          <Button
            variant="primary"
            size="sm"
            onClick={onActivate}
            loading={busy}
            disabled={Boolean(plan.archived_at) || (plan.sessions ?? []).length === 0}
          >
            <CheckCircle2 size={14} aria-hidden="true" />
            {t("plan.actions.activate")}
          </Button>
        )}
        <Button variant="danger" size="sm" onClick={onDelete} loading={busy}>
          <Trash2 size={14} aria-hidden="true" />
          {t("plan.actions.delete")}
        </Button>
      </div>
    </Card>
  );
}

function SessionRow({
  plan,
  session,
  units,
  locale,
  onEdit,
}: {
  plan: RegisteredPlanDetail;
  session: RegisteredPlanSession;
  units: Units;
  locale: Locale;
  onEdit: () => void;
}) {
  const { t } = useI18n();
  const [linkOpen, setLinkOpen] = useState(false);
  const unlink = useUnlinkActivity(plan.id);
  const typeKey = SESSION_TYPE_KEYS[session.type];
  return (
    <div className={cn("plan-session-row", `is-${session.status}`)}>
      <div className="plan-session-row__date">
        <strong>{formatDate(session.session_date, locale)}</strong>
        <span>{t(typeKey ?? "plan.session.type.other")}</span>
      </div>
      <div className="plan-session-row__target">
        <span>{sessionTarget(session, units, locale)}</span>
        {session.notes ? <small>{session.notes}</small> : null}
      </div>
      <div className="plan-session-row__badges">
        <Badge tone={INTENSITY_TONE[session.intensity] ?? "neutral"}>
          {t(INTENSITY_KEYS[session.intensity] ?? "plan.session.intensity.easy")}
        </Badge>
        <Badge tone={STATUS_TONE[session.status] ?? "neutral"}>
          {t(STATUS_KEYS[session.status] ?? "plan.session.status.planned")}
        </Badge>
      </div>
      <div className="plan-session-row__activity">
        {session.activity_id ? (
          <Link
            to="/activities/$activityId"
            params={{ activityId: String(session.activity_id) }}
            className="text-link"
          >
            <Activity size={13} aria-hidden="true" />
            {session.activity_name ?? `#${session.activity_id}`}
          </Link>
        ) : (
          <span>{t("plan.session.noActivity")}</span>
        )}
      </div>
      <div className="plan-session-row__actions">
        {session.activity_id ? (
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("plan.session.unlink")}
            loading={unlink.isPending}
            onClick={() => unlink.mutate(session.id)}
          >
            <Unlink size={14} aria-hidden="true" />
          </Button>
        ) : (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setLinkOpen((value) => !value)}
            disabled={session.status === "skipped" || session.type === "rest"}
          >
            <LinkIcon />
            {t("plan.session.link")}
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("plan.actions.edit")}
          onClick={onEdit}
        >
          <Pencil size={14} aria-hidden="true" />
        </Button>
        <DeleteSessionButton plan={plan} session={session} />
      </div>
      {linkOpen ? (
        <LinkActivityForm
          plan={plan}
          session={session}
          onClose={() => setLinkOpen(false)}
        />
      ) : null}
    </div>
  );
}

const INTENSITY_TONE: Record<string, "success" | "warning" | "danger" | "neutral" | "info"> = {
  easy: "info",
  moderate: "warning",
  hard: "danger",
  rest: "neutral",
};

function LinkIcon() {
  return <Activity size={14} aria-hidden="true" />;
}

function DeleteSessionButton({
  plan,
  session,
}: {
  plan: RegisteredPlanDetail;
  session: RegisteredPlanSession;
}) {
  const { t } = useI18n();
  const remove = useDeleteSession(plan.id);
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={t("plan.actions.delete")}
      loading={remove.isPending}
      onClick={() => {
        if (window.confirm(t("plan.confirm.deleteSession"))) {
          remove.mutate(session.id);
        }
      }}
    >
      <Trash2 size={14} aria-hidden="true" />
    </Button>
  );
}

function LinkActivityForm({
  plan,
  session,
  onClose,
}: {
  plan: RegisteredPlanDetail;
  session: RegisteredPlanSession;
  onClose: () => void;
}) {
  const { t, locale, units } = useI18n();
  const [activityId, setActivityId] = useState<number | null>(null);
  const link = useLinkActivity(plan.id);
  const activities = useActivities({
    from: session.session_date,
    to: session.session_date,
    limit: 100,
    sport: "running",
  });
  const items = activities.data?.items ?? [];
  return (
    <div className="plan-link-form">
      <div className="plan-link-form__head">
        <strong>{t("plan.link.title")}</strong>
        <span>{formatDate(session.session_date, locale)}</span>
      </div>
      {activities.isLoading ? (
        <Skeleton className="skeleton--line" />
      ) : items.length === 0 ? (
        <p className="analysis-note">{t("plan.link.empty")}</p>
      ) : (
        <>
          <select
            value={activityId ?? ""}
            onChange={(event) =>
              setActivityId(event.target.value ? Number(event.target.value) : null)
            }
          >
            <option value="">{t("plan.link.choose")}</option>
            {items.map((activity) => (
              <option key={activity.id} value={activity.id}>
                {activity.name} ·{" "}
                {formatDistance(activity.distance_m, units, locale, { digits: 1 })}
              </option>
            ))}
          </select>
          <div className="plan-link-form__actions">
            <Button
              variant="primary"
              size="sm"
              loading={link.isPending}
              disabled={activityId === null}
              onClick={() => {
                if (activityId === null) return;
                link.mutate(
                  { sessionId: session.id, activityId },
                  { onSuccess: onClose },
                );
              }}
            >
              {t("plan.link.submit")}
            </Button>
            <Button variant="ghost" size="sm" onClick={onClose}>
              {t("common.cancel")}
            </Button>
          </div>
        </>
      )}
      {link.isError ? (
        <p className="form-error">
          {link.error instanceof Error ? link.error.message : t("plan.link.error")}
        </p>
      ) : null}
    </div>
  );
}

function SessionForm({
  plan,
  session,
  onClose,
}: {
  plan: RegisteredPlanDetail;
  session?: RegisteredPlanSession;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const create = useCreateSession(plan.id);
  const update = useUpdateSession(plan.id);
  const [date, setDate] = useState(session?.session_date ?? plan.start_date);
  const [type, setType] = useState(session?.type ?? "easy");
  const [intensity, setIntensity] = useState(session?.intensity ?? "easy");
  const [distanceKm, setDistanceKm] = useState(
    session?.distance_m ? String(Math.round(session.distance_m / 100) / 10) : "",
  );
  const [durationMin, setDurationMin] = useState(
    session?.duration_s ? String(Math.round(session.duration_s / 60)) : "",
  );
  const [notes, setNotes] = useState(session?.notes ?? "");
  const [status, setStatus] = useState(session?.status ?? "planned");
  const [problem, setProblem] = useState<string | null>(null);
  const pending = create.isPending || update.isPending;
  const isRest = type === "rest";

  const changeType = (value: string) => {
    setType(value);
    if (value === "rest") {
      setIntensity("rest");
      setDistanceKm("");
      setDurationMin("");
    } else if (intensity === "rest") {
      setIntensity(value === "strength" || value === "cross_training" ? "moderate" : "easy");
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const distance = distanceKm.trim() ? Number(distanceKm) * 1000 : null;
    const duration = durationMin.trim() ? Number(durationMin) * 60 : null;
    if (!date || date < plan.start_date || date > plan.end_date) {
      setProblem(t("plan.session.invalidDate"));
      return;
    }
    if (!isRest && distance === null && duration === null) {
      setProblem(t("plan.session.invalidTarget"));
      return;
    }
    if (distance !== null && (!Number.isFinite(distance) || distance <= 0)) {
      setProblem(t("plan.session.invalidTarget"));
      return;
    }
    if (duration !== null && (!Number.isFinite(duration) || duration <= 0)) {
      setProblem(t("plan.session.invalidTarget"));
      return;
    }
    setProblem(null);
    const payload: RegisteredPlanSessionCreate = {
      session_date: date,
      type: type as RegisteredPlanSessionCreate["type"],
      intensity: (isRest ? "rest" : intensity) as RegisteredPlanSessionCreate["intensity"],
      distance_m: isRest ? null : distance,
      duration_s: isRest ? null : duration,
      status: status as RegisteredPlanSessionCreate["status"],
      notes: notes.trim() || null,
    };
    const onError = (error: unknown) =>
      setProblem(error instanceof Error ? error.message : t("plan.session.error"));
    if (session) {
      update.mutate(
        { sessionId: session.id, patch: payload as RegisteredPlanSessionUpdate },
        { onSuccess: onClose, onError },
      );
    } else {
      create.mutate(payload, { onSuccess: onClose, onError });
    }
  };

  return (
    <form className="plan-form plan-session-form" onSubmit={submit}>
      <div className="plan-form__head">
        <strong>{session ? t("plan.session.editTitle") : t("plan.session.addTitle")}</strong>
        <span>
          {t("plan.session.range", {
            start: plan.start_date,
            end: plan.end_date,
          })}
        </span>
      </div>
      <label>
        <span>{t("plan.session.date")}</span>
        <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
      </label>
      <label>
        <span>{t("plan.session.type")}</span>
        <select value={type} onChange={(event) => changeType(event.target.value)}>
          {SESSION_TYPES.map((item) => (
            <option key={item.value} value={item.value}>
              {t(item.key)}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>{t("plan.session.intensity")}</span>
        <select
          value={intensity}
          disabled={isRest}
          onChange={(event) => setIntensity(event.target.value)}
        >
          {INTENSITIES.map((value) => (
            <option key={value} value={value}>
              {t(INTENSITY_KEYS[value])}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>{t("plan.session.distance")}</span>
        <input
          value={distanceKm}
          onChange={(event) => setDistanceKm(event.target.value)}
          inputMode="decimal"
          disabled={isRest}
          placeholder="10"
        />
      </label>
      <label>
        <span>{t("plan.session.duration")}</span>
        <input
          value={durationMin}
          onChange={(event) => setDurationMin(event.target.value)}
          inputMode="numeric"
          disabled={isRest}
          placeholder="45"
        />
      </label>
      <label>
        <span>{t("plan.session.status")}</span>
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="planned">{t("plan.session.status.planned")}</option>
          <option value="completed">{t("plan.session.status.completed")}</option>
          <option value="skipped">{t("plan.session.status.skipped")}</option>
        </select>
      </label>
      <label className="plan-form__wide">
        <span>{t("plan.session.notes")}</span>
        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          rows={2}
          maxLength={2000}
        />
      </label>
      {problem ? <p className="form-error">{problem}</p> : null}
      <div className="plan-form__actions">
        <Button type="submit" variant="primary" size="sm" loading={pending}>
          {pending ? t("plan.session.saving") : t("common.save")}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}

function PlanForm({
  plan,
  onClose,
  onSaved,
}: {
  plan?: RegisteredPlanDetail;
  onClose: () => void;
  onSaved: (plan: RegisteredPlan) => void;
}) {
  const { t } = useI18n();
  const create = useCreatePlan();
  const update = useUpdatePlan(plan?.id ?? 0);
  const races = useRaces();
  const [name, setName] = useState(plan?.name ?? "");
  const [description, setDescription] = useState(plan?.description ?? "");
  const [start, setStart] = useState(plan?.start_date ?? toISODate(new Date()));
  const [end, setEnd] = useState(
    plan?.end_date ?? toISODate(new Date(Date.now() + 28 * 86_400_000)),
  );
  const [goalRaceId, setGoalRaceId] = useState<number | null>(plan?.goal_race_id ?? null);
  const [problem, setProblem] = useState<string | null>(null);
  const pending = create.isPending || update.isPending;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim() || !start || !end) {
      setProblem(t("plan.form.required"));
      return;
    }
    if (end < start) {
      setProblem(t("plan.form.invalidRange"));
      return;
    }
    setProblem(null);
    const payload: RegisteredPlanCreate = {
      name: name.trim(),
      description: description.trim() || null,
      start_date: start,
      end_date: end,
      goal_race_id: goalRaceId,
      source: plan?.source === "suggested" ? "suggested" : "manual",
    };
    const onError = (error: unknown) =>
      setProblem(error instanceof Error ? error.message : t("plan.form.error"));
    if (plan) {
      update.mutate(payload as RegisteredPlanUpdate, {
        onSuccess: (saved) => onSaved(saved),
        onError,
      });
    } else {
      create.mutate(payload, { onSuccess: onSaved, onError });
    }
  };

  return (
    <Card className="panel plan-form-card">
      <SectionHeading
        title={plan ? t("plan.form.editTitle") : t("plan.form.title")}
        subtitle={t("plan.form.subtitle")}
        icon={ClipboardList}
        action={
          <Button variant="ghost" size="icon" aria-label={t("common.close")} onClick={onClose}>
            <X size={16} aria-hidden="true" />
          </Button>
        }
      />
      <form className="plan-form" onSubmit={submit}>
        <label>
          <span>{t("plan.form.name")}</span>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={255}
            autoFocus
          />
        </label>
        <label>
          <span>{t("plan.form.goalRace")}</span>
          <select
            value={goalRaceId ?? ""}
            onChange={(event) =>
              setGoalRaceId(event.target.value ? Number(event.target.value) : null)
            }
          >
            <option value="">{t("plan.form.noGoalRace")}</option>
            {(races.data ?? []).map((race) => (
              <option key={race.id} value={race.id}>
                {race.name} · {race.race_date}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>{t("plan.form.start")}</span>
          <input type="date" value={start} onChange={(event) => setStart(event.target.value)} />
        </label>
        <label>
          <span>{t("plan.form.end")}</span>
          <input type="date" value={end} onChange={(event) => setEnd(event.target.value)} />
        </label>
        <label className="plan-form__wide">
          <span>{t("plan.form.description")}</span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={2}
            maxLength={2000}
          />
        </label>
        {problem ? <p className="form-error">{problem}</p> : null}
        <div className="plan-form__actions">
          <Button type="submit" variant="primary" size="sm" loading={pending}>
            {pending ? t("plan.form.saving") : t("common.save")}
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            {t("common.cancel")}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function BulkForm({ plan, onClose }: { plan: RegisteredPlanDetail; onClose: () => void }) {
  const { t } = useI18n();
  const bulk = useBulkSessions(plan.id);
  const [text, setText] = useState(() =>
    JSON.stringify(
      [
        {
          session_date: plan.start_date,
          type: "easy",
          intensity: "easy",
          distance_m: 8000,
        },
        {
          session_date: plan.start_date,
          type: "rest",
          intensity: "rest",
        },
      ],
      null,
      2,
    ),
  );
  const [problem, setProblem] = useState<string | null>(null);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    try {
      const parsed = JSON.parse(text) as unknown;
      const sessions = Array.isArray(parsed)
        ? parsed
        : parsed && typeof parsed === "object" && "sessions" in parsed
          ? (parsed as { sessions: unknown }).sessions
          : null;
      if (!Array.isArray(sessions) || sessions.length === 0) {
        setProblem(t("plan.bulk.invalid"));
        return;
      }
      setProblem(null);
      bulk.mutate(sessions as RegisteredPlanSessionCreate[], {
        onSuccess: () => {
          setProblem(null);
          onClose();
        },
        onError: (error) =>
          setProblem(error instanceof Error ? error.message : t("plan.bulk.error")),
      });
    } catch {
      setProblem(t("plan.bulk.invalid"));
    }
  };
  return (
    <form className="plan-form plan-bulk-form" onSubmit={submit}>
      <div className="plan-form__head">
        <strong>{t("plan.bulk.title")}</strong>
        <span>{t("plan.bulk.hint")}</span>
      </div>
      <label className="plan-form__wide">
        <span>{t("plan.bulk.json")}</span>
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={8}
          spellCheck={false}
        />
      </label>
      {problem ? <p className="form-error">{problem}</p> : null}
      {bulk.isError ? (
        <p className="form-error">
          {bulk.error instanceof Error ? bulk.error.message : t("plan.bulk.error")}
        </p>
      ) : null}
      <div className="plan-form__actions">
        <Button type="submit" variant="primary" size="sm" loading={bulk.isPending}>
          <Upload size={14} aria-hidden="true" />
          {t("plan.bulk.submit")}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}

function SuggestedPlanForm({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (plan: RegisteredPlanDetail) => void;
}) {
  const { t } = useI18n();
  const create = useCreatePlanFromSuggested();
  const [name, setName] = useState("Plan sugerido");
  const [start, setStart] = useState(toISODate(new Date()));
  const [weeks, setWeeks] = useState<4 | 8 | 12>(4);
  const [activate, setActivate] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setProblem(t("plan.form.required"));
      return;
    }
    setProblem(null);
    create.mutate(
      {
        name: name.trim(),
        start_date: start,
        weeks,
        activate,
      },
      {
        onSuccess: onCreated,
        onError: (error) =>
          setProblem(error instanceof Error ? error.message : t("plan.suggested.error")),
      },
    );
  };
  return (
    <Card className="panel plan-form-card">
      <SectionHeading
        title={t("plan.suggested.title")}
        subtitle={t("plan.suggested.subtitle")}
        icon={Sparkles}
        action={
          <Button variant="ghost" size="icon" aria-label={t("common.close")} onClick={onClose}>
            <X size={16} aria-hidden="true" />
          </Button>
        }
      />
      <form className="plan-form" onSubmit={submit}>
        <label>
          <span>{t("plan.form.name")}</span>
          <input value={name} onChange={(event) => setName(event.target.value)} maxLength={255} />
        </label>
        <label>
          <span>{t("plan.suggested.weeks")}</span>
          <select
            value={weeks}
            onChange={(event) => setWeeks(Number(event.target.value) as 4 | 8 | 12)}
          >
            {[4, 8, 12].map((value) => (
              <option key={value} value={value}>
                {t("plan.suggested.weeksValue", { weeks: value })}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>{t("plan.form.start")}</span>
          <input type="date" value={start} onChange={(event) => setStart(event.target.value)} />
        </label>
        <label className="plan-checkbox">
          <input
            type="checkbox"
            checked={activate}
            onChange={(event) => setActivate(event.target.checked)}
          />
          {t("plan.suggested.activate")}
        </label>
        {problem ? <p className="form-error">{problem}</p> : null}
        <div className="plan-form__actions">
          <Button type="submit" variant="primary" size="sm" loading={create.isPending}>
            <Sparkles size={14} aria-hidden="true" />
            {t("plan.suggested.submit")}
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            {t("common.cancel")}
          </Button>
        </div>
      </form>
    </Card>
  );
}
