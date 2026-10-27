import type { MessageKey } from "@/i18n";

export type ToastTone = "success" | "warning" | "danger" | "info";

export type ToastInput = {
  tone: ToastTone;
  titleKey?: MessageKey;
  title?: string;
  messageKey?: MessageKey;
  message?: string;
  values?: Record<string, string | number>;
  href?: string;
  linkKey?: MessageKey;
  durationMs?: number;
};

export type ToastItem = ToastInput & { id: number };

export const TOAST_EVENT = "run:toast";

let nextId = 0;

export function notifyToast(input: ToastInput): void {
  if (typeof window === "undefined") return;
  nextId += 1;
  const item: ToastItem = { ...input, id: nextId };
  window.dispatchEvent(new CustomEvent<ToastItem>(TOAST_EVENT, { detail: item }));
}
