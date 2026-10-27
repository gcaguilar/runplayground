import { Badge, Button, Card, SectionHeading } from "@/components/ui";
import type { ActivityDetail, ActivityPatch } from "@/api/client";
import { usePatchActivity } from "@/api/queries";
import { useI18n, type MessageKey } from "@/i18n";
import { formatPace } from "@/lib/format";
import { Gauge, RotateCcw, Sparkles, UserRound } from "lucide-react";

const INTENSITIES = ["easy", "moderate", "hard"] as const;

export function ActivityClassificationCard({ activity }: { activity: ActivityDetail }) {
  const { t, units } = useI18n();
  const patch = usePatchActivity();
  const classification = activity.classification;

  if (activity.sport !== "running" || !classification) return null;

  const update = (payload: ActivityPatch) => {
    patch.mutate({ id: activity.id, patch: payload });
  };

  return (
    <Card className="panel classification-card">
      <SectionHeading
        title={t("detail.classification.title")}
        subtitle={t("detail.classification.subtitle")}
        icon={Gauge}
        action={
          <Badge tone={classification.overridden ? "accent" : "info"} dot>
            {classification.overridden
              ? t("detail.classification.manual")
              : t("detail.classification.automatic")}
          </Badge>
        }
      />

      <div className="classification-card__summary">
        <div>
          <span className="classification-card__label">
            {t("detail.classification.effective")}
          </span>
          <strong className="classification-card__key">
            {t(`detail.classification.${classification.key}` as MessageKey)}
          </strong>
        </div>
        <div>
          <span className="classification-card__label">
            {t("detail.classification.automaticKey")}
          </span>
          <span className="classification-card__auto">
            {t(`detail.classification.${classification.auto_key}` as MessageKey)}
          </span>
        </div>
        <div>
          <span className="classification-card__label">{t("detail.classification.mode")}</span>
          <span className="classification-card__auto">
            {t(`settings.analysis.mode.${classification.mode}` as MessageKey)}
          </span>
        </div>
        <div>
          <span className="classification-card__label">
            {t("detail.classification.reference")}
          </span>
          <span className="classification-card__auto">
            {classification.threshold_pace_s_per_km
              ? formatPace(classification.threshold_pace_s_per_km, units)
              : "—"}
            {classification.hr_reference
              ? ` · ${Math.round(classification.hr_reference)} bpm`
              : ""}
          </span>
        </div>
      </div>

      <div className="classification-card__controls">
        <label>
          <span className="classification-card__label">
            {t("detail.classification.override")}
          </span>
          <select
            value={classification.overridden ? classification.key : ""}
            onChange={(event) => {
              const value = event.target.value;
              update({
                intensity_override:
                  value === ""
                    ? null
                    : (value as "easy" | "moderate" | "hard"),
              });
            }}
          >
            <option value="">{t("detail.classification.autoOption")}</option>
            {INTENSITIES.map((intensity) => (
              <option key={intensity} value={intensity}>
                {t(`detail.classification.${intensity}` as MessageKey)}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span className="classification-card__label">{t("detail.classification.rpe")}</span>
          <select
            value={activity.rpe ?? ""}
            onChange={(event) => {
              const value = event.target.value;
              update({ rpe: value === "" ? null : Number(value) });
            }}
          >
            <option value="">{t("detail.classification.rpeNone")}</option>
            {Array.from({ length: 10 }, (_, index) => index + 1).map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>

        <Button
          variant="secondary"
          size="sm"
          className="classification-card__clear"
          disabled={!classification.overridden || patch.isPending}
          onClick={() => update({ intensity_override: null })}
        >
          <RotateCcw size={14} aria-hidden="true" />
          {t("detail.classification.clear")}
        </Button>
      </div>

      <p className="classification-card__note">
        {classification.overridden ? (
          <UserRound size={13} aria-hidden="true" />
        ) : (
          <Sparkles size={13} aria-hidden="true" />
        )}
        {classification.overridden
          ? t("detail.classification.manualNote")
          : t("detail.classification.autoNote")}
      </p>
    </Card>
  );
}
