import {
  ArrowRight,
  CheckCircle2,
  Info,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { Link } from "@tanstack/react-router";

import { Card, PageHeader, SectionHeading } from "@/components/ui";
import { useI18n, type MessageKey } from "@/i18n";

type PlaceholderConfig = {
  eyebrow: MessageKey;
  title: MessageKey;
  subtitle: MessageKey;
  capabilities: MessageKey[];
  progressTitle: MessageKey;
  progressBody: MessageKey;
  icon: LucideIcon;
  stage: string;
};

const CONFIG: PlaceholderConfig = {
  eyebrow: "progress.eyebrow",
  title: "progress.title",
  subtitle: "progress.subtitle",
  capabilities: [
    "progress.capability.1",
    "progress.capability.2",
    "progress.capability.3",
    "progress.capability.4",
  ],
  progressTitle: "progress.progress.title",
  progressBody: "progress.progress.body",
  icon: TrendingUp,
  stage: "M3",
};

function PlaceholderPage({ config }: { config: PlaceholderConfig }) {
  const { t } = useI18n();
  const Icon = config.icon;

  return (
    <div className="page-stack">
      <PageHeader eyebrow={t(config.eyebrow)} title={t(config.title)} description={t(config.subtitle)} />

      <div className="placeholder-grid">
        <Card className="panel placeholder-hero">
          <span className="placeholder-hero__icon">
            <Icon size={30} aria-hidden="true" />
          </span>
          <div>
            <span className="eyebrow">{t("placeholder.milestone")}</span>
            <h2>{config.stage}</h2>
            <p>{t(config.progressBody)}</p>
          </div>
          <div className="placeholder-stage">
            <span className="mono">{config.stage}</span>
          </div>
        </Card>

        <Card className="panel">
          <SectionHeading title={t("placeholder.capabilities")} icon={CheckCircle2} />
          <ul className="capability-list">
            {config.capabilities.map((key) => (
              <li key={key}>
                <span className="capability-list__dot" aria-hidden="true" />
                {t(key)}
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card className="panel placeholder-note">
        <span className="placeholder-note__icon">
          <Info size={18} aria-hidden="true" />
        </span>
        <div>
          <strong>{t(config.progressTitle)}</strong>
          <p>{t("placeholder.note")}</p>
        </div>
        <Link to="/data" className="text-link">
          {t("data.title")}
          <ArrowRight size={13} aria-hidden="true" />
        </Link>
      </Card>
    </div>
  );
}

export function ProgressPage() {
  return <PlaceholderPage config={CONFIG} />;
}
