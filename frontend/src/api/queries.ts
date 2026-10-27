import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import {
  api,
  type ActionUpsert,
  type ActivityListParams,
  type ActivityPatch,
  type GoalUpsert,
  type PlannedRaceCreate,
  type PlannedRaceUpdate,
  type ReportPeriod,
} from "./client";

export const queryKeys = {
  auth: ["auth"] as const,
  system: ["system"] as const,
  summary: (weekStart?: string) => ["summary", "weekly", weekStart ?? "current"] as const,
  activities: (params: ActivityListParams) => ["activities", params] as const,
  activity: (id: number | string) => ["activity", String(id)] as const,
  streams: (id: number | string) => ["activity", String(id), "streams"] as const,
  comparison: (leftId: number | string, rightId: number | string) =>
    ["comparison", String(leftId), String(rightId)] as const,
  audit: ["audit"] as const,
  sync: ["sync"] as const,
  imports: ["imports"] as const,
  performance: ["performance"] as const,
  performanceHistory: (days: number) => ["performance", "history", days] as const,
  performanceGoals: ["performance", "goals"] as const,
  performanceReference: ["performance", "reference"] as const,
  diagnostics: ["diagnostics"] as const,
  training: ["training"] as const,
  adherence: (weeks: number) => ["adherence", weeks] as const,
  progress: (days: number) => ["progress", days] as const,
  calendar: (start: string | undefined, weeks: number) =>
    ["calendar", start ?? "current", weeks] as const,
  report: (period: ReportPeriod, date: string | undefined) =>
    ["reports", period, date ?? "current"] as const,
  races: ["races"] as const,
  forecast: (weeks: 8 | 12) => ["forecast", weeks] as const,
  tracking: (days: number) => ["tracking", days] as const,
  briefing: ["briefing"] as const,
  paceHr: (days: number) => ["comparables", "pace-hr", days] as const,
  recovery: (days: number) => ["recovery", days] as const,
};

function invalidatePlanData(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: ["progress"] });
  void queryClient.invalidateQueries({ queryKey: ["calendar"] });
  void queryClient.invalidateQueries({ queryKey: ["reports"] });
  void queryClient.invalidateQueries({ queryKey: queryKeys.races });
  void queryClient.invalidateQueries({ queryKey: ["forecast"] });
  void queryClient.invalidateQueries({ queryKey: ["tracking"] });
  void queryClient.invalidateQueries({ queryKey: ["adherence"] });
  void queryClient.invalidateQueries({ queryKey: queryKeys.briefing });
  void queryClient.invalidateQueries({ queryKey: ["comparables"] });
}

export function useAuthStatus() {
  return useQuery({
    queryKey: queryKeys.auth,
    queryFn: api.authStatus,
    retry: false,
    staleTime: 30_000,
  });
}

export function useSystemStatus() {
  return useQuery({
    queryKey: queryKeys.system,
    queryFn: api.systemStatus,
    staleTime: 30_000,
  });
}

export function useWeeklySummary(weekStart?: string) {
  return useQuery({
    queryKey: queryKeys.summary(weekStart),
    queryFn: () => api.weeklySummary(weekStart),
    staleTime: 60_000,
  });
}

export function useActivities(params: ActivityListParams) {
  return useQuery({
    queryKey: queryKeys.activities(params),
    queryFn: () => api.activities(params),
    staleTime: 30_000,
  });
}

export function useActivity(id: number | string | undefined) {
  return useQuery({
    queryKey: queryKeys.activity(id ?? "none"),
    queryFn: () => api.activity(id as number | string),
    enabled: id !== undefined && id !== "",
    staleTime: 60_000,
  });
}

export function useComparison(leftId?: number | string, rightId?: number | string) {
  return useQuery({
    queryKey: queryKeys.comparison(leftId ?? "none", rightId ?? "none"),
    queryFn: () => api.compareActivities(leftId as number | string, rightId as number | string),
    enabled:
      leftId !== undefined &&
      leftId !== "" &&
      rightId !== undefined &&
      rightId !== "" &&
      String(leftId) !== String(rightId),
    staleTime: 60_000,
  });
}

export function useStreams(id: number | string | undefined) {
  return useQuery({
    queryKey: queryKeys.streams(id ?? "none"),
    queryFn: () => api.streams(id as number | string),
    enabled: id !== undefined && id !== "",
    staleTime: 5 * 60_000,
  });
}

export function useAudit() {
  return useQuery({
    queryKey: queryKeys.audit,
    queryFn: api.audit,
    staleTime: 30_000,
  });
}

export function useBriefing() {
  return useQuery({
    queryKey: queryKeys.briefing,
    queryFn: api.briefing,
    staleTime: 60_000,
  });
}

export function useSyncStatus() {
  return useQuery({
    queryKey: queryKeys.sync,
    queryFn: api.syncStatus,
    staleTime: 10_000,
    refetchInterval: (query) =>
      query.state.data?.running ? 4_000 : query.state.error ? false : 60_000,
  });
}

export function useStartSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (mode: "incremental" | "backfill") => api.startSync(mode),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.sync });
    },
  });
}

export function usePatchActivity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number | string; patch: ActivityPatch }) =>
      api.patchActivity(id, patch),
    onSuccess: (detail) => {
      queryClient.setQueryData(queryKeys.activity(detail.id), detail);
      void queryClient.invalidateQueries({ queryKey: ["activities"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.audit });
      void queryClient.invalidateQueries({ queryKey: ["summary"] });
      void queryClient.invalidateQueries({ queryKey: ["comparison"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.system });
      void queryClient.invalidateQueries({ queryKey: queryKeys.performance });
      void queryClient.invalidateQueries({ queryKey: ["performance", "history"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.diagnostics });
      void queryClient.invalidateQueries({ queryKey: queryKeys.training });
      invalidatePlanData(queryClient);
    },
  });
}

export function useImports() {
  return useQuery({
    queryKey: queryKeys.imports,
    queryFn: api.imports,
    staleTime: 30_000,
  });
}

export function useImportFiles() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => api.uploadFiles(files),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.imports });
      void queryClient.invalidateQueries({ queryKey: ["activities"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.audit });
      void queryClient.invalidateQueries({ queryKey: ["summary"] });
      void queryClient.invalidateQueries({ queryKey: ["comparison"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.system });
      void queryClient.invalidateQueries({ queryKey: queryKeys.performance });
      void queryClient.invalidateQueries({ queryKey: ["performance", "history"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.diagnostics });
      void queryClient.invalidateQueries({ queryKey: queryKeys.training });
      invalidatePlanData(queryClient);
    },
  });
}

export function usePerformance() {
  return useQuery({
    queryKey: queryKeys.performance,
    queryFn: api.performance,
    staleTime: 60_000,
  });
}

export function usePerformanceHistory(days = 180) {
  return useQuery({
    queryKey: queryKeys.performanceHistory(days),
    queryFn: () => api.performanceHistory(days),
    staleTime: 60_000,
  });
}

export function usePerformanceGoals() {
  return useQuery({
    queryKey: queryKeys.performanceGoals,
    queryFn: api.performanceGoals,
    staleTime: 60_000,
  });
}

export function useGarminReference() {
  return useQuery({
    queryKey: queryKeys.performanceReference,
    queryFn: api.garminReference,
    staleTime: 60_000,
  });
}

export function useDiagnostics() {
  return useQuery({
    queryKey: queryKeys.diagnostics,
    queryFn: api.diagnostics,
    staleTime: 60_000,
  });
}

export function useTraining() {
  return useQuery({
    queryKey: queryKeys.training,
    queryFn: api.training,
    staleTime: 60_000,
  });
}

export function useRecomputePerformance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.recomputePerformance,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.performance });
      void queryClient.invalidateQueries({ queryKey: ["performance", "history"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.diagnostics });
      void queryClient.invalidateQueries({ queryKey: queryKeys.training });
      invalidatePlanData(queryClient);
    },
  });
}

export function useUpsertGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ distanceKey, goal }: { distanceKey: string; goal: GoalUpsert }) =>
      api.upsertGoal(distanceKey, goal),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.performance });
      void queryClient.invalidateQueries({ queryKey: queryKeys.performanceGoals });
      void queryClient.invalidateQueries({ queryKey: ["performance", "history"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.diagnostics });
      void queryClient.invalidateQueries({ queryKey: queryKeys.training });
      invalidatePlanData(queryClient);
    },
  });
}

export function useDeleteGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (distanceKey: string) => api.deleteGoal(distanceKey),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.performance });
      void queryClient.invalidateQueries({ queryKey: queryKeys.performanceGoals });
      void queryClient.invalidateQueries({ queryKey: ["performance", "history"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.diagnostics });
      void queryClient.invalidateQueries({ queryKey: queryKeys.training });
      invalidatePlanData(queryClient);
    },
  });
}

export function useImportGarminExport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => api.uploadGarminExport(file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.imports });
      void queryClient.invalidateQueries({ queryKey: ["activities"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.audit });
      void queryClient.invalidateQueries({ queryKey: queryKeys.performance });
      void queryClient.invalidateQueries({ queryKey: queryKeys.performanceReference });
      void queryClient.invalidateQueries({ queryKey: ["performance", "history"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.diagnostics });
      void queryClient.invalidateQueries({ queryKey: queryKeys.training });
      void queryClient.invalidateQueries({ queryKey: ["recovery"] });
      invalidatePlanData(queryClient);
    },
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (password: string) => api.login(password),
    onSuccess: (status) => {
      queryClient.setQueryData(queryKeys.auth, status);
      void queryClient.invalidateQueries();
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.clear();
    },
  });
}

export function useProgress(days = 180) {
  return useQuery({
    queryKey: queryKeys.progress(days),
    queryFn: () => api.progress(days),
    staleTime: 60_000,
  });
}

export function useCalendar(start?: string, weeks = 6) {
  return useQuery({
    queryKey: queryKeys.calendar(start, weeks),
    queryFn: () => api.calendar(start, weeks),
    staleTime: 30_000,
  });
}

export function useReport(period: ReportPeriod, date?: string) {
  return useQuery({
    queryKey: queryKeys.report(period, date),
    queryFn: () => api.report(period, date),
    staleTime: 30_000,
  });
}

export function useRaces() {
  return useQuery({
    queryKey: queryKeys.races,
    queryFn: api.races,
    staleTime: 30_000,
  });
}

export function useCreateRace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PlannedRaceCreate) => api.createRace(payload),
    onSuccess: () => invalidatePlanData(queryClient),
  });
}

export function useUpdateRace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: PlannedRaceUpdate }) =>
      api.updateRace(id, patch),
    onSuccess: () => invalidatePlanData(queryClient),
  });
}

export function useDeleteRace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteRace(id),
    onSuccess: () => invalidatePlanData(queryClient),
  });
}

export function useForecast(weeks: 8 | 12 = 8) {
  return useQuery({
    queryKey: queryKeys.forecast(weeks),
    queryFn: () => api.forecast(weeks),
    staleTime: 60_000,
  });
}

export function useAdherence(weeks = 8) {
  return useQuery({
    queryKey: queryKeys.adherence(weeks),
    queryFn: () => api.adherence(weeks),
    staleTime: 60_000,
  });
}

export function useTracking(days = 180) {
  return useQuery({
    queryKey: queryKeys.tracking(days),
    queryFn: () => api.tracking(days),
    staleTime: 60_000,
  });
}

export function useUpsertTrackingAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ dimensionKey, payload }: { dimensionKey: string; payload: ActionUpsert }) =>
      api.upsertTrackingAction(dimensionKey, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tracking"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.diagnostics });
    },
  });
}

export function useDeleteTrackingAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (dimensionKey: string) => api.deleteTrackingAction(dimensionKey),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tracking"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.diagnostics });
    },
  });
}

export function usePaceHr(days = 180) {
  return useQuery({
    queryKey: queryKeys.paceHr(days),
    queryFn: () => api.paceHr(days),
    staleTime: 60_000,
  });
}

export function useRecovery(days = 90) {
  return useQuery({
    queryKey: queryKeys.recovery(days),
    queryFn: () => api.recovery(days),
    staleTime: 60_000,
  });
}
