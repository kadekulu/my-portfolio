import os
import json
import datetime
import time
import subprocess
from dotenv import load_dotenv
from google import genai
from PIL import Image

# .envファイルからAPIキーを読み込む
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODELS_TO_TRY = [
    "gemini-3-flash-preview", 
    "gemini-2.0-flash", 
    "gemini-1.5-flash"
]

if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

def get_tags_with_retry(image_path, max_retries=1):
    if not client: return None
    for model_name in MODELS_TO_TRY:
        try:
            print(f"    -> {model_name} で分析中...")
            img = Image.open(image_path)
            prompt = (
                "Classify this illustration using EXACTLY one term from each category below. "
                "Return ONLY 4 terms separated by commas.\n\n"
                "1. Hair Color: [Pink Hair, Blue Hair, Blonde Hair, White Hair, Black Hair, Silver Hair, Brown Hair]\n"
                "2. Hair Style: [Twin Tails, Wavy Hair, Straight Hair, Pony Tail, Short Hair, Long Hair, Medium Hair]\n"
                "3. Clothing: [School Uniform, Dress, Lingerie, Swimsuit, Casual, Gothic]\n"
                "4. Identity: [Airi, Original] (CRITICAL: 'Airi' must have Pink hair, Wavy hair, and Angel wings. Otherwise use 'Original').\n\n"
                "Example output: Pink Hair, Twin Tails, Dress, Airi"
            )
            response = client.models.generate_content(model=model_name, contents=[prompt, img])
            if response and response.text:
                tags = [tag.strip() for tag in response.text.split(',')]
                return tags[:4]
        except Exception:
            continue
    return None

def save_data(artworks, output_file):
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("const ARTWORKS_DATA = ")
        json.dump(artworks, f, ensure_ascii=False, indent=4)
        f.write(";")

def deploy_to_github(message="Auto-update"):
    try:
        status = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True).stdout
        if not status: return False

        print(f"  [デプロイ] {message}...")
        subprocess.run(['git', 'add', '.'], check=True, capture_output=True)
        commit_msg = f"{message}: {datetime.datetime.now().strftime('%H:%M:%S')}"
        subprocess.run(['git', 'commit', '-m', commit_msg], check=True, capture_output=True)
        subprocess.run(['git', 'push', 'origin', 'main'], check=True, capture_output=True)
        return True
    except Exception:
        return False

def update_gallery():
    """戻り値: True なら『まだ仕事が残っている』という意味"""
    image_dir = 'illustrations'
    output_file = 'data.js'
    cache_file = 'tags_cache.json'
    
    valid_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
    if not os.path.exists(image_dir): os.makedirs(image_dir)

    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            tags_cache = json.load(f)
    else:
        tags_cache = {}

    filenames = [f for f in os.listdir(image_dir) if f.lower().endswith(valid_extensions)]
    artworks = []
    needs_ai = []
    
    for filename in filenames:
        file_path = os.path.join(image_dir, filename)
        timestamp = os.path.getmtime(file_path)
        dt = datetime.datetime.fromtimestamp(timestamp)
        date_str = dt.strftime('%Y.%m.%d')
        title = os.path.splitext(filename)[0].replace('_', ' ').capitalize()
        tags = tags_cache.get(filename, [])
        
        artworks.append({
            'filename': filename, 'title': title, 'date': date_str, 'tags': tags, 'timestamp': timestamp
        })
        if not tags:
            needs_ai.append(filename)
    
    # 画像のみ即公開
    save_data(sorted(artworks, key=lambda x: x['timestamp'], reverse=True), output_file)
    deploy_to_github("Rapid update")
    
    work_remains = False
    if needs_ai:
        print(f"\nAI分析開始 (残り {len(needs_ai)} 枚)...")
        processed_count = 0
        for filename in needs_ai:
            if processed_count >= 2: # 2枚ごとに区切って番人に主導権を戻す
                work_remains = True
                break
            
            new_tags = get_tags_with_retry(os.path.join(image_dir, filename))
            if new_tags:
                tags_cache[filename] = new_tags
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(tags_cache, f, ensure_ascii=False, indent=4)
                
                for art in artworks:
                    if art['filename'] == filename:
                        art['tags'] = new_tags
                save_data(sorted(artworks, key=lambda x: x['timestamp'], reverse=True), output_file)
                deploy_to_github(f"Tag added: {filename}")
                processed_count += 1
                time.sleep(5)
            else:
                # 失敗した場合は一旦飛ばして次へ（後でリトライされる）
                work_remains = True
                processed_count += 1

    # クリーンアップ
    cleaned_cache = {fn: tags for fn, tags in tags_cache.items() if fn in filenames}
    if len(cleaned_cache) != len(tags_cache):
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cleaned_cache, f, ensure_ascii=False, indent=4)
        deploy_to_github("Cache cleanup")

    return work_remains

if __name__ == '__main__':
    update_gallery()
