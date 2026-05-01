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

# 試行するモデルのリスト
MODELS_TO_TRY = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]

if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

def get_tags_with_retry(image_path, max_retries=2):
    """リトライしながらタグを取得する"""
    if not client: return None
    for model_name in MODELS_TO_TRY:
        for attempt in range(max_retries):
            try:
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
                time.sleep(30)
    return None

def save_data(artworks, output_file):
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("const ARTWORKS_DATA = ")
        json.dump(artworks, f, ensure_ascii=False, indent=4)
        f.write(";")

def deploy_to_github():
    """GitHubへ自動的にプッシュ（世界公開）する"""
    try:
        print("\n[デプロイ] 世界へ公開中...")
        # Gitコマンドを順番に実行
        subprocess.run(['git', 'add', '.'], check=True)
        # 日時をコメントに入れてコミット
        commit_msg = f"Auto-update: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(['git', 'commit', '-m', commit_msg], check=True)
        # メインブランチへ送信
        subprocess.run(['git', 'push', 'origin', 'main'], check=True)
        print("[成功] 世界への公開が完了しました！")
    except Exception as e:
        print(f"[失敗] デプロイ中にエラーが発生しました: {e}")
        print("ヒント: 最初の1回目は手動でログインや設定が必要な場合があります。")

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

    print("スキャン開始...")
    filenames = [f for f in os.listdir(image_dir) if f.lower().endswith(valid_extensions)]
    artworks = []
    cache_updated = False
    
    for filename in filenames:
        file_path = os.path.join(image_dir, filename)
        timestamp = os.path.getmtime(file_path)
        dt = datetime.datetime.fromtimestamp(timestamp)
        date_str = dt.strftime('%Y.%m.%d')
        title = os.path.splitext(filename)[0].replace('_', ' ').capitalize()
        
        tags = tags_cache.get(filename, [])
        if not tags:
            print(f"\nAI分析中: {filename}")
            new_tags = get_tags_with_retry(file_path)
            if new_tags:
                tags = new_tags
                tags_cache[filename] = tags
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(tags_cache, f, ensure_ascii=False, indent=4)
                cache_updated = True
                time.sleep(2)
        
        artworks.append({
            'filename': filename, 'title': title, 'date': date_str, 'tags': tags, 'timestamp': timestamp
        })
        save_data(sorted(artworks, key=lambda x: x['timestamp'], reverse=True), output_file)
    
    # 変化があれば自動でデプロイ（世界公開）を実行
    if cache_updated or True: # 実験のため常に実行するように設定（後で調整可）
        deploy_to_github()
    
    print(f"\n更新完了！")

if __name__ == '__main__':
    update_gallery()
