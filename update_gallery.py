import os
import json
import datetime
import time
import subprocess
import re
import requests
from dotenv import load_dotenv
from google import genai
from PIL import Image, ImageFilter

# .envファイルからAPIキーを読み込む
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Make.com / SNS連携の設定
MAKE_WEBHOOK_URL = "https://hook.us2.make.com/he8csq0dbyu2t4zoqiiql6myvlzhvw53"
GITHUB_PAGES_BASE_URL = "https://kadekulu.github.io/my-portfolio/"

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
    if not os.path.exists(logo_path):
        print(f"    [警告] ロゴファイルが見つかりません: {logo_path}")
        return False
    try:
        with Image.open(image_path) as temp_img:
            img = temp_img.copy()
        img = img.convert("RGBA")
        with Image.open(logo_path) as temp_logo:
            logo = temp_logo.copy()
        logo = logo.convert("RGBA")
        
        # サイズ調整 (画像幅の25%に少し大きく)
        target_width = int(img.size[0] * 0.25)
        logo = logo.resize((target_width, int(target_width * (logo.size[1]/logo.size[0]))), Image.Resampling.LANCZOS)
        
        # ロゴ自体の不透明度を調整 (全体を少し透かす)
        alpha = logo.getchannel('A')
        alpha = alpha.point(lambda p: p * 0.7) # 70%の濃さ
        logo.putalpha(alpha)
        
        # 右下に貼り付け (余白を少し調整)
        img.paste(logo, (img.size[0]-logo.size[0]-50, img.size[1]-logo.size[1]-50), logo)
        
        # 保存
        if image_path.lower().endswith(('.jpg', '.jpeg')):
            img.convert("RGB").save(image_path, quality=95, subsampling=0)
        else:
            img.save(image_path)
        print(f"    [成功] ロゴを貼り付けました: {os.path.basename(image_path)}")
        return True
    except Exception as e:
        print(f"    [エラー] ロゴ入れに失敗しました ({os.path.basename(image_path)}): {e}")
        return False

def get_tags_with_retry(image_path):
    if not client:
        print("    [エラー] Gemini APIクライアントが初期化されていません。APIキーを確認してください。")
        return None
    for model_name in MODELS_TO_TRY:
        try:
            print(f"    -> {model_name} で分析中...")
            # 愛依莉の特徴をAIに詳しく教えるプロンプトを作成
            prompt = (
                "Task: Classify this illustration based on the following rules.\n\n"
                "1. Identity Definition:\n"
                "   - 'Airi': A specific character with Pink Hair, Wavy Hair, Yellow Eyes, Large Breasts, an Angel Halo, and Angel Wings.\n"
                "   - 'Original': Any other characters that do not match the features of Airi.\n\n"
                "2. Tagging Rules:\n"
                "   - Return EXACTLY 4 terms from the lists below, separated by commas.\n"
                f"   - Hair Color: {VALID_VOCABULARY['Hair Color']}\n"
                f"   - Hair Style: {VALID_VOCABULARY['Hair Style']}\n"
                f"   - Clothing: {VALID_VOCABULARY['Clothing']}\n"
                f"   - Identity: {VALID_VOCABULARY['Identity']}\n\n"
                "3. Constraint:\n"
                "   - Be very strict. If the character doesn't have the angel halo/wings or has different eye/hair features, tag it as 'Original'.\n"
                "Example: Pink Hair, Wavy Hair, Dress, Airi"
            )
            response = client.models.generate_content(model=model_name, contents=[prompt, Image.open(image_path)])
            if response and response.text:
                tags = sanitize_tags(response.text)
                print(f"    [確定] {tags}")
                return tags
        except Exception as e:
            print(f"    [警告] {model_name} でエラーが発生しました: {e}")
            continue
    return None

def send_to_make(artwork_data):
    """Make.com の Webhook にデータを送信する"""
    if not MAKE_WEBHOOK_URL: return
    try:
        # 公開後の画像URLを作成
        image_url = f"{GITHUB_PAGES_BASE_URL}illustrations/{artwork_data['filename']}"
        payload = {
            "title": artwork_data['title'],
            "date": artwork_data['date'],
            "tags": artwork_data['tags'],
            "image_url": image_url,
            "portfolio_url": GITHUB_PAGES_BASE_URL
        }
        # Webhook に送信
        res = requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=10)
        if res.status_code == 200:
            print(f"    [Make] SNS連携データを送信しました: {artwork_data['title']}")
        else:
            print(f"    [Make] 送信失敗 (Status: {res.status_code})")
    except Exception as e:
        print(f"    [Make] エラーが発生しました: {e}")

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
                
                # artwork_data を更新して送信
                target_art = None
                for art in artworks:
                    if art['filename'] == filename:
                        art['tags'] = new_tags
                        target_art = art
                
                save()
                deploy(f"Processed: {filename}")
                
                # Make に送信
                if target_art:
                    send_to_make(target_art)
                
                time.sleep(2)
        return True
    return False

if __name__ == '__main__':
    update_gallery()
