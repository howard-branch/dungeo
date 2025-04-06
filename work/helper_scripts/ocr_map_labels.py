import os
import cv2
import pytesseract
import json
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"D:\Program Files\Tesseract-OCR\tesseract.exe"

IMAGE_FOLDER = "assets/images/candlekeep_maps"
OUTPUT_JSON = "assets/token_locations.json"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif")

locations_by_map = {}

for filename in os.listdir(IMAGE_FOLDER):
    if not filename.lower().endswith(IMAGE_EXTS):
        continue

    file_path = os.path.join(IMAGE_FOLDER, filename)
    base_name, ext = os.path.splitext(filename)
    map_name = base_name.replace("-", "_").replace(" ", "_").title()

    # ✅ Convert to PNG if not already
    if ext.lower() != ".png":
        png_path = os.path.join(IMAGE_FOLDER, base_name + ".png")
        print(f"🔁 Converting {filename} → {base_name}.png")
        try:
            with Image.open(file_path) as im:
                im.convert("RGB").save(png_path)
            file_path = png_path
        except Exception as e:
            print(f"❌ Failed to convert {filename} to PNG: {e}")
            continue

    # 🔍 OCR this PNG image
    print(f"🔍 Processing: {os.path.basename(file_path)}")
    img = cv2.imread(file_path)
    if img is None:
        print(f"❌ Failed to load: {file_path}")
        continue

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)[1]

    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
    coords = {}

    for i, word in enumerate(data["text"]):
        word_clean = word.strip().lower().replace(" ", "_")
        if len(word_clean) < 3 or not word_clean.isalnum():
            continue

        x = data["left"][i] + data["width"][i] // 2
        y = data["top"][i] + data["height"][i] // 2
        coords[word_clean] = [x, y]
        print(f"📍 {map_name}: '{word}' → ({x}, {y})")

    if coords:
        locations_by_map[map_name] = coords

# ✅ Save the final token_locations.json
os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
with open(OUTPUT_JSON, "w") as f:
    json.dump(locations_by_map, f, indent=2)

print(f"\n✅ All token locations saved to {OUTPUT_JSON}")