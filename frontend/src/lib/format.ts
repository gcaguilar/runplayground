import { localeTag, type Locale, type MessageKey, type Units } from "@/i18n";

const KM_PER_MILE = 1.609344;
const FEET_PER_METER = 3.280839895;

export function parseUtc(value: string): Date {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day);
  }
  const hasZone = /(?:z|[+-]\d{2}:\d{2})$/i.test(value);
  return new Date(hasZone ? value : `${value}Z`);
}

export function formatNumber(
  value: number | null | undefined,
  locale: Locale,
  digits = 0,
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(localeTag(locale), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatDistance(
  meters: number | null | undefined,
  units: Units,
  locale: Locale,
  options: { digits?: number; forceKm?: boolean; unit?: boolean } = {},
): string {
  if (meters === null || meters === undefined || !Number.isFinite(meters)) return "—";
  const { digits = 2, forceKm = true, unit = true } = options;
  if (units === "imperial") {
    const miles = meters / 1000 / KM_PER_MILE;
    if (!forceKm && miles < 0.1) {
      const feet = meters * FEET_PER_METER;
      return unit ? `${formatNumber(feet, locale)} ft` : formatNumber(feet, locale);
    }
    const formatted = formatNumber(miles, locale, digits);
    return unit ? `${formatted} mi` : formatted;
  }
  if (!forceKm && meters < 1000) {
    const rounded = Math.round(meters / 10) * 10;
    return unit ? `${formatNumber(rounded, locale)} m` : formatNumber(rounded, locale);
  }
  const km = meters / 1000;
  const formatted = formatNumber(km, locale, digits);
  return unit ? `${formatted} km` : formatted;
}

export function formatElevation(
  meters: number | null | undefined,
  units: Units,
  locale: Locale,
): string {
  if (meters === null || meters === undefined || !Number.isFinite(meters)) return "—";
  if (units === "imperial") {
    return `${formatNumber(meters * FEET_PER_METER, locale)} ft`;
  }
  return `${formatNumber(meters, locale)} m`;
}

export function formatPace(
  secondsPerKm: number | null | undefined,
  units: Units,
  options: { suffix?: boolean } = {},
): string {
  if (
    secondsPerKm === null ||
    secondsPerKm === undefined ||
    !Number.isFinite(secondsPerKm) ||
    secondsPerKm <= 0
  ) {
    return "—";
  }
  const { suffix = true } = options;
  const value = units === "imperial" ? secondsPerKm * KM_PER_MILE : secondsPerKm;
  const total = Math.round(value);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  const base = `${minutes}:${String(seconds).padStart(2, "0")}`;
  if (!suffix) return base;
  return `${base} /${units === "imperial" ? "mi" : "km"}`;
}

export function formatDuration(
  seconds: number | null | undefined,
  locale: Locale,
  compact = false,
): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "—";
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  const short = locale === "es" ? { h: "h", m: "min", s: "s" } : { h: "h", m: "m", s: "s" };

  if (hours > 0) {
    return compact
      ? `${hours}${short.h} ${String(minutes).padStart(2, "0")}${short.m}`
      : `${hours} ${short.h} ${String(minutes).padStart(2, "0")} ${short.m}`;
  }
  if (minutes > 0) {
    return compact
      ? `${minutes}${short.m} ${String(rest).padStart(2, "0")}${short.s}`
      : `${minutes} ${short.m} ${String(rest).padStart(2, "0")} ${short.s}`;
  }
  return `${rest} ${short.s}`;
}

export function formatClock(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "—";
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
  }
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

export function formatDate(
  value: string | Date | null | undefined,
  locale: Locale,
  options: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" },
): string {
  if (!value) return "—";
  const date = value instanceof Date ? value : parseUtc(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(localeTag(locale), options).format(date);
}

export function formatDateTime(
  value: string | Date | null | undefined,
  locale: Locale,
  options: Intl.DateTimeFormatOptions = {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  },
): string {
  if (!value) return "—";
  const date = value instanceof Date ? value : parseUtc(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(localeTag(locale), options).format(date);
}

export function formatTimeOfDay(value: string | Date | null | undefined, locale: Locale): string {
  return formatDateTime(value, locale, { hour: "2-digit", minute: "2-digit" });
}

export function formatWeekRange(
  weekStart: string,
  weekEnd: string,
  locale: Locale,
): string {
  const start = parseUtc(weekStart);
  const end = parseUtc(weekEnd);
  const sameMonth = start.getMonth() === end.getMonth() && start.getFullYear() === end.getFullYear();
  const startFormatter = new Intl.DateTimeFormat(localeTag(locale), {
    day: "numeric",
    month: sameMonth ? undefined : "short",
  });
  const endFormatter = new Intl.DateTimeFormat(localeTag(locale), {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  return `${startFormatter.format(start)} – ${endFormatter.format(end)}`;
}

export function formatRelative(
  value: string | Date | null | undefined,
  locale: Locale,
): string {
  if (!value) return "—";
  const date = value instanceof Date ? value : parseUtc(value);
  if (Number.isNaN(date.getTime())) return "—";
  const deltaSeconds = (date.getTime() - Date.now()) / 1000;
  const formatter = new Intl.RelativeTimeFormat(localeTag(locale), { numeric: "auto" });
  const absolute = Math.abs(deltaSeconds);
  if (absolute < 60) return formatter.format(Math.round(deltaSeconds), "second");
  if (absolute < 3600) return formatter.format(Math.round(deltaSeconds / 60), "minute");
  if (absolute < 86_400) return formatter.format(Math.round(deltaSeconds / 3600), "hour");
  if (absolute < 2_592_000) return formatter.format(Math.round(deltaSeconds / 86_400), "day");
  if (absolute < 31_536_000) {
    return formatter.format(Math.round(deltaSeconds / 2_592_000), "month");
  }
  return formatter.format(Math.round(deltaSeconds / 31_536_000), "year");
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatPercent(
  value: number | null | undefined,
  locale: Locale,
  digits = 0,
): string {
  if (value === null || value === undefined) return "—";
  return `${formatNumber(value, locale, digits)}%`;
}

export function formatDelta(
  value: number | null | undefined,
  locale: Locale,
): string | null {
  if (value === null || value === undefined) return null;
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value, locale, 0)}%`;
}

export function sportKey(sport: string | null | undefined): MessageKey {
  if (!sport) return "sport.other";
  const key = `sport.${sport}` as MessageKey;
  const known = new Set<MessageKey>([
    "sport.running",
    "sport.trail_running",
    "sport.treadmill_running",
    "sport.track_running",
    "sport.indoor_running",
    "sport.virtual_run",
    "sport.cycling",
    "sport.walking",
    "sport.hiking",
    "sport.swimming",
    "sport.strength_training",
    "sport.other",
  ]);
  return known.has(key) ? key : "sport.other";
}

export function localIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function startOfWeek(date: Date): Date {
  const result = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const day = result.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  result.setDate(result.getDate() + diff);
  return result;
}

export function addDays(date: Date, days: number): Date {
  const result = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  result.setDate(result.getDate() + days);
  return result;
}

export function weekStartKey(offsetWeeks = 0): string {
  return localIsoDate(addDays(startOfWeek(new Date()), offsetWeeks * 7));
}

export function weekdayKeys() {
  return [
    "weekday.mon",
    "weekday.tue",
    "weekday.wed",
    "weekday.thu",
    "weekday.fri",
    "weekday.sat",
    "weekday.sun",
  ] as const;
}

export function scoreBand(score: number): "excellent" | "good" | "fair" | "poor" {
  if (score >= 88) return "excellent";
  if (score >= 70) return "good";
  if (score >= 45) return "fair";
  return "poor";
}

export function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
