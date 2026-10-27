import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  X,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { useI18n } from "@/i18n";
import { TOAST_EVENT, type ToastItem, type ToastTone } from "@/lib/toast";

const TONE_ICON: Record<ToastTone, LucideIcon> = {
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
  info: Info,
};

export function ToastStack() {
  const { t } = useI18n();
  const [items, setItems] = useState<ToastItem[]>([]);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const handle = (event: Event) => {
      const item = (event as CustomEvent<ToastItem>).detail;
      if (!item) return;
      setItems((current) => [...current.slice(-3), item]);
      const timer = window.setTimeout(() => {
        setItems((current) => current.filter((toast) => toast.id !== item.id));
      }, item.durationMs ?? 6500);
      timers.current.push(timer);
    };
    window.addEventListener(TOAST_EVENT, handle);
    const pending = timers.current;
    return () => {
      window.removeEventListener(TOAST_EVENT, handle);
      for (const timer of pending) window.clearTimeout(timer);
    };
  }, []);

  if (!items.length) return null;

  return (
    <div className="toast-stack" role="status" aria-live="polite" aria-atomic="false">
      {items.map((item) => {
        const Icon = TONE_ICON[item.tone];
        const title = item.titleKey ? t(item.titleKey, item.values) : item.title;
        const message = item.messageKey ? t(item.messageKey, item.values) : item.message;
        return (
          <div className={`toast toast--${item.tone}`} key={item.id}>
            <span className="toast__icon">
              <Icon size={17} aria-hidden="true" />
            </span>
            <div className="toast__copy">
              {title ? <strong>{title}</strong> : null}
              {message ? <p>{message}</p> : null}
              {item.href && item.linkKey ? (
                <a className="text-link" href={item.href}>
                  {t(item.linkKey)}
                </a>
              ) : null}
            </div>
            <button
              type="button"
              className="icon-button toast__close"
              aria-label={t("common.close")}
              onClick={() => setItems((current) => current.filter((toast) => toast.id !== item.id))}
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
