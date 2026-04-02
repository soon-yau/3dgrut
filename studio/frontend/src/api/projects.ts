import { api } from "./client";

export interface Project {
  id: string;
  name: string;
  status: string;
  video_path: string | null;
  sfm_path: string | null;
  sfm_backend: string | null;
  created_at: string;
}

export function listProjects() {
  return api<Project[]>("/api/projects");
}

export function createProject(name: string) {
  return api<Project>("/api/projects", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function deleteProject(id: string) {
  return api<{ status: string }>(`/api/projects/${id}`, { method: "DELETE" });
}
