import os
import json
import zipfile
from PIL import Image
from shutil import copyfile

# === Configurable paths ===
MAP_SRC_FOLDER = "assets/images/candlekeep_maps"     # Where your raw maps are
MAP_OUT_FOLDER = "maps/candlekeep_maps"              # Where Foundry expects maps
MANIFEST_OUT_PATH = "assets/scene_manifest.json"     # Where Foundry expects the manifest
ZIP_OUT_PATH = "foundry-scene-assets.zip"            # Output zip file

# === Build temp structure ===
BUILD_ROOT = "build-temp"
MAP_BUILD = os.path.join(BUILD_ROOT, MAP_OUT_FOLDER)
MANIFEST_BUILD = os.path.join(BUILD_ROOT, MANIFEST_OUT_PATH)

# Ensure folders exist
os.makedirs(MAP_BUILD, exist_ok=True)
os.makedirs(os.path.dirname(MANIFEST_BUILD), exist_ok=True)

# === Build scene data and copy maps ===
scenes = []

def get_image_size(path):
    with Image.open(path) as img:
        return img.size

for filename in os.listdir(MAP_SRC_FOLDER):
    if not filename.lower().endswith(".png"):
        continue

    src_path = os.path.join(MAP_SRC_FOLDER, filename)
    dst_path = os.path.join(MAP_BUILD, filename)
    copyfile(src_path, dst_path)

    width, height = get_image_size(src_path)
    scenes.append({
        "name": os.path.splitext(filename)[0].replace("_", " ").title(),
        "img": f"{MAP_OUT_FOLDER}/{filename}",
        "width": width,
        "height": height,
        "grid": 100,
        "navigation": True
    })

# Write manifest
with open(MANIFEST_BUILD, "w") as f:
    json.dump(scenes, f, indent=2)

print(f"✅ Manifest written to {MANIFEST_BUILD}")

# === Create ZIP ===
with zipfile.ZipFile(ZIP_OUT_PATH, "w", zipfile.ZIP_DEFLATED) as zipf:
    for root, _, files in os.walk(BUILD_ROOT):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, BUILD_ROOT)
            zipf.write(full_path, arcname=rel_path)

print(f"✅ ZIP created: {ZIP_OUT_PATH}")
