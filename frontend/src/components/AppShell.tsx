import { useEffect, useRef, useState } from "react";
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  CalendarDays,
  Database,
  Dumbbell,
  FileText,
  Gauge,
  LayoutDashboard,
  Menu,
  Plus,
  RefreshCw,
  Settings,
  Stethoscope,
  TrendingUp,
  Upload,
  X,
  type LucideIcon,
} from "lucide-react";

import {
  useStartSync,
  useSyncStatus,
  useSystemStatus,
} from "@/api/queries";
import { cn } from "@/lib/cn";
import { formatDateTime, formatRelative } from "@/lib/format";
import { useI18n, type MessageKey } from "@/i18n";

type NavItem = {
  to:
    | "/"
    | "/performance"
    | "/progress"
    | "/calendar"
    | "/reports"
    | "/diagnostics"
    | "/training"
    | "/activities"
    | "/imports"
    | "/data"
    | "/settings";
  label: MessageKey;
  icon: LucideIcon;
  exact?: boolean;
};

const primaryNav: NavItem[] = [
  { to: "/", label: "nav.overview", icon: LayoutDashboard, exact: true },
  { to: "/performance", label: "nav.performance", icon: Gauge },
  { to: "/progress", label: "nav.progress", icon: TrendingUp },
  { to: "/calendar", label: "nav.calendar", icon: CalendarDays },
  { to: "/reports", label: "nav.reports", icon: FileText },
  { to: "/diagnostics", label: "nav.diagnostics", icon: Stethoscope },
  { to: "/training", label: "nav.training", icon: Dumbbell },
];

const libraryNav: NavItem[] = [
  { to: "/activities", label: "nav.activities", icon: Activity },
  { to: "/imports", label: "nav.imports", icon: Upload },
  { to: "/data", label: "nav.data", icon: Database },
];

function pageKey(pathname: string): MessageKey {
  if (pathname.startsWith("/activities")) return "nav.activities";
  if (pathname.startsWith("/imports")) return "nav.imports";
  if (pathname.startsWith("/data")) return "nav.data";
  if (pathname.startsWith("/settings")) return "nav.settings";
  if (pathname.startsWith("/performance")) return "nav.performance";
  if (pathname.startsWith("/progress")) return "nav.progress";
  if (pathname.startsWith("/calendar")) return "nav.calendar";
  if (pathname.startsWith("/reports")) return "nav.reports";
  if (pathname.startsWith("/diagnostics")) return "nav.diagnostics";
  if (pathname.startsWith("/training")) return "nav.training";
  return "nav.overview";
}

export function AppShell() {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const [menuOpen, setMenuOpen] = useState(false);
  const sync = useSyncStatus();
  const system = useSystemStatus();
  const startSync = useStartSync();
  const { locale, setLocale, t } = useI18n();
  const queryClient = useQueryClient();
  const wasRunning = useRef(false);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    const running = Boolean(sync.data?.running);
    if (wasRunning.current && !running) {
      void queryClient.invalidateQueries({ queryKey: ["activities"] });
      void queryClient.invalidateQueries({ queryKey: ["activity"] });
      void queryClient.invalidateQueries({ queryKey: ["summary"] });
      void queryClient.invalidateQueries({ queryKey: ["audit"] });
      void queryClient.invalidateQueries({ queryKey: ["system"] });
    }
    wasRunning.current = running;
  }, [sync.data?.running, queryClient]);

  const garminConfigured = sync.data?.garmin_configured ?? system.data?.garmin_configured ?? false;
  const running = Boolean(sync.data?.running);
  const lastRun = sync.data?.last_run;
  const version = system.data?.version ?? "0.1.0";

  const handleSync = () => {
    startSync.mutate("incremental");
  };

  return (
    <div className="app-shell">
      <div
        className={cn("sidebar-scrim", menuOpen && "is-visible")}
        onClick={() => setMenuOpen(false)}
        aria-hidden="true"
      />
      <aside className={cn("sidebar", menuOpen && "is-open")}>
        <div className="sidebar__head">
          <Link to="/" className="brand" aria-label="Run — inicio">
            <span className="brand__mark">R</span>
            <span className="brand__copy">
              <strong>RUN</strong>
              <small>Personal training intelligence</small>
            </span>
          </Link>
          <button
            type="button"
            className="icon-button sidebar__close"
            onClick={() => setMenuOpen(false)}
            aria-label={t("nav.close")}
          >
            <X size={19} aria-hidden="true" />
          </button>
        </div>

        <nav className="sidebar__nav" aria-label={t("nav.menu")}>
          <div className="nav-group">
            {primaryNav.map((item) => (
              <NavLink key={item.to} item={item} />
            ))}
          </div>
          <div className="nav-group">
            <span className="nav-group__label">{t("nav.library")}</span>
            {libraryNav.map((item) => (
              <NavLink key={item.to} item={item} />
            ))}
          </div>
        </nav>

        <div className="sidebar__foot">
          <div className="sidebar-status">
            <div className="sidebar-status__row">
              <span className={cn("status-dot", running && "status-dot--pulse")} />
              <strong>
                {running
                  ? t("sidebar.syncRunning")
                  : garminConfigured
                    ? t("sidebar.garminOn")
                    : t("sidebar.garminOff")}
              </strong>
            </div>
            <div className="sidebar-status__meta">
              <span>{t("sidebar.lastSync")}</span>
              <span>
                {lastRun?.finished_at
                  ? formatRelative(lastRun.finished_at, locale)
                  : t("sidebar.never")}
              </span>
            </div>
          </div>
          <Link to="/settings" className="nav-item nav-item--settings">
            <Settings size={18} aria-hidden="true" />
            <span>{t("nav.settings")}</span>
          </Link>
          <div className="sidebar__signature">
            <span className="mono">v{version}</span>
            <span>GPL-3.0</span>
            <span>{t("app.local")}</span>
          </div>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <div className="topbar__left">
            <button
              type="button"
              className="icon-button topbar__menu"
              onClick={() => setMenuOpen(true)}
              aria-label={t("topbar.openMenu")}
            >
              <Menu size={20} aria-hidden="true" />
            </button>
            <div className="topbar__context">
              <span className="topbar__section">{t(pageKey(pathname))}</span>
              <span className="topbar__date">
                {formatDateTime(new Date(), locale, {
                  weekday: "long",
                  day: "numeric",
                  month: "long",
                })}
              </span>
            </div>
          </div>

          <div className="topbar__right">
            <div className="locale-switch" role="group" aria-label={t("settings.preferences.language")}>
              <button
                type="button"
                className={cn(locale === "es" && "is-active")}
                onClick={() => setLocale("es")}
                aria-pressed={locale === "es"}
              >
                ES
              </button>
              <button
                type="button"
                className={cn(locale === "en" && "is-active")}
                onClick={() => setLocale("en")}
                aria-pressed={locale === "en"}
              >
                EN
              </button>
            </div>
            <Link to="/imports" className="button button--ghost button--sm topbar__import">
              <Plus size={15} aria-hidden="true" />
              <span>{t("topbar.import")}</span>
            </Link>
            <button
              type="button"
              className={cn("button button--primary button--sm topbar__sync", running && "is-running")}
              onClick={handleSync}
              disabled={!garminConfigured || running || startSync.isPending}
              title={
                !garminConfigured
                  ? t("topbar.syncUnavailable")
                  : startSync.error instanceof Error
                    ? startSync.error.message
                    : t("topbar.sync")
              }
            >
              <RefreshCw size={15} className={cn((running || startSync.isPending) && "spin")} aria-hidden="true" />
              <span>{running ? t("topbar.syncing") : t("topbar.sync")}</span>
            </button>
          </div>
        </header>

        <main className="page">
          <Outlet />
        </main>

        <footer className="app-footer">
          <span>{t("app.tagline")}</span>
          <span className="mono">v{version}</span>
        </footer>
      </div>
    </div>
  );
}

function NavLink({ item }: { item: NavItem }) {
  const { t } = useI18n();
  const Icon = item.icon;
  return (
    <Link
      to={item.to}
      activeOptions={{ exact: item.exact }}
      className="nav-item"
      activeProps={{ className: "nav-item is-active" }}
    >
      <Icon size={18} aria-hidden="true" />
      <span>{t(item.label)}</span>
      <span className="nav-item__indicator" aria-hidden="true" />
    </Link>
  );
}
