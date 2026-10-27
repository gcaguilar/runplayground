import type { ErrorComponentProps } from "@tanstack/react-router";
import { Link, createRootRoute, createRoute, createRouter } from "@tanstack/react-router";
import { RefreshCw } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { Button, ErrorState, Spinner } from "@/components/ui";
import { useAuthStatus } from "@/api/queries";
import { useI18n } from "@/i18n";
import { ActivitiesPage } from "@/pages/ActivitiesPage";
import { BackupPage } from "@/pages/BackupPage";
import { CalendarPage } from "@/pages/CalendarPage";
import { ActivityDetailPage } from "@/pages/ActivityDetailPage";
import { ComparePage } from "@/pages/ComparePage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DataQualityPage } from "@/pages/DataQualityPage";
import { DiagnosticsPage } from "@/pages/DiagnosticsPage";
import { ForecastPage } from "@/pages/ForecastPage";
import { ImportsPage } from "@/pages/ImportsPage";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { PerformancePage } from "@/pages/PerformancePage";
import { PlanPage } from "@/pages/PlanPage";
import { ProgressPage } from "@/pages/ProgressPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { RecoveryPage } from "@/pages/RecoveryPage";
import { TrackingPage } from "@/pages/TrackingPage";
import { TrainingPage } from "@/pages/TrainingPage";

function RootGate() {
  const auth = useAuthStatus();

  if (auth.isLoading) return <BootScreen />;
  if (auth.isError || !auth.data) {
    return <BootError onRetry={() => void auth.refetch()} />;
  }
  if (auth.data.auth_mode === "password" && !auth.data.authenticated) {
    return <LoginPage />;
  }
  return <AppShell />;
}

function BootScreen() {
  const { t } = useI18n();
  return (
    <div className="boot-screen">
      <span className="brand__mark brand__mark--xl">R</span>
      <Spinner label={t("boot.loading")} />
      <p>{t("boot.loading")}</p>
    </div>
  );
}

function BootError({ onRetry }: { onRetry: () => void }) {
  const { t } = useI18n();
  return (
    <div className="boot-screen">
      <span className="brand__mark brand__mark--xl">R</span>
      <h1>{t("boot.error")}</h1>
      <Button variant="secondary" size="md" onClick={onRetry}>
        <RefreshCw size={15} aria-hidden="true" />
        {t("common.retry")}
      </Button>
    </div>
  );
}

function RouteError({ error }: ErrorComponentProps) {
  const { t } = useI18n();
  return (
    <div className="page-stack">
      <ErrorState
        message={error instanceof Error ? error.message : t("error.desc")}
        onRetry={() => window.location.reload()}
      />
      <Link to="/" className="button button--secondary button--sm">
        {t("notFound.home")}
      </Link>
    </div>
  );
}

const rootRoute = createRootRoute({
  component: RootGate,
  notFoundComponent: NotFoundPage,
  errorComponent: RouteError,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: DashboardPage,
});

const performanceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/performance",
  component: PerformancePage,
});

const forecastRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/forecast",
  component: ForecastPage,
});

const progressRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/progress",
  component: ProgressPage,
});

const trackingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tracking",
  component: TrackingPage,
});

const recoveryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/recovery",
  component: RecoveryPage,
});

const calendarRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/calendar",
  component: CalendarPage,
});

const reportsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/reports",
  component: ReportsPage,
});

const diagnosticsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/diagnostics",
  component: DiagnosticsPage,
});

const trainingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/training",
  component: TrainingPage,
});

const planRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/plan",
  component: PlanPage,
});

const activitiesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/activities",
  component: ActivitiesPage,
});

const activityDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/activities/$activityId",
  component: ActivityDetailPage,
});

const compareRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/compare",
  validateSearch: (search: Record<string, unknown>) => {
    const raw = search.left;
    const value = typeof raw === "number" ? raw : typeof raw === "string" ? Number(raw) : NaN;
    return { left: Number.isFinite(value) && value > 0 ? value : undefined };
  },
  component: ComparePage,
});

const importsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/imports",
  component: ImportsPage,
});

const dataRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/data",
  component: DataQualityPage,
});

const backupRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/backup",
  component: BackupPage,
});

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings",
  component: SettingsPage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  performanceRoute,
  forecastRoute,
  progressRoute,
  trackingRoute,
  recoveryRoute,
  calendarRoute,
  reportsRoute,
  diagnosticsRoute,
  trainingRoute,
  planRoute,
  activitiesRoute,
  activityDetailRoute,
  compareRoute,
  importsRoute,
  dataRoute,
  backupRoute,
  settingsRoute,
]);

export const router = createRouter({
  routeTree,
  defaultPreload: "intent",
  defaultPreloadStaleTime: 30_000,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
