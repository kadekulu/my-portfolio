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

MODELS_TO_TRY = ["gemini-3-flash-preview", "gemini-2.0-flash", "gemini-1.5-flash"]
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

def apply_watermark(image_path, logo_path="watermark_logo.png"):
    """Windowsのファイルロックを回避しつつ、視認性の高いロゴを合成する"""
    if not os.path.exists(logo_path):
        print(f"    [警告] ロゴ画像が見つかりません: {logo_path}")
        return False
        
    try:
        # 1. 画像をメモリに読み込み、すぐにファイルを閉じる（ロック回避）
        with Image.open(image_path) as temp_img:
            img = temp_img.copy()
        img = img.convert("RGBA")
        
        # 2. ロゴの処理
        with Image.open(logo_path) as temp_logo:
            logo = temp_logo.copy()
        logo = logo.convert("RGBA")
        
        # ロゴの背景除去と白の強調
        datas = logo.getdata()
        new_data = []
        for item in datas:
            if item[0] < 60 and item[1] < 60 and item[2] < 60:
                new_data.append((0, 0, 0, 0)) # 透明
            else:
                new_data.append((255, 255, 255, 220)) # はっきりした白
        logo.putdata(new_data)

        # サイズ調整（横幅の20%）
        target_width = int(img.size[0] * 0.20)
        aspect_ratio = logo.size[1] / logo.size[0]
        target_height = int(target_width * aspect_ratio)
        logo = logo.resize((target_width, target_height), Image.Resampling.LANCZOS)
        
        # 3. シャドウ（影）を入れて視認性を上げる
        shadow = Image.new("RGBA", logo.size, (0, 0, 0, 255))
        shadow.putalpha(logo.getchannel("A"))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=3))
        
        # 影とロゴを合体
        combined_logo = Image.new("RGBA", logo.size, (0, 0, 0, 0))
        combined_logo.paste(shadow, (3, 3), shadow)
        combined_logo.paste(logo, (0, 0), logo)
        
        # 4. 配置（右下）
        x = img.size[0] - combined_logo.size[0] - 40
        y = img.size[1] - combined_logo.size[1] - 40
        
        img.paste(combined_logo, (x, y), combined_logo)
        
        # 5. 上書き保存
        if image_path.lower().endswith(('.jpg', '.jpeg')):
            img = img.convert("RGB")
            img.save(image_path, quality=95, subsampling=0)
        else:
            img.save(image_path)
            
        print(f"    [成功] ロゴを合成しました: {os.path.basename(image_path)}")
        return True
    except Exception as e:
        print(f"    [エラー] ロゴ合成失敗: {e}")
        return False

def get_tags_with_retry(image_path, max_retries=1):
    if not client: return None
    for model_name in MODELS_TO_TRY:
        try:
            print(f"    -> {model_name} で分析中...")
            response = client.models.generate_content(model=model_name, contents=[
                "Analyze this illustration. Return ONLY 4 tags: Hair Color, Hair Style, Clothing, Character Name (Airi or Original).",
                Image.open(image_path)
            ])
            if response and response.text:
                return [t.strip() for t in response.text.split(',')]
        except: continue
    return None

def save_data(artworks, output_file):
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("const ARTWORKS_DATA = ")
        json.dump(artworks, f, ensure_ascii=False, indent=4)
        f.write(";")

def deploy_to_github(message="Auto-update"):
    try:
        subprocess.run(['git', 'add', '.'], check=True, capture_output=True)
        commit_msg = f"{message}: {datetime.datetime.now().strftime('%H:%M:%S')}"
        subprocess.run(['git', 'commit', '-m', commit_msg], check=True, capture_output=True)
        subprocess.run(['git', 'push', 'origin', 'main'], check=True, capture_output=True)
        return True
    except: return False

def update_gallery():
    image_dir, output_file, cache_file = 'illustrations', 'data.js', 'tags_cache.json'
    if not os.path.exists(image_dir): os.makedirs(image_dir)
    tags_cache = json.load(open(cache_file, 'r', encoding='utf-8')) if os.path.exists(cache_file) else {}
    
    filenames = [f for f in os.listdir(image_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
    artworks = []
    needs_processing = []
    
    for filename in filenames:
        path = os.path.join(image_dir, filename)
        tags = tags_cache.get(filename, [])
        artworks.append({
            'filename': filename, 'title': os.path.splitext(filename)[0], 
            'date': datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y.%m.%d'),
            'tags': tags, 'timestamp': os.path.getmtime(path)
        })
        if not tags: needs_processing.append(filename)
    
    save_data(sorted(artworks, key=lambda x: x['timestamp'], reverse=True), output_file)
    deploy_to_github("Rapid update")
    
    work_remains = False
    if needs_processing:
        print(f"\n画像処理を開始 (残り {len(needs_processing)} 枚)...")
        for filename in needs_processing[:2]:
            path = os.path.join(image_dir, filename)
            if apply_watermark(path):
                new_tags = get_tags_with_retry(path)
                if new_tags:
                    tags_cache[filename] = new_tags
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump(tags_cache, f, ensure_ascii=False, indent=4)
                    for art in artworks:
                        if art['filename'] == filename: art['tags'] = new_tags
                    save_data(sorted(artworks, key=lambda x: x['timestamp'], reverse=True), output_file)
                    deploy_to_github(f"Processed: {filename}")
            work_remains = len(needs_processing) > 2
    return work_remains

if __name__ == '__main__':
    update_gallery()
