import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  type ActivityListParams,
  type ActivityPatch,
  type GoalUpsert,
} from "./client";

export const queryKeys = {
  auth: ["auth"] as const,
  system: ["system"] as const,
  summary: (weekStart?: string) => ["summary", "weekly", weekStart ?? "current"] as const,
  activities: (params: ActivityListParams) => ["activities", params] as const,
  activity: (id: number | string) => ["activity", String(id)] as const,
  streams: (id: number | string) => ["activity", String(id), "streams"] as const,
  audit: ["audit"] as const,
  sync: ["sync"] as const,
  imports: ["imports"] as const,
  performance: ["performance"] as const,
  performanceHistory: (days: number) => ["performance", "history", days] as const,
  performanceGoals: ["performance", "goals"] as const,
  performanceReference: ["performance", "reference"] as const,
};

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
      void queryClient.invalidateQueries({ queryKey: queryKeys.system });
      void queryClient.invalidateQueries({ queryKey: queryKeys.performance });
      void queryClient.invalidateQueries({ queryKey: ["performance", "history"] });
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
      void queryClient.invalidateQueries({ queryKey: queryKeys.system });
      void queryClient.invalidateQueries({ queryKey: queryKeys.performance });
      void queryClient.invalidateQueries({ queryKey: ["performance", "history"] });
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

export function useRecomputePerformance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.recomputePerformance,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.performance });
      void queryClient.invalidateQueries({ queryKey: ["performance", "history"] });
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
