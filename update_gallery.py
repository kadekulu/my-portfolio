import os
import json
import datetime
import time
import subprocess
import re
from dotenv import load_dotenv
from google import genai
from PIL import Image, ImageFilter

# .envファイルからAPIキーを読み込む
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODELS_TO_TRY = ["gemini-3-flash-preview", "gemini-2.0-flash", "gemini-1.5-flash"]
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

# 正解リスト
VALID_VOCABULARY = {
    "Hair Color": ["Pink Hair", "Blue Hair", "Blonde Hair", "White Hair", "Black Hair", "Silver Hair", "Brown Hair"],
    "Hair Style": ["Twin Tails", "Wavy Hair", "Straight Hair", "Pony Tail", "Short Hair", "Long Hair", "Medium Hair"],
    "Clothing": ["School Uniform", "Dress", "Lingerie", "Swimsuit", "Casual", "Gothic"],
    "Identity": ["Airi", "Original"]
}

def sanitize_tags(raw_text):
    if not raw_text: return []
    found_tags = []
    for category, options in VALID_VOCABULARY.items():
        matched = False
        for opt in options:
            if re.search(re.escape(opt), raw_text, re.IGNORECASE):
                found_tags.append(opt)
                matched = True
                break
        if not matched:
            if category == "Identity": found_tags.append("Original")
            else: found_tags.append("Other")
    return found_tags[:4]

def apply_watermark(image_path, logo_path="watermark_logo.png"):
    if not os.path.exists(logo_path): return False
    try:
        with Image.open(image_path) as temp_img:
            img = temp_img.copy()
        img = img.convert("RGBA")
        with Image.open(logo_path) as temp_logo:
            logo = temp_logo.copy()
        logo = logo.convert("RGBA")
        
        datas = logo.getdata()
        new_data = []
        for item in datas:
            if item[0] < 60 and item[1] < 60 and item[2] < 60: new_data.append((0, 0, 0, 0))
            else: new_data.append((255, 255, 255, 220))
        logo.putdata(new_data)

        target_width = int(img.size[0] * 0.20)
        logo = logo.resize((target_width, int(target_width * (logo.size[1]/logo.size[0]))), Image.Resampling.LANCZOS)
        
        shadow = Image.new("RGBA", logo.size, (0, 0, 0, 255))
        shadow.putalpha(logo.getchannel("A"))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=3))
        
        combined_logo = Image.new("RGBA", logo.size, (0, 0, 0, 0))
        combined_logo.paste(shadow, (3, 3), shadow)
        combined_logo.paste(logo, (0, 0), logo)
        
        img.paste(combined_logo, (img.size[0]-combined_logo.size[0]-40, img.size[1]-combined_logo.size[1]-40), combined_logo)
        
        if image_path.lower().endswith(('.jpg', '.jpeg')):
            img.convert("RGB").save(image_path, quality=95, subsampling=0)
        else:
            img.save(image_path)
        return True
    except: return False

def get_tags_with_retry(image_path):
    if not client: return None
    for model_name in MODELS_TO_TRY:
        try:
            print(f"    -> {model_name} で分析中...")
            prompt = (
                "Task: Classify this illustration.\n"
                "Constraints: Return EXACTLY 4 terms from the lists below, separated by commas.\n"
                f"1. Hair Color: {VALID_VOCABULARY['Hair Color']}\n"
                f"2. Hair Style: {VALID_VOCABULARY['Hair Style']}\n"
                f"3. Clothing: {VALID_VOCABULARY['Clothing']}\n"
                f"4. Identity: {VALID_VOCABULARY['Identity']}\n"
            )
            response = client.models.generate_content(model=model_name, contents=[prompt, Image.open(image_path)])
            if response and response.text:
                tags = sanitize_tags(response.text)
                print(f"    [確定] {tags}")
                return tags
        except: continue
    return None

def update_gallery():
    image_dir, output_file, cache_file = 'illustrations', 'data.js', 'tags_cache.json'
    if not os.path.exists(image_dir): os.makedirs(image_dir)
    
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            tags_cache = json.load(f)
    else:
        tags_cache = {}

    filenames = sorted([f for f in os.listdir(image_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))])
    artworks = []
    needs_processing = []
    
    for filename in filenames:
        path = os.path.join(image_dir, filename)
        tags = tags_cache.get(filename, [])
        mtime = os.path.getmtime(path)
        artworks.append({
            'filename': filename, 'title': os.path.splitext(filename)[0], 
            'date': datetime.datetime.fromtimestamp(mtime).strftime('%Y.%m.%d'),
            'tags': tags, 'timestamp': mtime
        })
        if not tags: needs_processing.append(filename)
    
    def save():
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("const ARTWORKS_DATA = ")
            json.dump(sorted(artworks, key=lambda x: x['timestamp'], reverse=True), f, ensure_ascii=False, indent=4)
            f.write(";")

    save()
    
    def deploy(msg):
        print(f"    [LOCAL] Git に変更を記録・送信中: {msg}")
        subprocess.run(['git', 'add', '.'], capture_output=True)
        subprocess.run(['git', 'commit', '-m', f"{msg}: {datetime.datetime.now().strftime('%H:%M:%S')}"], capture_output=True)
        subprocess.run(['git', 'push', 'origin', 'main'], capture_output=True)

    deploy("Update gallery data")
    
    if needs_processing:
        print(f"\nローカルでタグ付けを開始 (残り {len(needs_processing)} 枚)...")
        for filename in needs_processing[:5]:
            path = os.path.join(image_dir, filename)
            apply_watermark(path)
            new_tags = get_tags_with_retry(path)
            if new_tags:
                tags_cache[filename] = new_tags
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(tags_cache, f, ensure_ascii=False, indent=4)
                for art in artworks:
                    if art['filename'] == filename: art['tags'] = new_tags
                save()
                deploy(f"Processed: {filename}")
                time.sleep(2)
        return True
    return False

if __name__ == '__main__':
    update_gallery()
