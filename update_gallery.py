import os
import json
import datetime
import time
import subprocess
import re
import requests
import base64
from io import BytesIO
from dotenv import load_dotenv
from PIL import Image, ImageFilter

# .envファイルからAPIキーを読み込む
load_dotenv()

# Ollama (Local AI) の設定
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2-vision"

# Make.com / SNS連携の設定
MAKE_WEBHOOK_URL = "https://hook.us2.make.com/he8csq0dbyu2t4zoqiiql6myvlzhvw53"
GITHUB_PAGES_BASE_URL = "https://kadekulu.github.io/my-portfolio/"

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
        
        # サイズ調整 (画像幅の25%に)
        target_width = int(img.size[0] * 0.25)
        logo = logo.resize((target_width, int(target_width * (logo.size[1]/logo.size[0]))), Image.Resampling.LANCZOS)
        
        # --- 視認性向上のための「影」を作成 ---
        # 1. ロゴと同じサイズの真っ黒な画像を作成
        shadow = Image.new("RGBA", logo.size, (0, 0, 0, 255))
        # 2. ロゴの形（アルファチャンネル）を影に適用
        shadow.putalpha(logo.getchannel("A"))
        # 3. 影をぼかす (視認性を上げるために少し強めに)
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=4))
        
        # 4. 影とロゴを合成する台紙を作成
        combined_logo = Image.new("RGBA", logo.size, (0, 0, 0, 0))
        # 影を少しずらして貼り付け (立体感を出す)
        combined_logo.paste(shadow, (2, 2), shadow)
        # その上にロゴ本体を貼り付け
        combined_logo.paste(logo, (0, 0), logo)
        
        # 5. 合成したロゴ全体の不透明度を微調整 (85%くらいの濃さに)
        c_alpha = combined_logo.getchannel('A')
        c_alpha = c_alpha.point(lambda p: p * 0.85)
        combined_logo.putalpha(c_alpha)
        
        # 右下に貼り付け
        img.paste(combined_logo, (img.size[0]-combined_logo.size[0]-50, img.size[1]-combined_logo.size[1]-50), combined_logo)
        
        # 保存
        if image_path.lower().endswith(('.jpg', '.jpeg')):
            img.convert("RGB").save(image_path, quality=95, subsampling=0)
        else:
            img.save(image_path)
        print(f"    [成功] ロゴ(視認性強化)を貼り付けました: {os.path.basename(image_path)}")
        return True
    except Exception as e:
        print(f"    [エラー] ロゴ入れに失敗しました ({os.path.basename(image_path)}): {e}")
        return False

def get_tags_with_retry(image_path):
    """ローカルの Ollama (Llama 3.2 Vision) を使用して画像タグを生成する"""
    try:
        print(f"    -> ローカルAI ({OLLAMA_MODEL}) で分析中...")
        
        # 画像をBase64に変換
        with Image.open(image_path) as img:
            buffered = BytesIO()
            img.save(buffered, format="JPEG")
            img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')

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

        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "images": [img_str],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 50
            }
        }

        response = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
        if response.status_code == 200:
            raw_text = response.json().get('response', '')
            tags = sanitize_tags(raw_text)
            print(f"    [確定] {tags}")
            return tags
        else:
            print(f"    [エラー] Ollama 応答エラー (Status: {response.status_code})")
            return None

    except Exception as e:
        print(f"    [警告] ローカルAI処理中にエラーが発生しました: {e}")
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
        # キャッシュから情報を取得 (古い形式への互換性も考慮)
        cache_data = tags_cache.get(filename)
        if isinstance(cache_data, list):
            tags = cache_data
            is_watermarked = False
        elif isinstance(cache_data, dict):
            tags = cache_data.get('tags', [])
            is_watermarked = cache_data.get('watermarked', False)
        else:
            tags = []
            is_watermarked = False

        mtime = os.path.getmtime(path)
        artworks.append({
            'filename': filename, 'title': os.path.splitext(filename)[0], 
            'date': datetime.datetime.fromtimestamp(mtime).strftime('%Y.%m.%d'),
            'tags': tags, 'timestamp': mtime
        })
        # タグがない、またはロゴが入っていない場合に処理対象にする
        if not tags or not is_watermarked:
            needs_processing.append({'filename': filename, 'watermarked': is_watermarked, 'has_tags': bool(tags)})
    
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
        print(f"\nローカルで更新を開始 (残り {len(needs_processing)} 枚)...")
        for item in needs_processing[:5]:
            filename = item['filename']
            path = os.path.join(image_dir, filename)
            
            # まだロゴが入っていない場合のみ実行
            if not item['watermarked']:
                if apply_watermark(path):
                    # キャッシュを辞書形式に更新
                    if filename not in tags_cache or isinstance(tags_cache[filename], list):
                        tags_cache[filename] = {'tags': tags_cache.get(filename, []), 'watermarked': True}
                    else:
                        tags_cache[filename]['watermarked'] = True
                    
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump(tags_cache, f, ensure_ascii=False, indent=4)
            
            # タグがない場合のみ実行
            if not item['has_tags']:
                new_tags = get_tags_with_retry(path)
                if new_tags:
                    if filename not in tags_cache or isinstance(tags_cache[filename], list):
                        tags_cache[filename] = {'tags': new_tags, 'watermarked': True}
                    else:
                        tags_cache[filename]['tags'] = new_tags
                        tags_cache[filename]['watermarked'] = True
                    
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump(tags_cache, f, ensure_ascii=False, indent=4)
                    
                    target_art = None
                    for art in artworks:
                        if art['filename'] == filename:
                            art['tags'] = new_tags
                            target_art = art
                    
                    save()
                    deploy(f"Processed tags: {filename}")
                    if target_art:
                        send_to_make(target_art)
                
                time.sleep(2)
        return True
    return False

if __name__ == '__main__':
    update_gallery()
