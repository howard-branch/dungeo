import os
import requests
from PIL import Image
from dotenv import load_dotenv
import os

env_path = os.path.join(os.path.dirname(__file__), 'config', '.env')
load_dotenv(dotenv_path=env_path)

FOUNDRY_URL = os.getenv("FOUNDRY_API_URL")
API_KEY = os.getenv("FOUNDRY_API_KEY")
print("URL:", FOUNDRY_URL)

MAP_FOLDER = "assets/images/candlekeep_maps"
REMOTE_IMG_PATH = "maps/candlekeep_maps"  # relative to Foundry's data

def get_image_size(path):
    with Image.open(path) as img:
        return img.size  # (width, height)

def create_scene(name, img_path, width, height, grid=100):
    payload = {
        "name": name,
        "img": img_path,
        "width": width,
        "height": height,
        "grid": grid
    }

    headers = {"Authorization": f"Bearer {API_KEY}"}
    r = requests.post(f"{FOUNDRY_URL}/api/scenes", json=payload, headers=headers)

    if r.status_code == 200:
        print(f"✅ Scene created: {name}")
    else:
        print(f"❌ Failed to create {name}: {r.text}")

def create_all_scenes():
    for filename in os.listdir(MAP_FOLDER):
        if not filename.endswith(".png"):
            continue

        base_name = os.path.splitext(filename)[0]
        local_path = os.path.join(MAP_FOLDER, filename)
        remote_path = f"{REMOTE_IMG_PATH}/{filename}"

        width, height = get_image_size(local_path)
        create_scene(name=base_name.title(), img_path=remote_path, width=width, height=height)

if __name__ == "__main__":
    create_all_scenes()