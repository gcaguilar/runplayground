import { useRef, useState } from "react";
import {
  Archive,
  CheckCircle2,
  Clock3,
  Database,
  Download,
  FileArchive,
  HardDrive,
  Info,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Trash2,
  TriangleAlert,
  UploadCloud,
  XCircle,
} from "lucide-react";

import type { BackupManifest, BackupValidation } from "@/api/client";
import { api } from "@/api/client";
import {
  useBackupStatus,
  useCancelPendingRestore,
  useStageRestore,
  useValidateBackup,
} from "@/api/queries";
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
import { useI18n, type Locale, type MessageKey } from "@/i18n";
import { cn } from "@/lib/cn";
import { formatBytes, formatDateTime } from "@/lib/format";
import { notifyToast } from "@/lib/toast";

export function BackupPage() {
  const { locale, t } = useI18n();
  const status = useBackupStatus();
  const validate = useValidateBackup();
  const stage = useStageRestore();
  const cancel = useCancelPendingRestore();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [validation, setValidation] = useState<BackupValidation | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [dragging, setDragging] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const pending = status.data?.pending ?? null;
  const blocked = Boolean(status.data?.sync_running || status.data?.active_ingest);
  const maxRestoreBytes = (status.data?.max_restore_mb ?? 1024) * 1024 * 1024;
  const canRestore =
    Boolean(validation?.valid) &&
    Boolean(file) &&
    !pending &&
    !blocked &&
    confirmText === "RESTORE" &&
    !stage.isPending;

  const chooseFile = (incoming: File | undefined) => {
    if (!incoming) return;
    setProblem(null);
    setValidation(null);
    setConfirmText("");
    if (!incoming.name.toLowerCase().endsWith(".zip")) {
      const message = t("backup.restore.notZip");
      setProblem(message);
      setFile(null);
      notifyToast({ tone: "danger", titleKey: "toast.backup.invalid", message });
      return;
    }
    if (incoming.size > maxRestoreBytes) {
      const message = t("backup.restore.tooBig", {
        size: formatBytes(maxRestoreBytes),
      });
      setProblem(message);
      setFile(null);
      notifyToast({ tone: "danger", titleKey: "toast.backup.invalid", message });
      return;
    }
    setFile(incoming);
    validate.mutate(incoming, {
      onSuccess: (result) => {
        setValidation(result);
        if (!result.valid) {
          notifyToast({
            tone: "danger",
            titleKey: "toast.backup.invalid",
            messageKey: "toast.backup.invalidBody",
          });
        }
      },
      onError: (error) => {
        const message = error instanceof Error ? error.message : t("backup.restore.error");
        setProblem(message);
        notifyToast({ tone: "danger", titleKey: "toast.backup.invalid", message });
      },
    });
  };

  const download = async () => {
    setDownloading(true);
    try {
      const { blob, filename } = await api.exportBackup();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      notifyToast({
        tone: "success",
        titleKey: "toast.backup.exported",
        message: filename,
      });
    } catch (error) {
      notifyToast({
        tone: "danger",
        titleKey: "toast.backup.exportError",
        message: error instanceof Error ? error.message : undefined,
      });
    } finally {
      setDownloading(false);
    }
  };

  const restore = () => {
    if (!file || !canRestore) return;
    stage.mutate(file, {
      onSuccess: () => {
        setFile(null);
        setValidation(null);
        setConfirmText("");
        notifyToast({
          tone: "success",
          titleKey: "toast.restore.staged",
          messageKey: "toast.restore.restart",
          durationMs: 10_000,
        });
      },
      onError: (error) => {
        notifyToast({
          tone: "danger",
          titleKey: "toast.restore.error",
          message: error instanceof Error ? error.message : undefined,
        });
      },
    });
  };

  const cancelPending = () => {
    cancel.mutate(undefined, {
      onSuccess: () => {
        notifyToast({
          tone: "success",
          titleKey: "toast.restore.cancelled",
        });
      },
      onError: (error) => {
        notifyToast({
          tone: "danger",
          titleKey: "toast.restore.cancelError",
          message: error instanceof Error ? error.message : undefined,
        });
      },
    });
  };

  const last = status.data?.last_restore ?? null;
  const lastManifest = (last?.manifest ?? null) as BackupManifest | null;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={t("nav.library")}
        title={t("backup.title")}
        description={t("backup.subtitle")}
      />

      {status.isError ? (
        <ErrorState
          message={status.error instanceof Error ? status.error.message : undefined}
          onRetry={() => void status.refetch()}
        />
      ) : null}

      <div className="backup-layout">
        <div className="backup-main">
          <Card className="panel">
            <SectionHeading
              title={t("backup.export.title")}
              subtitle={t("backup.export.subtitle")}
              icon={Archive}
              action={
                <Badge tone="info">
                  {t("backup.export.limit", {
                    size: formatBytes((status.data?.max_backup_mb ?? 4096) * 1024 * 1024),
                  })}
                </Badge>
              }
            />
            <p className="settings-intro">{t("backup.export.description")}</p>
            <ul className="backup-checklist">
              <li>
                <Database size={15} aria-hidden="true" />
                {t("backup.export.point.database")}
              </li>
              <li>
                <FileArchive size={15} aria-hidden="true" />
                {t("backup.export.point.raw")}
              </li>
              <li>
                <CheckCircle2 size={15} aria-hidden="true" />
                {t("backup.export.point.checksums")}
              </li>
            </ul>
            <div className="form-actions">
              <Button
                variant="primary"
                size="md"
                loading={downloading}
                onClick={() => void download()}
              >
                <Download size={16} aria-hidden="true" />
                {downloading ? t("backup.export.downloading") : t("backup.export.button")}
              </Button>
            </div>
            <p className="settings-hint">{t("backup.export.hint")}</p>
          </Card>

          {pending ? (
            <Card className="panel backup-pending">
              <SectionHeading
                title={t("backup.pending.title")}
                subtitle={t("backup.pending.subtitle")}
                icon={Clock3}
                action={<Badge tone="warning" dot>{t("backup.pending.badge")}</Badge>}
              />
              <div className="settings-definitions">
                <DefinitionRow label={t("backup.pending.file")} value={pending.original_filename} />
                <DefinitionRow
                  label={t("backup.pending.stagedAt")}
                  value={formatDateTime(pending.staged_at, locale)}
                />
                <DefinitionRow
                  label={t("backup.pending.archive")}
                  value={formatBytes(pending.archive_size_bytes)}
                />
                {pending.manifest ? (
                  <>
                    <DefinitionRow
                      label={t("backup.pending.version")}
                      value={`v${pending.manifest.app_version}`}
                    />
                    <DefinitionRow
                      label={t("backup.pending.createdAt")}
                      value={formatDateTime(pending.manifest.created_at, locale)}
                    />
                    <DefinitionRow
                      label={t("backup.pending.activities")}
                      value={pending.manifest.counts?.activities ?? 0}
                    />
                  </>
                ) : null}
              </div>
              <div className="callout callout--warning">
                <TriangleAlert size={18} aria-hidden="true" />
                <div>
                  <strong>{t("backup.pending.restartTitle")}</strong>
                  <p>{t("backup.pending.restartBody")}</p>
                </div>
              </div>
              <div className="form-actions">
                <Button
                  variant="danger"
                  size="md"
                  loading={cancel.isPending}
                  onClick={cancelPending}
                >
                  <Trash2 size={15} aria-hidden="true" />
                  {t("backup.pending.cancel")}
                </Button>
              </div>
            </Card>
          ) : (
            <Card className="panel">
              <SectionHeading
                title={t("backup.restore.title")}
                subtitle={t("backup.restore.subtitle")}
                icon={RotateCcw}
              />

              {blocked ? (
                <div className="callout callout--warning">
                  <TriangleAlert size={18} aria-hidden="true" />
                  <p>{t("backup.restore.blocked")}</p>
                </div>
              ) : null}

              <div
                className={cn(
                  "dropzone",
                  dragging && "is-dragging",
                  validate.isPending && "is-busy",
                )}
                onDragOver={(event) => {
                  event.preventDefault();
                  if (!validate.isPending) setDragging(true);
                }}
                onDragLeave={(event) => {
                  if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
                  setDragging(false);
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  setDragging(false);
                  if (!validate.isPending) chooseFile(event.dataTransfer.files?.[0]);
                }}
                onClick={() => {
                  if (!validate.isPending) inputRef.current?.click();
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    inputRef.current?.click();
                  }
                }}
                role="button"
                tabIndex={0}
                aria-label={t("backup.restore.drop")}
              >
                <span className="dropzone__icon">
                  <UploadCloud size={28} aria-hidden="true" />
                </span>
                <strong>
                  {validate.isPending ? t("backup.restore.validating") : t("backup.restore.drop")}
                </strong>
                <p>{t("backup.restore.dropHint")}</p>
                <span className="dropzone__hint">
                  {t("backup.restore.limit", { size: formatBytes(maxRestoreBytes) })}
                </span>
                <Button variant="secondary" size="sm" tabIndex={-1}>
                  <FileArchive size={15} aria-hidden="true" />
                  {t("backup.restore.choose")}
                </Button>
                <input
                  ref={inputRef}
                  type="file"
                  accept=".zip,application/zip"
                  className="visually-hidden"
                  onChange={(event) => {
                    chooseFile(event.target.files?.[0]);
                    event.target.value = "";
                  }}
                />
              </div>

              {problem ? (
                <ul className="problem-list" role="alert">
                  <li>
                    <TriangleAlert size={14} aria-hidden="true" />
                    {problem}
                  </li>
                </ul>
              ) : null}

              {file && validation ? (
                <ValidationCard
                  file={file}
                  validation={validation}
                  locale={locale}
                />
              ) : null}

              {validation?.valid && file ? (
                <div className="backup-confirm">
                  <label htmlFor="restore-confirm">{t("backup.restore.confirmLabel")}</label>
                  <input
                    id="restore-confirm"
                    type="text"
                    value={confirmText}
                    autoComplete="off"
                    placeholder="RESTORE"
                    onChange={(event) => setConfirmText(event.target.value)}
                  />
                  <p className="settings-hint">{t("backup.restore.confirmHint")}</p>
                  <Button
                    variant="danger"
                    size="md"
                    loading={stage.isPending}
                    disabled={!canRestore}
                    onClick={restore}
                  >
                    <RotateCcw size={15} aria-hidden="true" />
                    {t("backup.restore.button")}
                  </Button>
                </div>
              ) : null}

              <p className="settings-hint">{t("backup.restore.noHotRestore")}</p>
            </Card>
          )}

          {last ? (
            <Card className="panel">
              <SectionHeading title={t("backup.last.title")} icon={RefreshCw} />
              <div className="settings-definitions">
                <DefinitionRow
                  label={t("backup.last.appliedAt")}
                  value={
                    typeof last.applied_at === "string"
                      ? formatDateTime(last.applied_at, locale)
                      : t("common.unknown")
                  }
                />
                <DefinitionRow
                  label={t("backup.last.version")}
                  value={lastManifest ? `v${lastManifest.app_version}` : t("common.unknown")}
                />
                <DefinitionRow
                  label={t("backup.last.revision")}
                  value={lastManifest?.alembic_revision ?? t("common.unknown")}
                />
                <DefinitionRow
                  label={t("backup.last.file")}
                  value={
                    typeof last.original_filename === "string"
                      ? last.original_filename
                      : t("common.unknown")
                  }
                />
                <DefinitionRow
                  label={t("backup.last.preRestore")}
                  value={
                    typeof last.pre_restore_database === "string" ? (
                      <code className="mono">{last.pre_restore_database}</code>
                    ) : (
                      t("common.unknown")
                    )
                  }
                />
              </div>
            </Card>
          ) : null}
        </div>

        <aside className="backup-rail">
          <Card className="panel note-card">
            <span className="note-card__icon">
              <ShieldCheck size={18} aria-hidden="true" />
            </span>
            <h2>{t("backup.safety.title")}</h2>
            <p>{t("backup.safety.body")}</p>
            <ul className="backup-checklist backup-checklist--compact">
              <li>
                <CheckCircle2 size={14} aria-hidden="true" />
                {t("backup.safety.noSecrets")}
              </li>
              <li>
                <CheckCircle2 size={14} aria-hidden="true" />
                {t("backup.safety.noHotRestore")}
              </li>
              <li>
                <CheckCircle2 size={14} aria-hidden="true" />
                {t("backup.safety.previous")}
              </li>
            </ul>
          </Card>

          <Card className="panel">
            <SectionHeading title={t("backup.status.title")} icon={HardDrive} />
            {status.isLoading || !status.data ? (
              <div className="backup-status-lines">
                <Skeleton className="skeleton--line" />
                <Skeleton className="skeleton--line skeleton--short" />
                <Skeleton className="skeleton--line" />
              </div>
            ) : (
              <div className="settings-definitions">
                <DefinitionRow
                  label={t("backup.status.dataDir")}
                  value={<code className="mono">{status.data.data_dir}</code>}
                />
                <DefinitionRow
                  label={t("backup.status.database")}
                  value={status.data.database_revision ?? t("common.unknown")}
                />
                <DefinitionRow
                  label={t("backup.status.head")}
                  value={status.data.head_revision ?? t("common.unknown")}
                />
                <DefinitionRow
                  label={t("backup.status.maxRestore")}
                  value={formatBytes((status.data.max_restore_mb ?? 0) * 1024 * 1024)}
                />
                <DefinitionRow
                  label={t("backup.status.pending")}
                  value={
                    status.data.pending ? (
                      <Badge tone="warning" dot>{t("backup.status.pendingYes")}</Badge>
                    ) : (
                      <Badge tone="success" dot>{t("backup.status.pendingNo")}</Badge>
                    )
                  }
                />
              </div>
            )}
          </Card>

          <Card className="panel">
            <div className="backup-note">
              <Info size={17} aria-hidden="true" />
              <p>{t("backup.note")}</p>
            </div>
          </Card>
        </aside>
      </div>
    </div>
  );
}

function ValidationCard({
  file,
  validation,
  locale,
}: {
  file: File;
  validation: BackupValidation;
  locale: Locale;
}) {
  const { t } = useI18n();
  const manifest = validation.manifest;
  return (
    <div className={cn("backup-validation", validation.valid ? "is-valid" : "is-invalid")}>
      <div className="backup-validation__head">
        {validation.valid ? (
          <CheckCircle2 size={18} aria-hidden="true" />
        ) : (
          <XCircle size={18} aria-hidden="true" />
        )}
        <strong>{validation.valid ? t("backup.validate.valid") : t("backup.validate.invalid")}</strong>
        <Badge tone={validation.valid ? "success" : "danger"}>
          {validation.valid ? t("backup.validate.ready") : t("backup.validate.rejected")}
        </Badge>
      </div>
      <p className="backup-validation__file">
        {file.name}
        <span className="dot-sep" aria-hidden="true" />
        {formatBytes(file.size)}
        <span className="dot-sep" aria-hidden="true" />
        {t("backup.validate.files", { count: validation.file_count })}
      </p>

      {manifest ? (
        <>
          <div className="settings-definitions">
            <DefinitionRow
              label={t("backup.validate.createdAt")}
              value={formatDateTime(manifest.created_at, locale)}
            />
            <DefinitionRow label={t("backup.validate.version")} value={`v${manifest.app_version}`} />
            <DefinitionRow
              label={t("backup.validate.revision")}
              value={<code className="mono">{manifest.alembic_revision}</code>}
            />
            <DefinitionRow
              label={t("backup.validate.uncompressed")}
              value={formatBytes(validation.uncompressed_size_bytes)}
            />
          </div>
          <div className="backup-counts">
            {[
              ["activities", "backup.count.activities"],
              ["goals", "backup.count.goals"],
              ["races", "backup.count.races"],
              ["actions", "backup.count.actions"],
              ["external_metrics", "backup.count.metrics"],
              ["raw_files", "backup.count.raw"],
            ].map(([key, label]) => (
              <div className="backup-count" key={key}>
                <strong>{manifest.counts?.[key] ?? 0}</strong>
                <span>{t(label as MessageKey)}</span>
              </div>
            ))}
          </div>
        </>
      ) : null}

      {validation.errors?.length ? (
        <ul className="problem-list" role="alert">
          {validation.errors.map((error) => (
            <li key={error}>
              <TriangleAlert size={14} aria-hidden="true" />
              {error}
            </li>
          ))}
        </ul>
      ) : null}

      {validation.warnings?.length ? (
        <details className="import-history__details">
          <summary>{t("backup.validate.warnings")}</summary>
          <ul>
            {validation.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
