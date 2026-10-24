import { useDeferredValue, useMemo, useState } from "react";
import { Link } from "@tanstack/react-router";
import { Search, SlidersHorizontal, Upload, X } from "lucide-react";

import { useActivities } from "@/api/queries";
import { ActivityTable, type ActivitySort } from "@/components/ActivityTable";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  SectionHeading,
} from "@/components/ui";
import { useI18n, type MessageKey } from "@/i18n";
import { cn } from "@/lib/cn";

const PAGE_SIZE = 25;

const SPORTS: Array<{ value: string; label: MessageKey }> = [
  { value: "", label: "activities.allSports" },
  { value: "running", label: "sport.running" },
  { value: "trail_running", label: "sport.trail_running" },
  { value: "treadmill_running", label: "sport.treadmill_running" },
  { value: "track_running", label: "sport.track_running" },
  { value: "cycling", label: "sport.cycling" },
  { value: "walking", label: "sport.walking" },
  { value: "hiking", label: "sport.hiking" },
  { value: "swimming", label: "sport.swimming" },
  { value: "strength_training", label: "sport.strength_training" },
];

export function ActivitiesPage() {
  const { t } = useI18n();
  const [search, setSearch] = useState("");
  const [sport, setSport] = useState("");
  const [sort, setSort] = useState<ActivitySort>("date_desc");
  const [pageIndex, setPageIndex] = useState(0);
  const deferredSearch = useDeferredValue(search.trim());

  const params = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset: pageIndex * PAGE_SIZE,
      sort,
      ...(sport ? { sport } : {}),
      ...(deferredSearch ? { q: deferredSearch } : {}),
    }),
    [deferredSearch, pageIndex, sort, sport],
  );

  const activities = useActivities(params);
  const items = activities.data?.items ?? [];
  const total = activities.data?.total ?? 0;
  const hasFilters = Boolean(search || sport);

  const updateSearch = (value: string) => {
    setSearch(value);
    setPageIndex(0);
  };

  const updateSport = (value: string) => {
    setSport(value);
    setPageIndex(0);
  };

  const clearFilters = () => {
    setSearch("");
    setSport("");
    setPageIndex(0);
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={t("nav.library")}
        title={t("activities.title")}
        description={t("activities.subtitle")}
        actions={
          <Link to="/imports" className="button button--primary button--md">
            <Upload size={16} aria-hidden="true" />
            {t("activities.import")}
          </Link>
        }
      />

      <Card className="panel activities-panel">
        <SectionHeading
          title={t("activities.title")}
          subtitle={t("activities.count", { count: total })}
          icon={SlidersHorizontal}
        />

        <div className="filter-bar">
          <label className="search-field">
            <Search size={16} aria-hidden="true" />
            <input
              type="search"
              value={search}
              onChange={(event) => updateSearch(event.target.value)}
              placeholder={t("activities.search")}
              aria-label={t("activities.search")}
            />
            {search ? (
              <button
                type="button"
                className="search-field__clear"
                onClick={() => updateSearch("")}
                aria-label={t("common.close")}
              >
                <X size={14} aria-hidden="true" />
              </button>
            ) : null}
          </label>

          <label className="select-field">
            <span>{t("activities.filterSport")}</span>
            <select value={sport} onChange={(event) => updateSport(event.target.value)}>
              {SPORTS.map((option) => (
                <option key={option.value || "all"} value={option.value}>
                  {t(option.label)}
                </option>
              ))}
            </select>
          </label>

          {hasFilters ? (
            <Button variant="ghost" size="sm" onClick={clearFilters}>
              <X size={14} aria-hidden="true" />
              {t("activities.noResults.clear")}
            </Button>
          ) : null}

          <div className={cn("filter-bar__count", "mono")}>
            {total} {total === 1 ? t("common.activity") : t("common.activities")}
          </div>
        </div>

        {activities.isError ? (
          <ErrorState
            message={activities.error instanceof Error ? activities.error.message : t("activities.error")}
            onRetry={() => void activities.refetch()}
          />
        ) : !activities.isLoading && items.length === 0 ? (
          hasFilters ? (
            <EmptyState
              icon={Search}
              title={t("activities.noResults.title")}
              description={t("activities.noResults.desc")}
              action={
                <Button variant="secondary" size="sm" onClick={clearFilters}>
                  {t("activities.noResults.clear")}
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={Upload}
              title={t("activities.empty.title")}
              description={t("activities.empty.desc")}
              action={
                <Link to="/imports" className="button button--primary button--md">
                  <Upload size={15} aria-hidden="true" />
                  {t("activities.import")}
                </Link>
              }
            />
          )
        ) : (
          <ActivityTable
            activities={items}
            total={total}
            pageIndex={pageIndex}
            pageSize={PAGE_SIZE}
            sort={sort}
            loading={activities.isLoading}
            onSortChange={(next) => {
              setSort(next);
              setPageIndex(0);
            }}
            onPageChange={setPageIndex}
          />
        )}
      </Card>
    </div>
  );
}
