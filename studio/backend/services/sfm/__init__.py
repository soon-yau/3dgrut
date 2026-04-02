from studio.backend.services.sfm.base import SfMBackend
from studio.backend.services.sfm.colmap_global import ColmapGlobalBackend
from studio.backend.services.sfm.colmap_incremental import ColmapIncrementalBackend
from studio.backend.services.sfm.mast3r import Mast3rBackend

BACKENDS: dict[str, SfMBackend] = {
    "colmap_incremental": ColmapIncrementalBackend(),
    "colmap_global": ColmapGlobalBackend(),
    "mast3r": Mast3rBackend(),
}

__all__ = ["BACKENDS", "SfMBackend", "ColmapIncrementalBackend", "ColmapGlobalBackend", "Mast3rBackend"]
