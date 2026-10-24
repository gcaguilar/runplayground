import type { components } from "./schema";

type Schemas = components["schemas"];

export type Activity = Schemas["ActivityOut"];
export type ActivityDetail = Schemas["ActivityDetail"];
export type ActivityList = Schemas["ActivityList"];
export type ActivityStreams = Schemas["ActivityStreams"];
export type StreamPoint = Schemas["StreamPoint"];
export type Lap = Schemas["LapOut"];
export type ActivitySource = Schemas["SourceOut"];
export type SourceOut = Schemas["SourceOut"];
export type AuditReport = Schemas["AuditReport"];
export type AuditFinding = Schemas["AuditFinding"];
export type AuditCoverage = Schemas["AuditCoverage"];
export type WeeklySummary = Schemas["WeeklySummary"];
export type WeeklyTotals = Schemas["WeeklyTotals"];
export type WeeklyDay = Schemas["WeeklyDay"];
export type SportTotal = Schemas["SportTotal"];
export type RaceCandidate = Schemas["RaceCandidate"];
export type MissingActivity = Schemas["MissingActivity"];
export type SyncStatus = Schemas["SyncStatus"];
export type SyncRun = Schemas["SyncRunOut"];
export type SystemStatus = Schemas["SystemStatus"];
export type GarminTokenStatus = Schemas["GarminTokenStatus"];
export type ImportResponse = Schemas["ImportResponse"];
export type ImportFileResult = Schemas["ImportFileResult"];
export type ImportRun = Schemas["ImportRunOut"];
export type AuthStatus = Schemas["AuthStatus"];
export type StartSyncResponse = Schemas["StartSyncResponse"];
export type PerformanceOverview = Schemas["PerformanceOverview"];
export type DistancePrediction = Schemas["DistancePredictionOut"];
export type PredictionEstimate = Schemas["PredictionEstimateOut"];
export type PerformanceEffort = Schemas["EffortOut"];
export type FitnessAnchor = Schemas["FitnessAnchorOut"];
export type PerformanceGoal = Schemas["GoalOut"];
export type GoalUpsert = Schemas["GoalUpsert"];
export type PerformanceHistory = Schemas["PerformanceHistory"];
export type PerformanceSnapshot = Schemas["PerformanceSnapshotOut"];
export type PerformanceRecomputeResponse = Schemas["PerformanceRecomputeResponse"];
export type GarminReference = Schemas["GarminReference"];
export type GarminMetricPoint = Schemas["GarminMetricPoint"];
export type GarminRacePrediction = Schemas["GarminRacePrediction"];
export type GarminExportResponse = Schemas["GarminExportResponse"];

const API_BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function errorDetail(payload: unknown, fallback: string): string {
  if (typeof payload === "string" && payload.trim()) return payload;
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    const detail = record.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) =>
          item && typeof item === "object" && "msg" in item
            ? String((item as { msg: unknown }).msg)
            : null,
        )
        .filter(Boolean);
      if (messages.length) return messages.join("; ");
    }
    if (typeof record.message === "string") return record.message;
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData) && init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      payload = await response.text();
    }
    throw new ApiError(
      response.status,
      errorDetail(payload, `${response.status} ${response.statusText}`),
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function queryString(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const serialized = search.toString();
  return serialized ? `?${serialized}` : "";
}

export type ActivityListParams = {
  limit?: number;
  offset?: number;
  sport?: string;
  q?: string;
  from?: string;
  to?: string;
  sort?: string;
};

export type ActivityPatch = {
  name?: string;
  is_race?: boolean;
};

export const api = {
  authStatus: () => request<AuthStatus>("/auth/status"),
  login: (password: string) =>
    request<AuthStatus>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  logout: () => request<AuthStatus>("/auth/logout", { method: "POST" }),

  systemStatus: () => request<SystemStatus>("/system/status"),

  weeklySummary: (weekStart?: string) =>
    request<WeeklySummary>(
      `/summary/weekly${queryString({
        week_start: weekStart,
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      })}`,
    ),

  activities: (params: ActivityListParams = {}) =>
    request<ActivityList>(`/activities${queryString(params)}`),

  activity: (id: number | string) => request<ActivityDetail>(`/activities/${id}`),

  streams: (id: number | string, maxPoints = 1500) =>
    request<ActivityStreams>(`/activities/${id}/streams?max_points=${maxPoints}`),

  patchActivity: (id: number | string, patch: ActivityPatch) =>
    request<ActivityDetail>(`/activities/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  audit: () => request<AuditReport>("/audit"),

  syncStatus: () => request<SyncStatus>("/sync/status"),
  startSync: (mode: "incremental" | "backfill") =>
    request<StartSyncResponse>("/sync", {
      method: "POST",
      body: JSON.stringify({ mode }),
    }),

  imports: () => request<ImportRun[]>("/imports?limit=20"),
  uploadFiles: (files: File[]) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    return request<ImportResponse>("/imports", { method: "POST", body: form });
  },
  uploadGarminExport: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<GarminExportResponse>("/imports/garmin-export", {
      method: "POST",
      body: form,
    });
  },

  performance: () => request<PerformanceOverview>("/performance"),
  recomputePerformance: () =>
    request<PerformanceRecomputeResponse>("/performance/recompute", { method: "POST" }),
  performanceHistory: (days = 180) =>
    request<PerformanceHistory>(`/performance/history?days=${days}`),
  performanceGoals: () => request<PerformanceGoal[]>("/performance/goals"),
  upsertGoal: (distanceKey: string, goal: GoalUpsert) =>
    request<PerformanceGoal>(`/performance/goals/${distanceKey}`, {
      method: "PUT",
      body: JSON.stringify(goal),
    }),
  deleteGoal: (distanceKey: string) =>
    request<void>(`/performance/goals/${distanceKey}`, { method: "DELETE" }),
  garminReference: () => request<GarminReference>("/performance/reference"),
};
