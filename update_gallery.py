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
# ローカル環境では .env を使い、GitHub Actions では Secrets から注入された環境変数を使います
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODELS_TO_TRY = ["gemini-3-flash-preview", "gemini-2.0-flash", "gemini-1.5-flash"]
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

# 【追加】GitHub Actions 環境かどうかを判定
IS_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"

# 正解リスト（この中の言葉以外は認めない）
VALID_VOCABULARY = {
    "Hair Color": ["Pink Hair", "Blue Hair", "Blonde Hair", "White Hair", "Black Hair", "Silver Hair", "Brown Hair"],
    "Hair Style": ["Twin Tails", "Wavy Hair", "Straight Hair", "Pony Tail", "Short Hair", "Long Hair", "Medium Hair"],
    "Clothing": ["School Uniform", "Dress", "Lingerie", "Swimsuit", "Casual", "Gothic"],
    "Identity": ["Airi", "Original"]
}

def sanitize_tags(raw_text):
    """AIの回答から正解リストにある単語だけを抽出して標準化する"""
    if not raw_text: return []
    
    # 全カテゴリーの単語をフラットなリストにする
    flatten_valid = [item for sublist in VALID_VOCABULARY.values() for item in sublist]
    
    found_tags = []
    # カテゴリーごとに、正解リストの単語が含まれているかチェック
    for category, options in VALID_VOCABULARY.items():
        matched = False
        for opt in options:
            # 大文字小文字を無視して検索
            if re.search(re.escape(opt), raw_text, re.IGNORECASE):
                found_tags.append(opt) # 正式な表記（Pink Hairなど）を追加
                matched = True
                break
        if not matched:
            # 見つからなかった場合のデフォルト
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
        
        # 背景除去
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
                "Constraints: Return EXACTLY 4 terms from the lists below, separated by commas. NO sentences, NO markdown.\n"
                f"1. Hair Color: {VALID_VOCABULARY['Hair Color']}\n"
                f"2. Hair Style: {VALID_VOCABULARY['Hair Style']}\n"
                f"3. Clothing: {VALID_VOCABULARY['Clothing']}\n"
                f"4. Identity: {VALID_VOCABULARY['Identity']}\n"
                "Example: Pink Hair, Wavy Hair, Dress, Airi"
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
    
    # キャッシュ読み込み
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            tags_cache = json.load(f)
    else:
        tags_cache = {}

    # キャッシュのクリーンアップ（不正なタグの除去）
    original_count = len(tags_cache)
    cleaned_cache = {}
    for fn, tags in tags_cache.items():
        is_dirty = any(not isinstance(t, str) or len(t) > 25 or '\n' in t or '*' in t for t in tags)
        if not is_dirty:
            cleaned_cache[fn] = tags
    
    if len(cleaned_cache) != original_count:
        print(f"--- タグの大掃除: {original_count - len(cleaned_cache)} 件の不正なタグを破棄しました ---")
        tags_cache = cleaned_cache

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
        # GitHub Actions 上では Git コマンドをスキップし、YAML側で処理する
        if IS_GITHUB_ACTIONS:
            print(f"    [SKIP] クラウド環境のため内部デプロイをスキップ: {msg}")
            return
            
        print(f"    [LOCAL] Git に変更を記録中: {msg}")
        subprocess.run(['git', 'add', '.'], capture_output=True)
        subprocess.run(['git', 'commit', '-m', f"{msg}: {datetime.datetime.now().strftime('%H:%M:%S')}"], capture_output=True)

    # 最初のデータ更新を記録
    deploy("Update gallery data")
    
    if needs_processing:
        # GitHub Actions では一度に処理する枚数を少し増やしてもOK（今回は安全のため5枚までに調整）
        limit = 5 if IS_GITHUB_ACTIONS else 2
        print(f"\nタグ付けを開始 (残り {len(needs_processing)} 枚, 今回は最大 {limit} 枚処理)...")
        
        for filename in needs_processing[:limit]:
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
                time.sleep(5)
        return True
    return False

if __name__ == '__main__':
    update_gallery()
