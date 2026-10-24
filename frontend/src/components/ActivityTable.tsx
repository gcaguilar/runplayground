import { useMemo } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Flag } from "lucide-react";

import type { Activity } from "@/api/client";
import { useI18n } from "@/i18n";
import { Badge, Button, Skeleton } from "@/components/ui";
import { cn } from "@/lib/cn";
import {
  formatDate,
  formatDistance,
  formatDuration,
  formatNumber,
  formatPace,
  formatTimeOfDay,
  sportKey,
} from "@/lib/format";

export type ActivitySort =
  | "date_desc"
  | "date_asc"
  | "distance_desc"
  | "distance_asc"
  | "duration_desc"
  | "duration_asc";

type Props = {
  activities: Activity[];
  total: number;
  pageIndex: number;
  pageSize: number;
  sort: ActivitySort;
  loading?: boolean;
  onSortChange: (sort: ActivitySort) => void;
  onPageChange: (pageIndex: number) => void;
};

export function ActivityTable({
  activities,
  total,
  pageIndex,
  pageSize,
  sort,
  loading = false,
  onSortChange,
  onPageChange,
}: Props) {
  const { locale, units, t } = useI18n();
  const navigate = useNavigate();

  const columns = useMemo<ColumnDef<Activity>[]>(
    () => [
      {
        id: "date",
        header: t("activities.table.date"),
        cell: ({ row }) => (
          <div className="activity-date">
            <strong>{formatDate(row.original.start_time_utc, locale, { day: "2-digit", month: "short" })}</strong>
            <span>{formatTimeOfDay(row.original.start_time_utc, locale)}</span>
          </div>
        ),
      },
      {
        id: "activity",
        header: t("activities.table.activity"),
        cell: ({ row }) => {
          const activity = row.original;
          const name = activity.name?.trim() || t(sportKey(activity.sub_sport || activity.sport));
          return (
            <div className="activity-name">
              <span className="activity-name__dot" aria-hidden="true" />
              <span className="activity-name__copy">
                <Link
                  to="/activities/$activityId"
                  params={{ activityId: String(activity.id) }}
                  onClick={(event) => event.stopPropagation()}
                >
                  {name}
                </Link>
                {activity.is_race ? (
                  <span className="activity-race">
                    <Flag size={11} aria-hidden="true" />
                    {t("detail.race")}
                  </span>
                ) : null}
              </span>
            </div>
          );
        },
      },
      {
        id: "sport",
        header: t("activities.table.sport"),
        cell: ({ row }) => (
          <span className="sport-tag">{t(sportKey(row.original.sub_sport || row.original.sport))}</span>
        ),
      },
      {
        id: "distance",
        header: t("activities.table.distance"),
        cell: ({ row }) => (
          <span className="num">{formatDistance(row.original.distance_m, units, locale)}</span>
        ),
      },
      {
        id: "duration",
        header: t("activities.table.duration"),
        cell: ({ row }) => (
          <span className="num">{formatDuration(row.original.duration_s, locale, true)}</span>
        ),
      },
      {
        id: "pace",
        header: t("activities.table.pace"),
        cell: ({ row }) => (
          <span className="num num--accent">
            {formatPace(row.original.avg_pace_s_per_km, units)}
          </span>
        ),
      },
      {
        id: "hr",
        header: t("activities.table.hr"),
        cell: ({ row }) => (
          <span className="num">
            {row.original.avg_hr ? `${formatNumber(row.original.avg_hr, locale)} bpm` : "—"}
          </span>
        ),
      },
      {
        id: "source",
        header: t("activities.table.source"),
        cell: ({ row }) => (
          <div className="source-list">
            {(row.original.source_names ?? []).map((source) => (
              <span key={source} className="source-tag">
                {source === "garmin_api" ? "Garmin" : t("activities.source.upload")}
              </span>
            ))}
          </div>
        ),
      },
      {
        id: "quality",
        header: t("activities.table.quality"),
        cell: ({ row }) => <QualityBadge activity={row.original} />,
      },
    ],
    [locale, t, units],
  );

  const table = useReactTable({
    data: activities,
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    pageCount: Math.ceil(total / pageSize),
  });

  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const from = total > 0 ? pageIndex * pageSize + 1 : 0;
  const to = Math.min(total, (pageIndex + 1) * pageSize);

  return (
    <div className="table-shell">
      <div className="table-wrap">
        <table className="activity-table">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const id = header.column.id;
                  const sortable = id === "date" || id === "distance" || id === "duration";
                  const active = sort.startsWith(`${id}_`);
                  const descending = sort.endsWith("_desc");
                  return (
                    <th
                      key={header.id}
                      aria-sort={
                        sortable
                          ? active
                            ? descending
                              ? "descending"
                              : "ascending"
                            : "none"
                          : undefined
                      }
                    >
                      {sortable ? (
                        <button
                          type="button"
                          className={cn("table-sort", active && "is-active")}
                          onClick={() =>
                            onSortChange(
                              `${id}_${active && descending ? "asc" : "desc"}` as ActivitySort,
                            )
                          }
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {active ? (
                            descending ? (
                              <ArrowDown size={12} aria-hidden="true" />
                            ) : (
                              <ArrowUp size={12} aria-hidden="true" />
                            )
                          ) : null}
                        </button>
                      ) : (
                        flexRender(header.column.columnDef.header, header.getContext())
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: Math.min(pageSize, 8) }).map((_, index) => (
                  <tr key={`skeleton-${index}`} className="skeleton-row">
                    {columns.map((column) => (
                      <td key={column.id}>
                        <Skeleton className="skeleton--line" />
                      </td>
                    ))}
                  </tr>
                ))
              : table.getRowModel().rows.map((row) => (
                  <tr
                    key={row.id}
                    tabIndex={0}
                    onClick={() =>
                      navigate({
                        to: "/activities/$activityId",
                        params: { activityId: String(row.original.id) },
                      })
                    }
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        navigate({
                          to: "/activities/$activityId",
                          params: { activityId: String(row.original.id) },
                        });
                      }
                    }}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                    ))}
                  </tr>
                ))}
          </tbody>
        </table>
      </div>

      <div className="table-footer">
        <span className="table-footer__info">
          {t("activities.pageInfo", { from, to, total })}
        </span>
        <div className="pagination">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onPageChange(pageIndex - 1)}
            disabled={pageIndex <= 0 || loading}
            aria-label={t("common.previous")}
          >
            <ChevronLeft size={15} aria-hidden="true" />
            <span>{t("common.previous")}</span>
          </Button>
          <span className="pagination__page mono">
            {pageIndex + 1} / {pageCount}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onPageChange(pageIndex + 1)}
            disabled={pageIndex + 1 >= pageCount || loading}
            aria-label={t("common.next")}
          >
            <span>{t("common.next")}</span>
            <ChevronRight size={15} aria-hidden="true" />
          </Button>
        </div>
      </div>
    </div>
  );
}

export function QualityBadge({ activity, withLabel = true }: { activity: Activity; withLabel?: boolean }) {
  const { t } = useI18n();
  const flags = activity.quality_flag_list ?? [];
  const limited = !activity.has_streams || activity.avg_hr === null || activity.avg_hr === undefined;
  const partial = flags.length > 0;
  const tone = limited ? "danger" : partial ? "warning" : "success";
  const label = limited
    ? t("activities.quality.limited")
    : partial
      ? t("activities.quality.partial")
      : t("activities.quality.complete");
  if (!withLabel) return <span className={cn("quality-dot", `quality-dot--${tone}`)} title={label} />;
  return (
    <Badge tone={tone} dot>
      {label}
    </Badge>
  );
}
