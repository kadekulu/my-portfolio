import os
import json
import datetime
import time
import subprocess
from dotenv import load_dotenv
from google import genai
from PIL import Image, ImageFilter, ImageOps

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

def apply_watermark(image_path, logo_path="watermark_logo.png"):
    """画像に視認性の高いロゴを合成して上書き保存する"""
    if not os.path.exists(logo_path):
        print(f"    [警告] ロゴ画像が見つかりません: {logo_path}")
        return False
        
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGBA")
            
            with Image.open(logo_path) as logo:
                logo = logo.convert("RGBA")
                
                # 1. ロゴのクリーンアップ（黒背景を除去し、白を強調）
                datas = logo.getdata()
                new_data = []
                for item in datas:
                    # 黒に近い色を完全に透明に
                    if item[0] < 50 and item[1] < 50 and item[2] < 50:
                        new_data.append((0, 0, 0, 0))
                    else:
                        # 白い部分はハッキリと（不透明度200/255）
                        new_data.append((255, 255, 255, 200))
                logo.putdata(new_data)

                # 2. サイズ調整（イラストの横幅の20%に拡大）
                target_width = int(img.size[0] * 0.20)
                aspect_ratio = logo.size[1] / logo.size[0]
                target_height = int(target_width * aspect_ratio)
                logo = logo.resize((target_width, target_height), Image.Resampling.LANCZOS)
                
                # 3. 縁取り/シャドウの作成（白い背景でも見えるようにする）
                # ロゴのアルファチャンネル（形）を取り出してぼかす
                shadow = Image.new("RGBA", logo.size, (0, 0, 0, 255))
                shadow.putalpha(logo.getchannel("A"))
                # 黒い影を少し広げてぼかす
                shadow = shadow.filter(ImageFilter.GaussianBlur(radius=2))
                
                # 4. 合成
                # 下地に黒い影、その上に白いロゴを重ねる
                combined_logo = Image.new("RGBA", logo.size, (0, 0, 0, 0))
                combined_logo.paste(shadow, (2, 2), shadow) # 影を少しずらす
                combined_logo.paste(logo, (0, 0), logo)
                
                # 配置場所（右下）
                x = img.size[0] - combined_logo.size[0] - 40
                y = img.size[1] - combined_logo.size[1] - 40
                
                overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                overlay.paste(combined_logo, (x, y))
                
                # 最終合成
                watermarked = Image.alpha_composite(img, overlay)
                
                if image_path.lower().endswith(('.jpg', '.jpeg')):
                    watermarked = watermarked.convert("RGB")
                    watermarked.save(image_path, quality=95)
                else:
                    watermarked.save(image_path)
                
                print(f"    [加工] 視認性強化ロゴを配置しました")
                return True
    except Exception as e:
        print(f"    [エラー] ロゴ合成失敗: {e}")
        return False

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
                print(f"    [成功] 属性確定: {tags}")
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
        subprocess.run(['git', 'add', '.'], check=True, capture_output=True)
        commit_msg = f"{message}: {datetime.datetime.now().strftime('%H:%M:%S')}"
        subprocess.run(['git', 'commit', '-m', commit_msg], check=True, capture_output=True)
        subprocess.run(['git', 'push', 'origin', 'main'], check=True, capture_output=True)
        return True
    except Exception:
        return False

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

    filenames = [f for f in os.listdir(image_dir) if f.lower().endswith(valid_extensions)]
    artworks = []
    needs_processing = []
    
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
            needs_processing.append(filename)
    
    save_data(sorted(artworks, key=lambda x: x['timestamp'], reverse=True), output_file)
    deploy_to_github("Rapid update")
    
    work_remains = False
    if needs_processing:
        print(f"\n新規画像の処理を開始 (残り {len(needs_processing)} 枚)...")
        processed_count = 0
        for filename in needs_processing:
            if processed_count >= 2:
                work_remains = True
                break
            
            file_path = os.path.join(image_dir, filename)
            
            # 【改良版】視認性の高いロゴ合成
            apply_watermark(file_path)
            
            new_tags = get_tags_with_retry(file_path)
            if new_tags:
                tags_cache[filename] = new_tags
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(tags_cache, f, ensure_ascii=False, indent=4)
                
                for art in artworks:
                    if art['filename'] == filename:
                        art['tags'] = new_tags
                save_data(sorted(artworks, key=lambda x: x['timestamp'], reverse=True), output_file)
                deploy_to_github(f"Processed: {filename}")
                processed_count += 1
                time.sleep(5)
            else:
                work_remains = True
                processed_count += 1

    cleaned_cache = {fn: tags for fn, tags in tags_cache.items() if fn in filenames}
    if len(cleaned_cache) != len(tags_cache):
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cleaned_cache, f, ensure_ascii=False, indent=4)
        deploy_to_github("Cache cleanup")

    return work_remains

if __name__ == '__main__':
    update_gallery()
