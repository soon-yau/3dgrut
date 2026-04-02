import type { SfmBackendId, SfmBackendInfo } from "../types/sfm";
import { api } from "./client";

export function getSfmBackends() {
  return api<SfmBackendInfo[]>("/api/sfm/backends");
}

export function startSfm(projectId: string, backend: SfmBackendId, params: Record<string, unknown> = {}) {
  return api<{ status: string }>(`/api/projects/${projectId}/sfm/start`, {
    method: "POST",
    body: JSON.stringify({ backend, params }),
  });
}

export function sfmStatus(projectId: string) {
  return api<{ ready: boolean; n_cameras: number; n_points: number; backend: string | null }>(
    `/api/projects/${projectId}/sfm/status`
  );
}

export function sfmPointcloud(projectId: string) {
  return api<{ positions: number[][]; colors: number[][] }>(`/api/projects/${projectId}/sfm/pointcloud`);
}
