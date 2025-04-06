import os
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://mikesrpgcenter.com/bgate/maps/"
MAP_PAGES = [
    "candlekeep.html",
    "library.html"
]

SAVE_FOLDER = "assets/images/candlekeep_maps"
os.makedirs(SAVE_FOLDER, exist_ok=True)

def download_map_images():
    for page in MAP_PAGES:
        url = BASE_URL + page
        print(f"🔍 Scraping: {url}")
        response = requests.get(url)
        soup = BeautifulSoup(response.content, "html.parser")
        images = soup.find_all("img")

        for img in images:
            src = img.get("src")
            if src and (".gif" in src or ".jpg" in src or ".png" in src):
                # Normalize relative paths
                img_url = src if "http" in src else BASE_URL + src
                filename = os.path.basename(img_url)
                save_path = os.path.join(SAVE_FOLDER, filename)

                print(f"⬇️ Downloading: {img_url}")
                img_data = requests.get(img_url).content
                with open(save_path, "wb") as f:
                    f.write(img_data)
                print(f"✅ Saved to: {save_path}")

download_map_images()