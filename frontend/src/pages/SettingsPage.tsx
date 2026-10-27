import { Link } from "@tanstack/react-router";
import {
  Activity,
  CheckCircle2,
  Database,
  HardDrive,
  Info,
  KeyRound,
  Languages,
  LogOut,
  RefreshCw,
  Ruler,
  ShieldCheck,
  SlidersHorizontal,
  TriangleAlert,
} from "lucide-react";

import { useAuthStatus, useLogout, useStartSync, useSyncStatus, useSystemStatus } from "@/api/queries";
import { AnalysisSettingsCard } from "@/components/AnalysisSettingsCard";
import {
  Badge,
  Button,
  Card,
  DefinitionRow,
  ErrorState,
  PageHeader,
  SectionHeading,
  Skeleton,
} from "@/components/ui";
import { useI18n, type Locale, type MessageKey, type Units } from "@/i18n";
import { cn } from "@/lib/cn";
import {
  formatBytes,
  formatDateTime,
  formatRelative,
} from "@/lib/format";

export function SettingsPage() {
  const { locale, units, setLocale, setUnits, t } = useI18n();
  const system = useSystemStatus();
  const sync = useSyncStatus();
  const auth = useAuthStatus();
  const startSync = useStartSync();
  const logout = useLogout();

  if (system.isError) {
    return (
      <div className="page-stack">
        <PageHeader title={t("settings.title")} description={t("settings.subtitle")} />
        <ErrorState
          message={system.error instanceof Error ? system.error.message : undefined}
          onRetry={() => void system.refetch()}
        />
      </div>
    );
  }

  const data = system.data;
  const running = Boolean(sync.data?.running);
  const lastRun = sync.data?.last_run;
  const token = data?.garmin_token;
  const passwordMode = auth.data?.auth_mode === "password";

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={t("nav.settings")}
        title={t("settings.title")}
        description={t("settings.subtitle")}
      />

      {!data ? (
        <SettingsSkeleton />
      ) : (
        <div className="settings-grid">
          <section className="settings-main">
            <AnalysisSettingsCard />

            <Card className="panel">
              <SectionHeading
                title={t("settings.connection.title")}
                icon={KeyRound}
                action={
                  <Badge tone={data.garmin_configured ? "success" : "warning"} dot>
                    {data.garmin_configured
                      ? t("settings.connection.connected")
                      : t("settings.connection.missing")}
                  </Badge>
                }
              />
              <p className="settings-intro">{t("settings.connection.description")}</p>

              <div className="settings-definitions">
                <DefinitionRow
                  label={t("settings.connection.key")}
                  value={data.garmin_configured ? t("settings.connection.connected") : t("settings.connection.missing")}
                />
                {data.garmin_key_fingerprint ? (
                  <DefinitionRow
                    label={t("settings.connection.fingerprint")}
                    value={<code className="mono">{data.garmin_key_fingerprint}</code>}
                  />
                ) : null}
                <DefinitionRow
                  label={t("settings.connection.token")}
                  value={
                    token?.cached && token.expires_at
                      ? t("settings.connection.expires", {
                          time: formatRelative(new Date(token.expires_at * 1000).toISOString(), locale),
                        })
                      : t("settings.connection.noToken")
                  }
                />
              </div>

              {!data.garmin_configured ? (
                <div className="callout callout--warning">
                  <TriangleAlert size={18} aria-hidden="true" />
                  <div>
                    <strong>{t("settings.connection.howTo")}</strong>
                    <ol className="step-list">
                      <li>{t("settings.connection.step1")}</li>
                      <li>{t("settings.connection.step2")}</li>
                      <li>{t("settings.connection.step3")}</li>
                    </ol>
                    <pre className="code-block">GARMIN_PERSONAL_API_KEY=tu_clave</pre>
                  </div>
                </div>
              ) : null}

              <div className="callout callout--info">
                <Info size={17} aria-hidden="true" />
                <p>{t("settings.connection.limitNote")}</p>
              </div>
            </Card>

            <Card className="panel">
              <SectionHeading
                title={t("settings.sync.title")}
                icon={RefreshCw}
                action={
                  <Badge tone={running ? "info" : data.sync_interval_hours > 0 ? "success" : "neutral"} dot>
                    {running
                      ? t("settings.sync.running")
                      : data.sync_interval_hours > 0
                        ? t("settings.sync.auto", { hours: data.sync_interval_hours })
                        : t("settings.sync.disabled")}
                  </Badge>
                }
              />

              {!data.garmin_configured ? (
                <p className="muted-copy">{t("settings.sync.noKey")}</p>
              ) : (
                <>
                  <div className="settings-definitions">
                    <DefinitionRow
                      label={t("settings.sync.lastRun")}
                      value={
                        lastRun?.finished_at
                          ? formatDateTime(lastRun.finished_at, locale)
                          : t("settings.sync.never")
                      }
                    />
                    <DefinitionRow
                      label={t("settings.sync.next")}
                      value={
                        sync.data?.next_sync_at
                          ? formatDateTime(sync.data.next_sync_at, locale)
                          : t("settings.sync.disabled")
                      }
                    />
                    {lastRun ? (
                      <>
                        <DefinitionRow
                          label={t("dashboard.metric.activities")}
                          value={`${lastRun.activities_created} + · ${lastRun.activities_updated} ↻ · ${lastRun.activities_skipped} –`}
                        />
                        <DefinitionRow
                          label={t("settings.sync.files")}
                          value={
                            <Badge
                              tone={
                                lastRun.status === "success"
                                  ? "success"
                                  : lastRun.status === "error"
                                    ? "danger"
                                    : "warning"
                              }
                            >
                              {syncStatusLabel(lastRun.status, t)}
                            </Badge>
                          }
                        />
                      </>
                    ) : null}
                  </div>

                  {lastRun?.message ? <p className="settings-message mono">{lastRun.message}</p> : null}

                  <div className="form-actions settings-sync-actions">
                    <Button
                      variant="primary"
                      size="md"
                      loading={startSync.isPending || running}
                      disabled={running}
                      onClick={() => startSync.mutate("incremental")}
                    >
                      <RefreshCw size={15} className={cn(running && "spin")} aria-hidden="true" />
                      {running ? t("settings.sync.running") : t("settings.sync.incremental")}
                    </Button>
                    <Button
                      variant="secondary"
                      size="md"
                      disabled={running || startSync.isPending}
                      onClick={() => startSync.mutate("backfill")}
                    >
                      {t("settings.sync.backfill")}
                    </Button>
                  </div>
                  <p className="settings-hint">{t("settings.sync.backfillHint", { pages: 100 })}</p>
                  {startSync.isError ? (
                    <p className="form-error" role="alert">
                      {startSync.error instanceof Error
                        ? startSync.error.message
                        : t("settings.sync.error")}
                    </p>
                  ) : startSync.isSuccess ? (
                    <p className="form-success">
                      <CheckCircle2 size={14} aria-hidden="true" />
                      {t("settings.sync.started")}
                    </p>
                  ) : null}
                </>
              )}
            </Card>

            <Card className="panel">
              <SectionHeading title={t("settings.storage.title")} icon={HardDrive} />
              <div className="settings-definitions">
                <DefinitionRow
                  label={t("settings.storage.dataDir")}
                  value={<code className="mono">{data.data_dir}</code>}
                />
                <DefinitionRow
                  label={t("settings.storage.databaseSize")}
                  value={`${formatBytes(data.database_size_bytes)} · SQLite`}
                />
                <DefinitionRow
                  label={t("settings.storage.activities")}
                  value={data.activity_count}
                />
                <DefinitionRow
                  label={t("settings.storage.rawFiles")}
                  value={data.raw_file_count}
                />
                <DefinitionRow
                  label={t("settings.storage.formats")}
                  value={data.supported_formats.map((format) => format.toUpperCase()).join(" · ")}
                />
              </div>
            </Card>
          </section>

          <aside className="settings-rail">
            <Card className="panel">
              <SectionHeading title={t("settings.security.title")} icon={ShieldCheck} />
              <div className="settings-definitions">
                <DefinitionRow
                  label={t("settings.security.authMode")}
                  value={
                    <Badge tone={passwordMode ? "success" : "warning"} dot>
                      {passwordMode ? t("settings.security.password") : t("settings.security.none")}
                    </Badge>
                  }
                />
              </div>
              <p className={cn("settings-note", !passwordMode && "settings-note--warning")}>
                {passwordMode ? t("settings.security.passwordNote") : t("settings.security.warning")}
              </p>
              <p className="settings-note">{t("settings.security.serverNote")}</p>
              {passwordMode ? (
                <Button
                  variant="secondary"
                  size="sm"
                  loading={logout.isPending}
                  onClick={() => logout.mutate()}
                  className="settings-logout"
                >
                  <LogOut size={14} aria-hidden="true" />
                  {t("settings.logout")}
                </Button>
              ) : null}
            </Card>

            <Card className="panel">
              <SectionHeading title={t("settings.preferences.title")} icon={SlidersHorizontal} />
              <div className="preference-group">
                <span className="preference-group__label">
                  <Languages size={15} aria-hidden="true" />
                  {t("settings.preferences.language")}
                </span>
                <PreferenceToggle<Locale>
                  options={[
                    { value: "es", label: "Español" },
                    { value: "en", label: "English" },
                  ]}
                  value={locale}
                  onChange={setLocale}
                />
              </div>
              <div className="preference-group">
                <span className="preference-group__label">
                  <Ruler size={15} aria-hidden="true" />
                  {t("settings.preferences.units")}
                </span>
                <PreferenceToggle<Units>
                  options={[
                    { value: "metric", label: t("settings.preferences.metric") },
                    { value: "imperial", label: t("settings.preferences.imperial") },
                  ]}
                  value={units}
                  onChange={setUnits}
                />
              </div>
              <p className="settings-hint">{t("settings.preferences.saved")}</p>
            </Card>

            <Card className="panel about-card">
              <SectionHeading title={t("settings.about.title")} icon={Info} />
              <p className="settings-intro">{t("settings.about.description")}</p>
              <div className="settings-definitions">
                <DefinitionRow label={t("settings.about.version")} value={<span className="mono">v{data.version}</span>} />
                <DefinitionRow label={t("settings.about.license")} value="GPL-3.0" />
              </div>
              <p className="settings-hint">{t("settings.about.unofficial")}</p>
              <div className="about-links">
                <Link to="/data" className="text-link">
                  <Database size={13} aria-hidden="true" />
                  {t("data.title")}
                </Link>
                <Link to="/activities" className="text-link">
                  <Activity size={13} aria-hidden="true" />
                  {t("nav.activities")}
                </Link>
              </div>
            </Card>
          </aside>
        </div>
      )}
    </div>
  );
}

function PreferenceToggle<T extends string>({
  options,
  value,
  onChange,
}: {
  options: Array<{ value: T; label: string }>;
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="preference-toggle" role="group">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={cn(option.value === value && "is-active")}
          onClick={() => onChange(option.value)}
          aria-pressed={option.value === value}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function SettingsSkeleton() {
  return (
    <div className="settings-grid">
      <Card className="panel">
        <Skeleton className="skeleton--block" />
      </Card>
      <Card className="panel">
        <Skeleton className="skeleton--block" />
      </Card>
    </div>
  );
}

function syncStatusLabel(status: string, t: (key: MessageKey) => string): string {
  const known: Record<string, MessageKey> = {
    success: "sync.status.success",
    partial: "sync.status.partial",
    error: "sync.status.error",
    running: "sync.status.running",
    interrupted: "sync.status.interrupted",
  };
  return known[status] ? t(known[status]) : status;
}
