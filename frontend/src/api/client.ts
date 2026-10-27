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
export type AnalysisSettings = Schemas["AnalysisSettingsOut"];
export type AnalysisSettingsValues = Schemas["AnalysisSettingsValuesOut"];
export type AnalysisSettingsUpdate = Schemas["AnalysisSettingsUpdate"];
export type AnalysisClassificationMode = "auto" | "pace" | "hr";
export type ActivityClassification = Schemas["ActivityClassificationOut"];
export type DiagnosticsOverview = Schemas["DiagnosticsOverview"];
export type AnalysisDimension = Schemas["DimensionOut"];
export type AnalysisLimiter = Schemas["LimiterOut"];
export type AnalysisIntensity = Schemas["IntensityOut"];
export type AnalysisIntensityBucket = Schemas["IntensityBucketOut"];
export type AnalysisIntensityTarget = Schemas["IntensityTargetOut"];
export type AnalysisLoad = Schemas["LoadOut"];
export type WeeklyLoad = Schemas["WeeklyLoadOut"];
export type AnalysisCoverage = Schemas["AnalysisCoverageOut"];
export type AnalysisReference = Schemas["AnalysisReferenceOut"];
export type TrainingPlan = Schemas["TrainingPlan"];
export type RegisteredPlan = Schemas["TrainingPlanOut"];
export type RegisteredPlanDetail = Schemas["TrainingPlanDetailOut"];
export type RegisteredPlanCreate = Schemas["TrainingPlanCreate"];
export type RegisteredPlanUpdate = Schemas["TrainingPlanUpdate"];
export type RegisteredPlanSession = Schemas["TrainingPlanSessionOut"];
export type RegisteredPlanSessionCreate = Schemas["TrainingPlanSessionCreate"];
export type RegisteredPlanSessionUpdate = Schemas["TrainingPlanSessionUpdate"];
export type RegisteredPlanBulk = Schemas["TrainingPlanSessionsBulk"];
export type RegisteredPlanBulkResult = Schemas["TrainingPlanBulkOut"];
export type RegisteredPlanFromSuggested = Schemas["TrainingPlanFromSuggested"];
export type RegisteredPlanActivation = Schemas["TrainingPlanActivationOut"];
export type CalendarPlan = Schemas["CalendarActivePlanOut"];
export type AdherenceSessionItem = Schemas["AdherenceSessionItemOut"];
export type TrainingFocus = Schemas["TrainingFocusOut"];
export type TrainingSession = Schemas["TrainingSessionOut"];
export type TrainingLoadTarget = Schemas["TrainingLoadTargetOut"];
export type ProgressOverview = Schemas["ProgressOverview"];
export type ProgressTotals = Schemas["ProgressTotalsOut"];
export type ProgressWeek = Schemas["ProgressWeekOut"];
export type ProgressConsistency = Schemas["ConsistencyOut"];
export type FitnessPoint = Schemas["FitnessPointOut"];
export type PersonalBest = Schemas["PersonalBestOut"];
export type GoalProgress = Schemas["GoalProgressOut"];
export type ProgressHighlight = Schemas["ProgressHighlightOut"];
export type PlannedRace = Schemas["PlannedRaceOut"];
export type PlannedRaceCreate = Schemas["PlannedRaceCreate"];
export type PlannedRaceUpdate = Schemas["PlannedRaceUpdate"];
export type CalendarView = Schemas["CalendarView"];
export type CalendarWeek = Schemas["CalendarWeekOut"];
export type CalendarDay = Schemas["CalendarDayOut"];
export type CalendarEntry = Schemas["CalendarEntryOut"];
export type AdherenceOverview = Schemas["AdherenceOverview"];
export type AdherenceWeek = Schemas["AdherenceWeekOut"];
export type AdherenceSummary = Schemas["AdherenceSummaryOut"];
export type ReportPeriod = "week" | "month";
export type Report = Schemas["ReportOut"];
export type ReportNarrative = Schemas["ReportNarrativeOut"];
export type ForecastView = Schemas["ForecastView"];
export type ForecastGoal = Schemas["ForecastGoalOut"];
export type ForecastBaseline = Schemas["ForecastBaselineOut"];
export type ForecastScenario = Schemas["ScenarioOut"];
export type ScenarioProjection = Schemas["ScenarioProjectionOut"];
export type TrackingOverview = Schemas["TrackingOverview"];
export type DriverAnalysis = Schemas["DriverAnalysisOut"];
export type Driver = Schemas["DriverOut"];
export type PredictionAccuracy = Schemas["PredictionAccuracyOut"];
export type AccuracySample = Schemas["AccuracySampleOut"];
export type AccuracySummary = Schemas["AccuracySummaryOut"];
export type GoalTracking = Schemas["GoalTrackingOut"];
export type GoalHistoryPoint = Schemas["GoalHistoryPointOut"];
export type GoalResult = Schemas["GoalResultOut"];
export type GoalRevision = Schemas["GoalRevisionOut"];
export type TrackedAction = Schemas["TrackedActionOut"];
export type ActionUpsert = Schemas["ActionUpsert"];
export type ActionSuggestion = Schemas["ActionSuggestionOut"];
export type RecoveryOverview = Schemas["RecoveryOverview"];
export type RecoveryMetric = Schemas["RecoveryMetricOut"];
export type RecoveryMetricPoint = Schemas["RecoveryMetricPointOut"];
export type ComparisonView = Schemas["ComparisonView"];
export type ComparisonSide = Schemas["ComparisonSideOut"];
export type ComparisonMetric = Schemas["ComparisonMetricOut"];
export type ComparisonSplit = Schemas["ComparisonSplitOut"];
export type ComparisonInsight = Schemas["ComparisonInsightOut"];
export type PaceHrAnalysis = Schemas["PaceHrAnalysisOut"];
export type PaceHrGroup = Schemas["PaceHrGroupOut"];
export type PaceHrPoint = Schemas["PaceHrPointOut"];
export type PaceHrLine = Schemas["PaceHrLineOut"];
export type BriefingView = Schemas["BriefingView"];
export type BriefingTrend = Schemas["BriefingTrendOut"];
export type BriefingDistance = Schemas["BriefingDistanceOut"];
export type BriefingSignal = Schemas["BriefingSignalOut"];
export type BriefingInsight = Schemas["BriefingInsightOut"];
export type BriefingAction = Schemas["BriefingActionOut"];

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

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
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

export function queryString(params: Record<string, string | number | undefined | null>): string {
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
  intensity_override?: "easy" | "moderate" | "hard" | null;
  rpe?: number | null;
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

  compareActivities: (leftId: number | string, rightId: number | string) =>
    request<ComparisonView>(
      `/activities/compare?left_id=${encodeURIComponent(String(leftId))}&right_id=${encodeURIComponent(
        String(rightId),
      )}`,
    ),

  streams: (id: number | string, maxPoints = 1500) =>
    request<ActivityStreams>(`/activities/${id}/streams?max_points=${maxPoints}`),

  patchActivity: (id: number | string, patch: ActivityPatch) =>
    request<ActivityDetail>(`/activities/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  audit: () => request<AuditReport>("/audit"),
  briefing: () =>
    request<BriefingView>(
      `/briefing${queryString({
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      })}`,
    ),

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

  diagnostics: () =>
    request<DiagnosticsOverview>(
      `/diagnostics${queryString({
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      })}`,
    ),
  analysisSettings: () => request<AnalysisSettings>("/analysis/settings"),
  updateAnalysisSettings: (payload: AnalysisSettingsUpdate) =>
    request<AnalysisSettings>("/analysis/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  training: () =>
    request<TrainingPlan>(
      `/training${queryString({
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      })}`,
    ),

  progress: (days = 180) =>
    request<ProgressOverview>(
      `/progress${queryString({
        days,
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      })}`,
    ),
  calendar: (start?: string, weeks = 6) =>
    request<CalendarView>(
      `/calendar${queryString({
        start,
        weeks,
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      })}`,
    ),
  report: (period: ReportPeriod, date?: string) =>
    request<Report>(
      `/reports${queryString({
        period,
        date,
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      })}`,
    ),
  races: () =>
    request<PlannedRace[]>(
      `/races${queryString({
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      })}`,
    ),
  createRace: (payload: PlannedRaceCreate) =>
    request<PlannedRace>(
      `/races${queryString({
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      })}`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  updateRace: (id: number, patch: PlannedRaceUpdate) =>
    request<PlannedRace>(
      `/races/${id}${queryString({
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      })}`,
      { method: "PATCH", body: JSON.stringify(patch) },
    ),
  deleteRace: (id: number) => request<void>(`/races/${id}`, { method: "DELETE" }),

  forecast: (weeks: 8 | 12 = 8) =>
    request<ForecastView>(
      `/forecast${queryString({
        weeks,
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      })}`,
    ),
  adherence: (weeks = 8) =>
    request<AdherenceOverview>(
      `/adherence${queryString({
        weeks,
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      })}`,
    ),
  tracking: (days = 180) =>
    request<TrackingOverview>(
      `/tracking${queryString({
        days,
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      })}`,
    ),
  upsertTrackingAction: (dimensionKey: string, payload: ActionUpsert) =>
    request<TrackedAction>(
      `/tracking/actions/${dimensionKey}${queryString({
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      })}`,
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  deleteTrackingAction: (dimensionKey: string) =>
    request<void>(`/tracking/actions/${dimensionKey}`, { method: "DELETE" }),
  paceHr: (days = 180) =>
    request<PaceHrAnalysis>(
      `/comparables/pace-hr${queryString({
        days,
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      })}`,
    ),
  recovery: (days = 90) =>
    request<RecoveryOverview>(
      `/recovery${queryString({
        days,
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      })}`,
    ),
};
