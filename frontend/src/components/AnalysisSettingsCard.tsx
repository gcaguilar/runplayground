import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, HeartPulse, Save, TriangleAlert, Undo2 } from "lucide-react";

import { ApiError } from "@/api/client";
import type {
  AnalysisClassificationMode,
  AnalysisSettingsUpdate,
  AnalysisSettingsValues,
} from "@/api/client";
import { useAnalysisSettings, useUpdateAnalysisSettings } from "@/api/queries";
import { Badge, Button, Card, ErrorState, SectionHeading, Skeleton } from "@/components/ui";
import { useI18n, type MessageKey } from "@/i18n";
import { formatDateTime, formatPace } from "@/lib/format";
import { cn } from "@/lib/cn";

const KM_PER_MILE = 1.609344;

const MODES: AnalysisClassificationMode[] = ["auto", "pace", "hr"];

const SOURCE_TONES: Record<string, "neutral" | "accent" | "success" | "warning" | "info"> = {
  manual: "accent",
  observed: "info",
  derived: "warning",
  missing: "neutral",
};

const KNOWN_WARNINGS = new Set<MessageKey>([
  "settings.analysis.warning.no_observed_max_hr",
  "settings.analysis.warning.no_observed_resting_hr",
  "settings.analysis.warning.no_observed_threshold_pace",
  "settings.analysis.warning.no_threshold_hr",
  "settings.analysis.warning.no_threshold_pace",
  "settings.analysis.warning.manual_threshold_without_manual_max_hr",
]);

type Draft = {
  maxHr: string;
  restingHr: string;
  thresholdHr: string;
  pace: string;
  mode: AnalysisClassificationMode;
};

function emptyDraft(mode: AnalysisClassificationMode = "auto"): Draft {
  return { maxHr: "", restingHr: "", thresholdHr: "", pace: "", mode };
}

function valueString(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

function paceDraft(secondsPerKm: number | null | undefined, imperial: boolean): string {
  if (secondsPerKm === null || secondsPerKm === undefined) return "";
  const value = imperial ? secondsPerKm * KM_PER_MILE : secondsPerKm;
  const total = Math.round(value);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function parsePaceDraft(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const match = /^(\d{1,2}):(\d{1,2})$/.exec(trimmed);
  if (!match) return Number.NaN;
  const minutes = Number(match[1]);
  const seconds = Number(match[2]);
  if (seconds >= 60) return Number.NaN;
  return minutes * 60 + seconds;
}

function draftFrom(
  manual: AnalysisSettingsValues | undefined,
  imperial: boolean,
): Draft {
  return {
    maxHr: valueString(manual?.max_hr),
    restingHr: valueString(manual?.resting_hr),
    thresholdHr: valueString(manual?.threshold_hr),
    pace: paceDraft(manual?.threshold_pace_s_per_km, imperial),
    mode: manual?.classification_mode ?? "auto",
  };
}

export function AnalysisSettingsCard() {
  const { t, units, locale } = useI18n();
  const settings = useAnalysisSettings();
  const save = useUpdateAnalysisSettings();
  const imperial = units === "imperial";
  const [draft, setDraft] = useState<Draft>(() => emptyDraft());
  const [localError, setLocalError] = useState<string | null>(null);
  const [savedFlash, setSavedFlash] = useState(false);

  const data = settings.data;
  const manual = data?.manual;
  const effective = data?.effective;
  const observed = data?.observed;

  useEffect(() => {
    if (!manual) return;
    setDraft(draftFrom(manual, imperial));
  }, [manual, imperial]);

  useEffect(() => {
    if (!savedFlash) return;
    const timer = window.setTimeout(() => setSavedFlash(false), 2400);
    return () => window.clearTimeout(timer);
  }, [savedFlash]);

  const modeHint = useMemo<MessageKey>(() => {
    if (draft.mode === "pace") return "settings.analysis.mode.paceHint";
    if (draft.mode === "hr") return "settings.analysis.mode.hrHint";
    return "settings.analysis.mode.autoHint";
  }, [draft.mode]);

  if (settings.isError) {
    return (
      <Card className="panel">
        <SectionHeading title={t("settings.analysis.title")} icon={HeartPulse} />
        <ErrorState
          message={
            settings.error instanceof Error
              ? settings.error.message
              : t("settings.analysis.loadError")
          }
          onRetry={() => void settings.refetch()}
        />
      </Card>
    );
  }

  if (!data) {
    return (
      <Card className="panel">
        <SectionHeading title={t("settings.analysis.title")} icon={HeartPulse} />
        <Skeleton className="skeleton--block" />
      </Card>
    );
  }

  const submit = () => {
    setLocalError(null);
    setSavedFlash(false);
    const maxHr = parseOptionalInteger(draft.maxHr);
    const restingHr = parseOptionalInteger(draft.restingHr);
    const thresholdHr = parseOptionalInteger(draft.thresholdHr);
    if (
      (maxHr !== null && !Number.isFinite(maxHr)) ||
      (restingHr !== null && !Number.isFinite(restingHr)) ||
      (thresholdHr !== null && !Number.isFinite(thresholdHr))
    ) {
      setLocalError(t("settings.analysis.invalidNumber"));
      return;
    }
    if (maxHr !== null && (maxHr < 100 || maxHr > 230)) {
      setLocalError(t("settings.analysis.invalidMaxHr"));
      return;
    }
    if (restingHr !== null && (restingHr < 30 || restingHr > 120)) {
      setLocalError(t("settings.analysis.invalidRestingHr"));
      return;
    }
    if (thresholdHr !== null && (thresholdHr < 100 || thresholdHr > 230)) {
      setLocalError(t("settings.analysis.invalidThresholdHr"));
      return;
    }
    if (maxHr !== null && thresholdHr !== null && thresholdHr > maxHr) {
      setLocalError(t("settings.analysis.invalidCoherence"));
      return;
    }
    if (restingHr !== null && thresholdHr !== null && restingHr >= thresholdHr) {
      setLocalError(t("settings.analysis.invalidCoherence"));
      return;
    }

    let pace: number | null = null;
    const parsedPace = parsePaceDraft(draft.pace);
    if (Number.isNaN(parsedPace)) {
      setLocalError(t("settings.analysis.invalidPace"));
      return;
    }
    if (parsedPace !== null) {
      pace = imperial ? parsedPace / KM_PER_MILE : parsedPace;
      if (pace < 120 || pace > 1200) {
        setLocalError(t("settings.analysis.invalidPace"));
        return;
      }
    }

    const payload: AnalysisSettingsUpdate = {
      max_hr: maxHr,
      resting_hr: restingHr,
      threshold_hr: thresholdHr,
      threshold_pace_s_per_km: pace === null ? null : Math.round(pace * 10) / 10,
      classification_mode: draft.mode,
    };
    save.mutate(payload, {
      onSuccess: () => setSavedFlash(true),
    });
  };

  const useObserved = () => {
    setLocalError(null);
    setDraft(emptyDraft());
    save.mutate(
      {
        max_hr: null,
        resting_hr: null,
        threshold_hr: null,
        threshold_pace_s_per_km: null,
        classification_mode: null,
      },
      { onSuccess: () => setSavedFlash(true) },
    );
  };

  const error = localError ?? mutationError(save.error, t);

  return (
    <Card className="panel analysis-settings">
      <SectionHeading
        title={t("settings.analysis.title")}
        subtitle={t("settings.analysis.subtitle")}
        icon={HeartPulse}
        action={
          savedFlash ? (
            <span className="form-success">
              <CheckCircle2 size={14} aria-hidden="true" />
              {t("settings.analysis.saved")}
            </span>
          ) : data.updated_at ? (
            <span className="analysis-settings__updated">
              {t("settings.analysis.updated", {
                time: formatDateTime(data.updated_at, locale),
              })}
            </span>
          ) : null
        }
      />

      <p className="settings-intro">{t("settings.analysis.description")}</p>

      <div className="analysis-settings__fields">
        <label>
          <span>{t("settings.analysis.maxHr")}</span>
          <input
            type="number"
            inputMode="numeric"
            min={100}
            max={230}
            value={draft.maxHr}
            placeholder={valueString(observed?.max_hr) || "—"}
            onChange={(event) => setDraft({ ...draft, maxHr: event.target.value })}
          />
        </label>
        <label>
          <span>{t("settings.analysis.restingHr")}</span>
          <input
            type="number"
            inputMode="numeric"
            min={30}
            max={120}
            value={draft.restingHr}
            placeholder={valueString(observed?.resting_hr) || "—"}
            onChange={(event) => setDraft({ ...draft, restingHr: event.target.value })}
          />
        </label>
        <label>
          <span>{t("settings.analysis.thresholdHr")}</span>
          <input
            type="number"
            inputMode="numeric"
            min={100}
            max={230}
            value={draft.thresholdHr}
            placeholder={valueString(effective?.threshold_hr) || "—"}
            onChange={(event) => setDraft({ ...draft, thresholdHr: event.target.value })}
          />
        </label>
        <label>
          <span>
            {t("settings.analysis.thresholdPace", {
              unit: imperial ? "mi" : "km",
            })}
          </span>
          <input
            type="text"
            inputMode="numeric"
            value={draft.pace}
            placeholder={paceDraft(effective?.threshold_pace_s_per_km ?? null, imperial) || "—"}
            onChange={(event) => setDraft({ ...draft, pace: event.target.value })}
          />
        </label>
      </div>

      <div className="analysis-settings__mode">
        <span className="analysis-settings__label">{t("settings.analysis.mode")}</span>
        <div className="segmented" role="group" aria-label={t("settings.analysis.mode")}>
          {MODES.map((mode) => (
            <button
              key={mode}
              type="button"
              className={cn(draft.mode === mode && "is-active")}
              aria-pressed={draft.mode === mode}
              onClick={() => setDraft({ ...draft, mode })}
            >
              {t(`settings.analysis.mode.${mode}` as MessageKey)}
            </button>
          ))}
        </div>
        <p className="settings-hint">{t(modeHint)}</p>
      </div>

      <div className="analysis-settings__table" role="table">
        <div className="analysis-settings__row analysis-settings__row--head" role="row">
          <span role="columnheader">{t("settings.analysis.field")}</span>
          <span role="columnheader">{t("settings.analysis.observed")}</span>
          <span role="columnheader">{t("settings.analysis.effective")}</span>
          <span role="columnheader">{t("settings.analysis.source")}</span>
        </div>
        <SettingRow
          label={t("settings.analysis.maxHr")}
          observed={valueString(observed?.max_hr)}
          effective={valueString(effective?.max_hr)}
          source={data.sources?.max_hr}
        />
        <SettingRow
          label={t("settings.analysis.restingHr")}
          observed={valueString(observed?.resting_hr)}
          effective={valueString(effective?.resting_hr)}
          source={data.sources?.resting_hr}
        />
        <SettingRow
          label={t("settings.analysis.thresholdHr")}
          observed={valueString(observed?.threshold_hr)}
          effective={valueString(effective?.threshold_hr)}
          source={data.sources?.threshold_hr}
        />
        <SettingRow
          label={t("settings.analysis.thresholdPace", {
            unit: imperial ? "mi" : "km",
          })}
          observed={paceOrDash(observed?.threshold_pace_s_per_km, imperial, units)}
          effective={paceOrDash(effective?.threshold_pace_s_per_km, imperial, units)}
          source={data.sources?.threshold_pace_s_per_km}
        />
        <SettingRow
          label={t("settings.analysis.mode")}
          observed="—"
          effective={t(
            `settings.analysis.mode.${effective?.classification_mode ?? "auto"}` as MessageKey,
          )}
          source={data.sources?.classification_mode}
        />
      </div>

      {data.warnings?.length ? (
        <ul className="analysis-settings__warnings">
          {data.warnings.map((warning) => (
            <li key={warning}>
              <TriangleAlert size={13} aria-hidden="true" />
              {warningLabel(warning, t)}
            </li>
          ))}
        </ul>
      ) : null}

      <p className="settings-hint">{t("settings.analysis.anchorNote")}</p>

      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="form-actions analysis-settings__actions">
        <Button variant="primary" size="md" loading={save.isPending} onClick={submit}>
          <Save size={15} aria-hidden="true" />
          {t("settings.analysis.save")}
        </Button>
        <Button
          variant="secondary"
          size="md"
          disabled={save.isPending}
          onClick={useObserved}
        >
          <Undo2 size={15} aria-hidden="true" />
          {t("settings.analysis.useObserved")}
        </Button>
      </div>
    </Card>
  );
}

function SettingRow({
  label,
  observed,
  effective,
  source,
}: {
  label: string;
  observed: string;
  effective: string;
  source: string | undefined;
}) {
  const { t } = useI18n();
  const known = source && source in SOURCE_TONES ? source : "missing";
  return (
    <div className="analysis-settings__row" role="row">
      <span role="cell">{label}</span>
      <span role="cell" className="num">
        {observed || "—"}
      </span>
      <span role="cell" className="num analysis-settings__effective">
        {effective || "—"}
      </span>
      <span role="cell">
        <Badge tone={SOURCE_TONES[known]}>
          {t(`settings.analysis.source.${known}` as MessageKey)}
        </Badge>
      </span>
    </div>
  );
}

function paceOrDash(
  secondsPerKm: number | null | undefined,
  imperial: boolean,
  units: "metric" | "imperial",
): string {
  if (secondsPerKm === null || secondsPerKm === undefined) return "—";
  return formatPace(secondsPerKm, units, { suffix: false }) + (imperial ? " /mi" : " /km");
}

function parseOptionalInteger(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || !Number.isInteger(parsed)) return Number.NaN;
  return parsed;
}

function warningLabel(warning: string, t: (key: MessageKey) => string): string {
  const key = `settings.analysis.warning.${warning}` as MessageKey;
  return KNOWN_WARNINGS.has(key) ? t(key) : warning;
}

function mutationError(
  error: unknown,
  t: (key: MessageKey) => string,
): string | null {
  if (!error) return null;
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return t("settings.analysis.error");
}
