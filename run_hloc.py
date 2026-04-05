import os
import pycolmap
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

from hloc import extract_features, match_features, reconstruction
from hloc.extract_features import ImageDataset


def write_sequence_pairs(
    output: Path,
    image_dir: Path,
    *,
    overlap: int = 10,
    quadratic_overlap: bool = True,
    preprocessing_conf: Optional[Dict] = None,
) -> None:
    """Sequential/video pairs file (hloc dropped pairs_from_sequence; same role as the old helper)."""
    prep = preprocessing_conf or {
        "grayscale": True,
        "resize_max": 1600,
        "resize_force": True,
    }
    names = ImageDataset(image_dir, prep).names
    n = len(names)
    pairs: Set[Tuple[str, str]] = set()
    for i in range(n):
        for k in range(1, overlap + 1):
            j = i + k
            if j < n:
                pairs.add((names[i], names[j]))
        if quadratic_overlap:
            kk = 2
            while i + kk < n:
                if kk > overlap:
                    pairs.add((names[i], names[i + kk]))
                kk *= 2
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        f.write("\n".join(f"{a} {b}" for a, b in sorted(pairs)))


# 1. Define your paths (Safely creating the directory first)
images_dir = Path('/workspace/gym_empty/images')
outputs = Path('/workspace/gym_empty/hloc_output')
if outputs.is_file():
    os.remove(outputs)
outputs.mkdir(parents=True, exist_ok=True)

# Explicitly name the output files so hloc doesn't confuse files with folders
feature_path = outputs / 'features.h5'
match_path = outputs / 'matches.h5'
sfm_pairs = outputs / 'pairs-sequence.txt'
sfm_dir = outputs / 'sparse/0'

# 2. Configuration
feature_conf = extract_features.confs['superpoint_max']
matcher_conf = match_features.confs['superglue']
# Force the neural network to use the indoor weights
matcher_conf['model']['weights'] = 'indoor'

# 3. Run the AI Pipeline
print("Extracting SuperPoint features...")
extract_features.main(feature_conf, images_dir, image_list=None, feature_path=feature_path)

print("Pairing sequential video frames...")
write_sequence_pairs(
    sfm_pairs,
    images_dir,
    overlap=10,
    quadratic_overlap=True,
    preprocessing_conf=feature_conf["preprocessing"],
)

print("Matching with SuperGlue...")
match_features.main(matcher_conf, sfm_pairs, features=feature_path, matches=match_path)

print("Running COLMAP triangulation (Forcing PINHOLE)...")
image_opts = {'camera_model': 'PINHOLE'}
reconstruction.main(
    sfm_dir, 
    images_dir, 
    sfm_pairs, 
    feature_path, 
    match_path, 
    image_list=None, 
    camera_mode=pycolmap.CameraMode.SINGLE, 
    image_options=image_opts
)

print(f"Success! Your 3DGRUT-ready sparse folder is at: {sfm_dir}")