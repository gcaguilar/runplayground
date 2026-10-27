import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  RegisteredPlanCreate,
  RegisteredPlanFromSuggested,
  RegisteredPlanSessionCreate,
  RegisteredPlanSessionUpdate,
  RegisteredPlanUpdate,
} from "./client";
import { planApi } from "./planClient";

export const planKeys = {
  list: (includeArchived: boolean) => ["plans", includeArchived] as const,
  detail: (id: number) => ["plan", id] as const,
};

function invalidatePlans(queryClient: ReturnType<typeof useQueryClient>, id?: number) {
  void queryClient.invalidateQueries({ queryKey: ["plans"] });
  if (id !== undefined) {
    void queryClient.invalidateQueries({ queryKey: planKeys.detail(id) });
  }
  void queryClient.invalidateQueries({ queryKey: ["calendar"] });
  void queryClient.invalidateQueries({ queryKey: ["adherence"] });
  void queryClient.invalidateQueries({ queryKey: ["training"] });
}

export function usePlans(includeArchived = false) {
  return useQuery({
    queryKey: planKeys.list(includeArchived),
    queryFn: () => planApi.plans(includeArchived),
    staleTime: 30_000,
  });
}

export function usePlan(id: number | null) {
  return useQuery({
    queryKey: planKeys.detail(id ?? -1),
    queryFn: () => planApi.plan(id as number),
    enabled: id !== null,
    staleTime: 15_000,
  });
}

export function useCreatePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RegisteredPlanCreate) => planApi.createPlan(payload),
    onSuccess: (plan) => invalidatePlans(queryClient, plan.id),
  });
}

export function useUpdatePlan(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: RegisteredPlanUpdate) => planApi.updatePlan(id, patch),
    onSuccess: () => invalidatePlans(queryClient, id),
  });
}

export function useDeletePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => planApi.deletePlan(id),
    onSuccess: () => invalidatePlans(queryClient),
  });
}

export function useActivatePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => planApi.activatePlan(id),
    onSuccess: () => invalidatePlans(queryClient),
  });
}

export function useArchivePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => planApi.archivePlan(id),
    onSuccess: (_plan, id) => invalidatePlans(queryClient, id),
  });
}

export function useCreatePlanFromSuggested() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RegisteredPlanFromSuggested) =>
      planApi.createPlanFromSuggested(payload),
    onSuccess: (plan) => invalidatePlans(queryClient, plan.id),
  });
}

export function useCreateSession(planId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RegisteredPlanSessionCreate) =>
      planApi.createSession(planId, payload),
    onSuccess: () => invalidatePlans(queryClient, planId),
  });
}

export function useUpdateSession(planId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      sessionId,
      patch,
    }: {
      sessionId: number;
      patch: RegisteredPlanSessionUpdate;
    }) => planApi.updateSession(planId, sessionId, patch),
    onSuccess: () => invalidatePlans(queryClient, planId),
  });
}

export function useDeleteSession(planId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: number) => planApi.deleteSession(planId, sessionId),
    onSuccess: () => invalidatePlans(queryClient, planId),
  });
}

export function useBulkSessions(planId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessions: RegisteredPlanSessionCreate[]) =>
      planApi.bulkSessions(planId, { sessions }),
    onSuccess: () => invalidatePlans(queryClient, planId),
  });
}

export function useLinkActivity(planId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      sessionId,
      activityId,
    }: {
      sessionId: number;
      activityId: number;
    }) => planApi.linkActivity(planId, sessionId, activityId),
    onSuccess: () => invalidatePlans(queryClient, planId),
  });
}

export function useUnlinkActivity(planId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: number) => planApi.unlinkActivity(planId, sessionId),
    onSuccess: () => invalidatePlans(queryClient, planId),
  });
}
