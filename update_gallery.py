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

def get_tags_with_retry(image_path, max_retries=2):
    if not client: return None
    for model_name in MODELS_TO_TRY:
        for attempt in range(max_retries):
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
                    print(f"    [成功] タグ確定: {tags}")
                    return tags[:4]
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg:
                    print(f"    [混雑] 少し休憩します...")
                    time.sleep(30)
                else:
                    break
    return None

def save_data(artworks, output_file):
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("const ARTWORKS_DATA = ")
        json.dump(artworks, f, ensure_ascii=False, indent=4)
        f.write(";")

def deploy_to_github(message="Auto-update"):
    try:
        print(f"\n[デプロイ] {message}...")
        subprocess.run(['git', 'add', '.'], check=True, capture_output=True)
        commit_msg = f"{message}: {datetime.datetime.now().strftime('%H:%M:%S')}"
        subprocess.run(['git', 'commit', '-m', commit_msg], check=True, capture_output=True)
        subprocess.run(['git', 'push', 'origin', 'main'], check=True, capture_output=True)
        print("[成功] 反映完了！")
    except Exception:
        pass # エラーは静かにスルー

def update_gallery():
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

    print("=== スピード優先モード起動 ===")
    filenames = [f for f in os.listdir(image_dir) if f.lower().endswith(valid_extensions)]
    artworks = []
    
    # 【ステップ1】まずは現在の全画像を即座にリスト化して公開
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
    
    # 暫定版（タグなし画像含む）を即デプロイ
    save_data(sorted(artworks, key=lambda x: x['timestamp'], reverse=True), output_file)
    deploy_to_github("Rapid deployment")
    
    # 【ステップ2】裏でじっくりAIタグ付けを行い、1枚ごとに更新
    for art in artworks:
        if not art['tags']:
            print(f"\nAI分析開始: {art['filename']}")
            new_tags = get_tags_with_retry(os.path.join(image_dir, art['filename']))
            if new_tags:
                art['tags'] = new_tags
                tags_cache[art['filename']] = new_tags
                # キャッシュ保存
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(tags_cache, f, ensure_ascii=False, indent=4)
                # 1枚ごとにサイト更新
                save_data(sorted(artworks, key=lambda x: x['timestamp'], reverse=True), output_file)
                deploy_to_github(f"Tag updated: {art['filename']}")
                # 制限回避の休憩
                time.sleep(10)
    
    # クリーンアップ（最後にお掃除）
    cleaned_cache = {fn: tags for fn, tags in tags_cache.items() if fn in filenames}
    if len(cleaned_cache) != len(tags_cache):
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cleaned_cache, f, ensure_ascii=False, indent=4)
        deploy_to_github("Cache cleanup")

    print(f"\n=== すべての作業が完了しました！ ===")

if __name__ == '__main__':
    update_gallery()
