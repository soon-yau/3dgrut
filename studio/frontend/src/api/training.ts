import { api } from "./client";

export function startTraining(
  projectId: string,
  body: {
    config_name?: string;
    experiment_name?: string;
    path?: string | null;
    n_iterations?: number | null;
    val_frequency?: number | null;
    num_workers?: number | null;
    use_wandb?: boolean;
    extra_overrides?: Record<string, unknown>;
  }
) {
  return api<{ run_id: string; status: string }>(`/api/projects/${projectId}/runs`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listRuns(projectId: string) {
  return api<
    {
      id: string;
      status: string;
      metrics_path: string | null;
      started_at: string | null;
      finished_at: string | null;
    }[]
  >(`/api/projects/${projectId}/runs`);
}
