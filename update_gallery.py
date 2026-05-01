import os
import json
import datetime
import time
import subprocess
from dotenv import load_dotenv
from google import genai
from PIL import Image, ImageOps

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
    """画像にロゴを合成して上書き保存する"""
    if not os.path.exists(logo_path):
        print(f"    [警告] ロゴ画像が見つかりません: {logo_path}")
        return False
        
    try:
        with Image.open(image_path) as img:
            # 元画像をRGBAに変換
            img = img.convert("RGBA")
            
            # ロゴを読み込み
            with Image.open(logo_path) as logo:
                logo = logo.convert("RGBA")
                
                # 黒背景を透明にする処理（もしロゴが背景付きの場合）
                # 背景が黒(0,0,0)に近い部分を透明化
                datas = logo.getdata()
                new_data = []
                for item in datas:
                    # 黒に近い色（R,G,Bがすべて30以下）を透明にする
                    if item[0] < 30 and item[1] < 30 and item[2] < 30:
                        new_data.append((255, 255, 255, 0))
                    else:
                        # 白い部分は半透明(アルファ値150程度)にする
                        new_data.append((item[0], item[1], item[2], 150))
                logo.putdata(new_data)

                # ロゴのサイズ調整（イラストの横幅の15%程度にする）
                target_width = int(img.size[0] * 0.15)
                aspect_ratio = logo.size[1] / logo.size[0]
                target_height = int(target_width * aspect_ratio)
                logo = logo.resize((target_width, target_height), Image.Resampling.LANCZOS)
                
                # 配置場所（右下から少し内側）
                x = img.size[0] - logo.size[0] - 30
                y = img.size[1] - logo.size[1] - 30
                
                # 合成用の透明レイヤー作成
                overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                overlay.paste(logo, (x, y))
                
                # 合成
                watermarked = Image.alpha_composite(img, overlay)
                
                # 保存
                if image_path.lower().endswith(('.jpg', '.jpeg')):
                    watermarked = watermarked.convert("RGB")
                    watermarked.save(image_path, quality=95)
                else:
                    watermarked.save(image_path)
                
                print(f"    [加工] オリジナルロゴを配置しました")
                return True
    except Exception as e:
        print(f"    [エラー] ロゴ合成に失敗しました: {e}")
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
            
            # 【新機能】オリジナルロゴを合成
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
