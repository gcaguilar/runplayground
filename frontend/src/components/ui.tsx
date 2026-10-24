import type {
  ButtonHTMLAttributes,
  ComponentPropsWithoutRef,
  ReactNode,
} from "react";
import {
  AlertTriangle,
  ArrowRight,
  LoaderCircle,
  RefreshCw,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/cn";
import { useI18n } from "@/i18n";
import type { MessageKey } from "@/i18n";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "quiet";
type ButtonSize = "sm" | "md" | "lg" | "icon";

const buttonVariants: Record<ButtonVariant, string> = {
  primary: "button--primary",
  secondary: "button--secondary",
  ghost: "button--ghost",
  danger: "button--danger",
  quiet: "button--quiet",
};

const buttonSizes: Record<ButtonSize, string> = {
  sm: "button--sm",
  md: "button--md",
  lg: "button--lg",
  icon: "button--icon",
};

export function Button({
  children,
  variant = "secondary",
  size = "md",
  loading = false,
  className,
  type = "button",
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}) {
  return (
    <button
      type={type}
      className={cn(
        "button",
        buttonVariants[variant],
        buttonSizes[size],
        loading && "button--loading",
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <LoaderCircle size={16} className="spin" aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

export function Card({
  children,
  className,
  as: Tag = "div",
  ...props
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
} & Omit<ComponentPropsWithoutRef<"div">, "children">) {
  return (
    <Tag className={cn("card", className)} {...props}>
      {children}
    </Tag>
  );
}

type BadgeTone = "neutral" | "accent" | "success" | "warning" | "danger" | "info";

export function Badge({
  children,
  tone = "neutral",
  dot = false,
  className,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  dot?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("badge", `badge--${tone}`, className)}>
      {dot ? <span className="badge__dot" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="spinner" role="status" aria-label={label ?? "Loading"}>
      <LoaderCircle size={18} className="spin" aria-hidden="true" />
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <span className={cn("skeleton", className)} aria-hidden="true" />;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: ReactNode;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div className="page-header__copy">
        {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </header>
  );
}

export function SectionHeading({
  title,
  subtitle,
  action,
  icon: Icon,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  icon?: LucideIcon;
}) {
  return (
    <div className="section-heading">
      <div className="section-heading__copy">
        {Icon ? (
          <span className="section-heading__icon">
            <Icon size={17} aria-hidden="true" />
          </span>
        ) : null}
        <div>
          <h2>{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
      </div>
      {action ? <div className="section-heading__action">{action}</div> : null}
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  compact = false,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={cn("empty-state", compact && "empty-state--compact")}>
      {Icon ? (
        <span className="empty-state__icon">
          <Icon size={22} aria-hidden="true" />
        </span>
      ) : null}
      <h3>{title}</h3>
      {description ? <p>{description}</p> : null}
      {action ? <div className="empty-state__action">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="error-state" role="alert">
      <span className="error-state__icon">
        <AlertTriangle size={20} aria-hidden="true" />
      </span>
      <div>
        <strong>{t("error.title")}</strong>
        <p>{message || t("error.desc")}</p>
      </div>
      {onRetry ? (
        <Button size="sm" variant="secondary" onClick={onRetry}>
          <RefreshCw size={14} aria-hidden="true" />
          {t("common.retry")}
        </Button>
      ) : null}
    </div>
  );
}

export function ProgressBar({
  value,
  tone = "accent",
  label,
}: {
  value: number;
  tone?: "accent" | "warning" | "danger" | "info";
  label?: string;
}) {
  const safe = Math.max(0, Math.min(100, value));
  return (
    <div
      className={cn("progress", `progress--${tone}`)}
      role="progressbar"
      aria-valuenow={Math.round(safe)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <span style={{ width: `${safe}%` }} />
    </div>
  );
}

export function ScoreRing({
  score,
  label,
  caption,
}: {
  score: number;
  label: string;
  caption?: string;
}) {
  const safe = Math.max(0, Math.min(100, score));
  const tone = safe >= 88 ? "excellent" : safe >= 70 ? "good" : safe >= 45 ? "fair" : "poor";
  return (
    <div className={cn("score-ring", `score-ring--${tone}`)}>
      <div
        className="score-ring__chart"
        style={{ ["--score" as string]: `${safe * 3.6}deg` }}
      >
        <div className="score-ring__inner">
          <strong>{safe}</strong>
          <span>{label}</span>
        </div>
      </div>
      {caption ? <p>{caption}</p> : null}
    </div>
  );
}

export function InlineLink({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("inline-link", className)}>
      {children}
      <ArrowRight size={13} aria-hidden="true" />
    </span>
  );
}

export function DefinitionRow({
  label,
  value,
  title,
}: {
  label: string;
  value: ReactNode;
  title?: string;
}) {
  return (
    <div className="definition-row" title={title}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function Translate({ id }: { id: MessageKey }) {
  const { t } = useI18n();
  return <>{t(id)}</>;
}
