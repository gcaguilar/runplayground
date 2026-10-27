import { useEffect, useRef, useState } from "react";
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Archive,
  ArrowLeftRight,
  CalendarDays,
  ClipboardList,
  Database,
  Dumbbell,
  FileText,
  Gauge,
  HeartPulse,
  History,
  LayoutDashboard,
  Menu,
  Plus,
  RefreshCw,
  Settings,
  Sparkles,
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
import { ToastStack } from "@/components/Notifications";
import { cn } from "@/lib/cn";
import { formatDateTime, formatRelative } from "@/lib/format";
import { notifyToast } from "@/lib/toast";
import { useI18n, type MessageKey } from "@/i18n";

type NavItem = {
  to:
    | "/"
    | "/performance"
    | "/forecast"
    | "/progress"
    | "/tracking"
    | "/recovery"
    | "/calendar"
    | "/reports"
    | "/diagnostics"
    | "/training"
    | "/plan"
    | "/activities"
    | "/compare"
    | "/imports"
    | "/data"
    | "/backup"
    | "/settings";
  label: MessageKey;
  icon: LucideIcon;
  exact?: boolean;
};

const primaryNav: NavItem[] = [
  { to: "/", label: "nav.overview", icon: LayoutDashboard, exact: true },
  { to: "/performance", label: "nav.performance", icon: Gauge },
  { to: "/forecast", label: "nav.forecast", icon: Sparkles },
  { to: "/progress", label: "nav.progress", icon: TrendingUp },
  { to: "/tracking", label: "nav.tracking", icon: History },
  { to: "/recovery", label: "nav.recovery", icon: HeartPulse },
  { to: "/calendar", label: "nav.calendar", icon: CalendarDays },
  { to: "/reports", label: "nav.reports", icon: FileText },
  { to: "/diagnostics", label: "nav.diagnostics", icon: Stethoscope },
  { to: "/training", label: "nav.training", icon: Dumbbell },
  { to: "/plan", label: "nav.plan", icon: ClipboardList },
];

const libraryNav: NavItem[] = [
  { to: "/activities", label: "nav.activities", icon: Activity },
  { to: "/compare", label: "nav.compare", icon: ArrowLeftRight },
  { to: "/imports", label: "nav.imports", icon: Upload },
  { to: "/data", label: "nav.data", icon: Database },
  { to: "/backup", label: "nav.backup", icon: Archive },
];

function pageKey(pathname: string): MessageKey {
  if (pathname.startsWith("/activities")) return "nav.activities";
  if (pathname.startsWith("/compare")) return "nav.compare";
  if (pathname.startsWith("/imports")) return "nav.imports";
  if (pathname.startsWith("/data")) return "nav.data";
  if (pathname.startsWith("/backup")) return "nav.backup";
  if (pathname.startsWith("/settings")) return "nav.settings";
  if (pathname.startsWith("/performance")) return "nav.performance";
  if (pathname.startsWith("/forecast")) return "nav.forecast";
  if (pathname.startsWith("/progress")) return "nav.progress";
  if (pathname.startsWith("/tracking")) return "nav.tracking";
  if (pathname.startsWith("/recovery")) return "nav.recovery";
  if (pathname.startsWith("/calendar")) return "nav.calendar";
  if (pathname.startsWith("/reports")) return "nav.reports";
  if (pathname.startsWith("/diagnostics")) return "nav.diagnostics";
  if (pathname.startsWith("/training")) return "nav.training";
  if (pathname.startsWith("/plan")) return "nav.plan";
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
  const lastSyncSeen = useRef<{ id: number; status: string } | null>(readLastSyncSeen());
  const mainRef = useRef<HTMLElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const pathnameRef = useRef(pathname);
  const menuOpenedAt = useRef(pathname);
  const firstRoute = useRef(true);
  pathnameRef.current = pathname;

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  // Move focus to the page landmark after client-side navigation. The main
  // element keeps tabIndex={-1} so it can receive programmatic focus without
  // entering the normal tab order.
  useEffect(() => {
    if (firstRoute.current) {
      firstRoute.current = false;
      return;
    }
    mainRef.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [pathname]);

  // The off-canvas navigation behaves as a modal dialog on small screens:
  // focus moves inside, Escape closes it and focus returns to the trigger.
  useEffect(() => {
    if (!menuOpen) return;
    menuOpenedAt.current = pathnameRef.current;
    const previous =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    // Wait one frame so the sidebar is visible before moving focus into it.
    const frame = window.requestAnimationFrame(() => closeButtonRef.current?.focus());

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setMenuOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = sidebarRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", onKeyDown);
      // Only return focus when the menu closed in place (Escape, scrim or the
      // close button). A navigation moves focus to the new page instead.
      if (menuOpenedAt.current === pathnameRef.current) previous?.focus();
    };
  }, [menuOpen]);

  useEffect(() => {
    const running = Boolean(sync.data?.running);
    if (wasRunning.current && !running) {
      void queryClient.invalidateQueries({ queryKey: ["activities"] });
      void queryClient.invalidateQueries({ queryKey: ["activity"] });
      void queryClient.invalidateQueries({ queryKey: ["summary"] });
      void queryClient.invalidateQueries({ queryKey: ["audit"] });
      void queryClient.invalidateQueries({ queryKey: ["system"] });
      void queryClient.invalidateQueries({ queryKey: ["performance"] });
      void queryClient.invalidateQueries({ queryKey: ["diagnostics"] });
      void queryClient.invalidateQueries({ queryKey: ["training"] });
      void queryClient.invalidateQueries({ queryKey: ["progress"] });
      void queryClient.invalidateQueries({ queryKey: ["calendar"] });
      void queryClient.invalidateQueries({ queryKey: ["reports"] });
      void queryClient.invalidateQueries({ queryKey: ["forecast"] });
      void queryClient.invalidateQueries({ queryKey: ["tracking"] });
      void queryClient.invalidateQueries({ queryKey: ["adherence"] });
      void queryClient.invalidateQueries({ queryKey: ["recovery"] });
      void queryClient.invalidateQueries({ queryKey: ["briefing"] });
      void queryClient.invalidateQueries({ queryKey: ["comparables"] });
    }
    wasRunning.current = running;
  }, [sync.data?.running, queryClient]);

  useEffect(() => {
    const run = sync.data?.last_run;
    if (!run) return;
    const current = { id: run.id, status: run.status };
    const previous = lastSyncSeen.current;
    if (previous && previous.id === current.id && previous.status === current.status) return;
    if (previous && previous.id > current.id) return;
    writeLastSyncSeen(current);
    lastSyncSeen.current = current;
    // The first observed run is a baseline, not a fresh notification.
    if (!previous) return;
    if (!["success", "partial", "error"].includes(run.status)) return;

    const failed = run.status === "error";
    notifyToast({
      tone: failed ? "danger" : run.status === "partial" ? "warning" : "success",
      titleKey: failed ? "toast.sync.failedTitle" : "toast.sync.title",
      messageKey:
        run.status === "success"
          ? "toast.sync.success"
          : run.status === "partial"
            ? "toast.sync.partial"
            : "toast.sync.error",
      values: {
        created: run.activities_created,
        updated: run.activities_updated,
        skipped: run.activities_skipped,
        errors: run.errors_count,
      },
      href: failed ? "/settings" : "/data",
      linkKey: failed ? "toast.sync.openSettings" : "toast.sync.openData",
    });
  }, [sync.data?.last_run]);

  const garminConfigured = sync.data?.garmin_configured ?? system.data?.garmin_configured ?? false;
  const running = Boolean(sync.data?.running);
  const lastRun = sync.data?.last_run;
  const version = system.data?.version ?? "0.1.0";

  const handleSync = () => {
    startSync.mutate("incremental");
  };

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        {t("a11y.skipToContent")}
      </a>
      <div
        className={cn("sidebar-scrim", menuOpen && "is-visible")}
        onClick={() => setMenuOpen(false)}
        aria-hidden="true"
      />
      <aside
        id="app-sidebar"
        ref={sidebarRef}
        className={cn("sidebar", menuOpen && "is-open")}
        role={menuOpen ? "dialog" : undefined}
        aria-modal={menuOpen ? true : undefined}
        aria-label={menuOpen ? t("nav.menu") : undefined}
      >
        <div className="sidebar__head">
          <Link to="/" className="brand" aria-label="Run — inicio">
            <span className="brand__mark">R</span>
            <span className="brand__copy">
              <strong>RUN</strong>
              <small>Personal training intelligence</small>
            </span>
          </Link>
          <button
            ref={closeButtonRef}
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
              ref={menuButtonRef}
              type="button"
              className="icon-button topbar__menu"
              onClick={() => setMenuOpen(true)}
              aria-label={t("topbar.openMenu")}
              aria-expanded={menuOpen}
              aria-controls="app-sidebar"
              aria-haspopup="dialog"
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

        <main id="main-content" ref={mainRef} className="page" tabIndex={-1}>
          <Outlet />
        </main>

        <footer className="app-footer">
          <span>{t("app.tagline")}</span>
          <span className="mono">v{version}</span>
        </footer>
      </div>
      <ToastStack />
    </div>
  );
}

const LAST_SYNC_KEY = "run.sync.lastSeen";

function readLastSyncSeen(): { id: number; status: string } | null {
  try {
    const raw = localStorage.getItem(LAST_SYNC_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { id?: unknown; status?: unknown };
    if (typeof parsed.id !== "number" || typeof parsed.status !== "string") return null;
    return { id: parsed.id, status: parsed.status };
  } catch {
    return null;
  }
}

function writeLastSyncSeen(value: { id: number; status: string }): void {
  try {
    localStorage.setItem(LAST_SYNC_KEY, JSON.stringify(value));
  } catch {
    // Private browsing or a full quota must not break the shell.
  }
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
