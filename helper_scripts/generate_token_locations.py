import os
import json

MAPS_FOLDER = "assets/maps"
OUTPUT_FILE = "assets/token_locations.json"

locations = {}

for filename in os.listdir(MAPS_FOLDER):
    if not filename.endswith(".json"):
        continue
    with open(os.path.join(MAPS_FOLDER, filename)) as f:
        region = json.load(f)
        area = region.get("area")
        if not area:
            continue

        area_coords = {}
        for node in region.get("nodes", []):
            label = node.get("id")
            x = node.get("x", 0)
            y = node.get("y", 0)
            area_coords[label] = [x, y]

        locations[area] = area_coords

with open(OUTPUT_FILE, "w") as out:
    json.dump(locations, out, indent=2)

print(f"✅ Token coordinates exported to {OUTPUT_FILE}")