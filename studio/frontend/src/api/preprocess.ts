import { api } from "./client";

export function uploadVideo(projectId: string, file: File) {
  const fd = new FormData();
  fd.append("file", file);
  return fetch(`/api/projects/${projectId}/upload`, {
    method: "POST",
    body: fd,
  }).then(async (r) => {
    if (!r.ok) throw new Error(await r.text());
    return r.json() as Promise<{ video_path: string }>;
  });
}

export function startPreprocess(
  projectId: string,
  body: {
    fps?: number;
    jpeg_quality?: number;
    time_start_s?: number;
    time_end_s?: number | null;
    scale_divisor?: number;
    blur_threshold?: number;
  }
) {
  return api<{ status: string }>(`/api/projects/${projectId}/preprocess/start`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listFrames(projectId: string) {
  return api<{ frames: string[]; blur_scores: Record<string, number> }>(`/api/projects/${projectId}/frames`);
}
