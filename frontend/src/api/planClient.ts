import {
  queryString,
  request,
  requestBlob,
  type RegisteredPlan,
  type RegisteredPlanActivation,
  type RegisteredPlanBulk,
  type RegisteredPlanBulkResult,
  type RegisteredPlanCreate,
  type RegisteredPlanDetail,
  type RegisteredPlanFromSuggested,
  type RegisteredPlanImportResult,
  type RegisteredPlanSession,
  type RegisteredPlanSessionCreate,
  type RegisteredPlanSessionUpdate,
  type RegisteredPlanUpdate,
} from "./client";

function timezoneOffset(): number {
  return -new Date().getTimezoneOffset();
}

export const planApi = {
  plans: (includeArchived = false) =>
    request<RegisteredPlan[]>(
      `/training-plans${queryString({
        include_archived: includeArchived ? "true" : undefined,
      })}`,
    ),
  plan: (id: number) => request<RegisteredPlanDetail>(`/training-plans/${id}`),
  createPlan: (payload: RegisteredPlanCreate) =>
    request<RegisteredPlan>("/training-plans", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updatePlan: (id: number, patch: RegisteredPlanUpdate) =>
    request<RegisteredPlanDetail>(`/training-plans/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deletePlan: (id: number) => request<void>(`/training-plans/${id}`, { method: "DELETE" }),
  activatePlan: (id: number) =>
    request<RegisteredPlanActivation>(`/training-plans/${id}/activate`, { method: "POST" }),
  archivePlan: (id: number) =>
    request<RegisteredPlan>(`/training-plans/${id}/archive`, { method: "POST" }),
  createPlanFromSuggested: (payload: RegisteredPlanFromSuggested) =>
    request<RegisteredPlanDetail>(
      `/training-plans/from-suggested${queryString({
        tz_offset_minutes: timezoneOffset(),
      })}`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  createSession: (planId: number, payload: RegisteredPlanSessionCreate) =>
    request<RegisteredPlanSession>(`/training-plans/${planId}/sessions`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateSession: (
    planId: number,
    sessionId: number,
    patch: RegisteredPlanSessionUpdate,
  ) =>
    request<RegisteredPlanSession>(`/training-plans/${planId}/sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteSession: (planId: number, sessionId: number) =>
    request<void>(`/training-plans/${planId}/sessions/${sessionId}`, {
      method: "DELETE",
    }),
  bulkSessions: (planId: number, payload: RegisteredPlanBulk) =>
    request<RegisteredPlanBulkResult>(`/training-plans/${planId}/sessions/bulk`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  linkActivity: (planId: number, sessionId: number, activityId: number) =>
    request<RegisteredPlanSession>(
      `/training-plans/${planId}/sessions/${sessionId}/activity`,
      {
        method: "POST",
        body: JSON.stringify({ activity_id: activityId }),
      },
    ),
  unlinkActivity: (planId: number, sessionId: number) =>
    request<RegisteredPlanSession>(
      `/training-plans/${planId}/sessions/${sessionId}/activity`,
      { method: "DELETE" },
    ),
  exportCsv: (planId: number) =>
    requestBlob(`/training-plans/${planId}/export.csv`, `plan-${planId}.csv`),
  importCsv: ({
    file,
    name,
    activate = false,
    dryRun = false,
  }: {
    file: File;
    name?: string;
    activate?: boolean;
    dryRun?: boolean;
  }) => {
    const form = new FormData();
    form.append("file", file);
    if (name?.trim()) form.append("name", name.trim());
    form.append("activate", String(activate));
    form.append("dry_run", String(dryRun));
    return request<RegisteredPlanImportResult>("/training-plans/import", {
      method: "POST",
      body: form,
    });
  },
};
