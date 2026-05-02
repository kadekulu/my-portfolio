import os
import json
import datetime
import time
import subprocess
from dotenv import load_dotenv
from google import genai
from PIL import Image, ImageFilter

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODELS_TO_TRY = ["gemini-3-flash-preview", "gemini-2.0-flash", "gemini-1.5-flash"]
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

def apply_watermark(image_path, logo_path="watermark_logo.png"):
    """デバッグ用：ロゴを確実に表示させるための修正版"""
    if not os.path.exists(logo_path):
        print(f"    [致命的] ロゴ画像が見つかりません: {logo_path}")
        return False
        
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGBA")
            with Image.open(logo_path) as logo:
                logo = logo.convert("RGBA")
                
                # デバッグ：ロゴのサイズを出力
                print(f"    [DEBUG] 元画像サイズ: {img.size}, ロゴサイズ: {logo.size}")

                # 背景除去（少し条件を緩める）
                datas = logo.getdata()
                new_data = []
                for item in datas:
                    # 黒背景を透明に（R,G,Bがすべて60以下なら透明）
                    if item[0] < 60 and item[1] < 60 and item[2] < 60:
                        new_data.append((0, 0, 0, 0))
                    else:
                        # 白い部分は不透明な赤（デバッグ用にあえて目立つ色にする）
                        # うまくいったら白に戻します
                        new_data.append((255, 0, 0, 255)) 
                logo.putdata(new_data)
                
                # サイズ：横幅の25%（大きめに設定）
                target_width = int(img.size[0] * 0.25)
                target_height = int(target_width * (logo.size[1] / logo.size[0]))
                logo = logo.resize((target_width, target_height), Image.Resampling.LANCZOS)
                
                # デバッグ：処理後のロゴを単体で保存して確認
                logo.save("debug_logo_check.png")
                
                # 配置（右下から50px内側）
                x = img.size[0] - logo.size[0] - 50
                y = img.size[1] - logo.size[1] - 50
                
                # 貼り付け
                img.paste(logo, (x, y), logo) # 第3引数にlogo（mask）を指定
                
                # 保存
                final_img = img.convert("RGB")
                final_img.save(image_path, quality=95)
                
                print(f"    [加工成功] 右下({x},{y})に赤色のデバッグロゴを配置しました")
                return True
    except Exception as e:
        print(f"    [エラー] デバッグ加工失敗: {e}")
        return False

def get_tags_with_retry(image_path, max_retries=1):
    if not client: return None
    for model_name in MODELS_TO_TRY:
        try:
            print(f"    -> {model_name} で分析中...")
            response = client.models.generate_content(model=model_name, contents=["Return 4 tags: Hair, Style, Clothes, Name", Image.open(image_path)])
            if response and response.text: return [t.strip() for t in response.text.split(',')]
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
        subprocess.run(['git', 'commit', '-m', f"{message}: {datetime.datetime.now()}"], check=True, capture_output=True)
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
        artworks.append({'filename': filename, 'title': filename, 'date': '2026', 'tags': tags, 'timestamp': os.path.getmtime(path)})
        if not tags: needs_processing.append(filename)
    
    save_data(artworks, output_file)
    
    work_remains = False
    if needs_processing:
        print(f"\nデバッグ処理開始 (残り {len(needs_processing)} 枚)...")
        for filename in needs_processing[:2]:
            path = os.path.join(image_dir, filename)
            apply_watermark(path)
            new_tags = get_tags_with_retry(path)
            if new_tags:
                tags_cache[filename] = new_tags
                with open(cache_file, 'w', encoding='utf-8') as f: json.dump(tags_cache, f, ensure_ascii=False, indent=4)
                save_data(artworks, output_file)
                deploy_to_github(f"Debug: {filename}")
            work_remains = len(needs_processing) > 2
    return work_remains

if __name__ == '__main__':
    update_gallery()
