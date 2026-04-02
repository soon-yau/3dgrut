export type SfmBackendId = "colmap_incremental" | "colmap_global" | "mast3r";

export interface SfmBackendInfo {
  id: SfmBackendId;
  display: string;
  available: boolean;
  requires_gpu: boolean;
  install_hint: string | null;
}
