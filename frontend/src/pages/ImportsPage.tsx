import { useRef, useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  ArrowRight,
  CheckCircle2,
  Clock3,
  Database,
  FileUp,
  History,
  Info,
  Trash2,
  TriangleAlert,
  UploadCloud,
  XCircle,
} from "lucide-react";

import type { ImportFileResult, ImportRun } from "@/api/client";
import { useImportFiles, useImports } from "@/api/queries";
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
import { useI18n, type MessageKey } from "@/i18n";
import {
  formatBytes,
  formatDateTime,
  formatRelative,
} from "@/lib/format";
import { cn } from "@/lib/cn";

const MAX_FILE_BYTES = 50 * 1024 * 1024;
const MAX_FILES = 20;
const ACCEPTED = [".fit", ".tcx", ".gpx"];

type PendingFile = {
  key: string;
  file: File;
};

export function ImportsPage() {
  const { locale, t } = useI18n();
  const imports = useImports();
  const upload = useImportFiles();
  const inputRef = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<PendingFile[]>([]);
  const [problems, setProblems] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);
  const [results, setResults] = useState<ImportFileResult[] | null>(null);

  const addFiles = (incoming: FileList | File[]) => {
    const nextProblems: string[] = [];
    const candidates = Array.from(incoming);
    setPending((current) => {
      const next = [...current];
      for (const file of candidates) {
        const extension = file.name.includes(".")
          ? `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`
          : "";
        if (!ACCEPTED.includes(extension)) {
          nextProblems.push(`${file.name}: ${t("imports.unsupported")}`);
          continue;
        }
        if (file.size > MAX_FILE_BYTES) {
          nextProblems.push(`${file.name}: ${t("imports.tooBig")}`);
          continue;
        }
        const key = `${file.name}-${file.size}-${file.lastModified}`;
        if (next.some((item) => item.key === key)) {
          nextProblems.push(`${file.name}: ${t("imports.duplicateFile")}`);
          continue;
        }
        if (next.length >= MAX_FILES) {
          nextProblems.push(`${file.name}: ${t("imports.tooMany")}`);
          continue;
        }
        next.push({ key, file });
      }
      return next;
    });
    setProblems(nextProblems);
  };

  const removeFile = (key: string) => {
    setPending((current) => current.filter((item) => item.key !== key));
  };

  const startUpload = () => {
    if (!pending.length) {
      setProblems([t("imports.emptyFiles")]);
      return;
    }
    setProblems([]);
    upload.mutate(
      pending.map((item) => item.file),
      {
        onSuccess: (response) => {
          setResults(response.results);
          setPending([]);
        },
      },
    );
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={t("nav.library")}
        title={t("imports.title")}
        description={t("imports.subtitle")}
        actions={
          <Link to="/activities" className="button button--secondary button--md">
            {t("nav.activities")}
            <ArrowRight size={15} aria-hidden="true" />
          </Link>
        }
      />

      <div className="imports-layout">
        <div className="imports-main">
          <Card className="panel">
            <div
              className={cn("dropzone", dragging && "is-dragging", upload.isPending && "is-busy")}
              onDragOver={(event) => {
                event.preventDefault();
                if (!upload.isPending) setDragging(true);
              }}
              onDragLeave={(event) => {
                if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
                setDragging(false);
              }}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                if (!upload.isPending && event.dataTransfer.files.length) {
                  addFiles(event.dataTransfer.files);
                }
              }}
              onClick={() => {
                if (!upload.isPending) inputRef.current?.click();
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  inputRef.current?.click();
                }
              }}
              role="button"
              tabIndex={0}
              aria-label={t("imports.drop.button")}
            >
              <span className="dropzone__icon">
                <UploadCloud size={28} aria-hidden="true" />
              </span>
              <strong>{t("imports.drop.title")}</strong>
              <p>{t("imports.drop.or")}</p>
              <span className="dropzone__hint">{t("imports.drop.hint")}</span>
              <Button variant="secondary" size="sm" tabIndex={-1}>
                <FileUp size={15} aria-hidden="true" />
                {t("imports.drop.button")}
              </Button>
              <input
                ref={inputRef}
                type="file"
                multiple
                accept=".fit,.tcx,.gpx"
                className="visually-hidden"
                onChange={(event) => {
                  if (event.target.files?.length) addFiles(event.target.files);
                  event.target.value = "";
                }}
              />
            </div>

            {problems.length ? (
              <ul className="problem-list" role="alert">
                {problems.map((problem) => (
                  <li key={problem}>
                    <TriangleAlert size={14} aria-hidden="true" />
                    {problem}
                  </li>
                ))}
              </ul>
            ) : null}
          </Card>

          {pending.length ? (
            <Card className="panel">
              <SectionHeading
                title={t("imports.selected")}
                subtitle={t("activities.count", { count: pending.length })}
                icon={FileUp}
                action={
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setPending([])}
                    disabled={upload.isPending}
                  >
                    {t("imports.clear")}
                  </Button>
                }
              />
              <div className="file-queue">
                {pending.map((item) => (
                  <div className="file-row" key={item.key}>
                    <span className="file-row__icon">
                      <FileUp size={17} aria-hidden="true" />
                    </span>
                    <div className="file-row__copy">
                      <strong>{item.file.name}</strong>
                      <span>
                        {formatBytes(item.file.size)}
                        <span className="dot-sep" aria-hidden="true" />
                        {item.file.name.split(".").pop()?.toUpperCase()}
                      </span>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => removeFile(item.key)}
                      disabled={upload.isPending}
                      aria-label={t("imports.remove", { name: item.file.name })}
                    >
                      <Trash2 size={15} aria-hidden="true" />
                    </Button>
                  </div>
                ))}
              </div>
              <div className="form-actions">
                <Button
                  variant="primary"
                  size="md"
                  loading={upload.isPending}
                  onClick={startUpload}
                >
                  <UploadCloud size={16} aria-hidden="true" />
                  {upload.isPending
                    ? t("imports.uploading")
                    : t("imports.upload", { count: pending.length })}
                </Button>
              </div>
            </Card>
          ) : null}

          {upload.isError ? (
            <ErrorState
              message={upload.error instanceof Error ? upload.error.message : t("imports.error")}
              onRetry={startUpload}
            />
          ) : null}

          {results ? (
            <Card className="panel">
              <SectionHeading title={t("imports.results.title")} icon={History} />
              <div className="import-results">
                {results.map((result, index) => (
                  <div className="import-result" key={`${result.filename}-${index}`}>
                    <ResultIcon status={result.status} />
                    <div className="import-result__copy">
                      <strong>{result.filename}</strong>
                      {result.message ? <span>{result.message}</span> : null}
                      {result.warnings?.length ? (
                        <div className="import-result__warnings">
                          <span>{t("imports.warnings")}</span>
                          <ul>
                            {result.warnings.map((warning) => (
                              <li key={warning}>{warning}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                    </div>
                    <div className="import-result__actions">
                      <Badge tone={resultTone(result.status)}>{statusLabel(result.status, t)}</Badge>
                      {result.activity_id ? (
                        <Link
                          to="/activities/$activityId"
                          params={{ activityId: String(result.activity_id) }}
                          className="text-link"
                        >
                          {t("imports.openActivity")}
                          <ArrowRight size={13} aria-hidden="true" />
                        </Link>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          ) : null}
        </div>

        <aside className="imports-rail">
          <Card className="panel note-card">
            <span className="note-card__icon">
              <Info size={18} aria-hidden="true" />
            </span>
            <h2>{t("imports.note.title")}</h2>
            <p>{t("imports.note.body")}</p>
            <div className="note-card__fact">
              <Database size={15} aria-hidden="true" />
              <span>{t("detail.provenance.localNote")}</span>
            </div>
          </Card>

          <Card className="panel">
            <SectionHeading
              title={t("imports.history.title")}
              icon={Clock3}
              subtitle={t("imports.recent")}
            />
            {imports.isLoading ? (
              <div className="import-history">
                {Array.from({ length: 3 }).map((_, index) => (
                  <div className="import-history__row" key={index}>
                    <Skeleton className="skeleton--line" />
                    <Skeleton className="skeleton--line skeleton--short" />
                  </div>
                ))}
              </div>
            ) : imports.isError ? (
              <ErrorState onRetry={() => void imports.refetch()} />
            ) : imports.data?.length ? (
              <div className="import-history">
                {imports.data.map((run) => (
                  <ImportRunRow key={run.id} run={run} locale={locale} />
                ))}
              </div>
            ) : (
              <EmptyState compact title={t("imports.history.empty")} icon={History} />
            )}
          </Card>
        </aside>
      </div>
    </div>
  );
}

function ImportRunRow({ run, locale }: { run: ImportRun; locale: "es" | "en" }) {
  const { t } = useI18n();
  const files = run.results ?? [];
  return (
    <div className="import-history__item">
      <div className="import-history__row">
        <div>
          <strong>{formatDateTime(run.started_at, locale)}</strong>
          <span>
            {t("imports.history.files", { count: files.length })}
            <span className="dot-sep" aria-hidden="true" />
            {formatRelative(run.started_at, locale)}
          </span>
        </div>
        <Badge tone={run.status === "success" ? "success" : run.status === "error" ? "danger" : "info"}>
          {statusLabel(run.status, t)}
        </Badge>
      </div>
      {files.length ? (
        <details className="import-history__details">
          <summary>{t("imports.history.details")}</summary>
          <ul>
            {files.map((file, index) => (
              <li key={`${file.filename}-${index}`}>
                <span>{file.filename}</span>
                <Badge tone={resultTone(file.status)}>{statusLabel(file.status, t)}</Badge>
              </li>
            ))}
          </ul>
        </details>
      ) : (
        <span className="import-history__none">{t("imports.history.noDetails")}</span>
      )}
    </div>
  );
}

function ResultIcon({ status }: { status: string }) {
  if (status === "error") return <XCircle size={20} className="result-icon result-icon--error" aria-hidden="true" />;
  if (status === "duplicate") return <Info size={20} className="result-icon result-icon--info" aria-hidden="true" />;
  return <CheckCircle2 size={20} className="result-icon result-icon--success" aria-hidden="true" />;
}

function resultTone(status: string): "success" | "warning" | "danger" | "info" | "neutral" {
  if (status === "error") return "danger";
  if (status === "duplicate") return "warning";
  if (status === "merged") return "info";
  if (status === "imported") return "success";
  return "neutral";
}

function statusLabel(status: string, t: (key: MessageKey) => string): string {
  const known: Record<string, MessageKey> = {
    imported: "imports.status.imported",
    merged: "imports.status.merged",
    duplicate: "imports.status.duplicate",
    error: "imports.status.error",
    success: "imports.status.success",
    partial: "imports.status.partial",
    running: "imports.status.running",
  };
  return known[status] ? t(known[status]) : status;
}
