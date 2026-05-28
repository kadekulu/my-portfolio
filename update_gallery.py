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

# --- 設定の読み込み ---
CONFIG_FILE = "config.json"
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"USE_LOCAL_AI": True}

config = load_config()
USE_LOCAL_AI = config.get("USE_LOCAL_AI", True)
# ------------------

# Ollama (Local AI) の設定
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2-vision"

# Gemini (Cloud AI) の設定
from google import genai
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
else:
    gemini_client = None
GEMINI_MODELS = ["gemini-2.0-flash-exp", "gemini-1.5-flash"]

# 正解リスト
VALID_VOCABULARY = {
    "Hair Color": ["Pink Hair", "Blue Hair", "Blonde Hair", "White Hair", "Black Hair", "Silver Hair", "Brown Hair"],
    "Hair Style": ["Twin Tails", "Wavy Hair", "Straight Hair", "Pony Tail", "Short Hair", "Long Hair", "Medium Hair"],
    "Clothing": ["School Uniform", "Dress", "Lingerie", "Swimsuit", "Casual", "Gothic"],
    "Identity": ["Airi", "Original"]
}

def sanitize_tags(raw_text):
    if not raw_text: return []
    # AIの回答をカンマで分割し、各項目をクリーンアップ
    parts = [p.strip() for p in raw_text.split(',')]
    found_tags = []
    
    # カテゴリごとに最適なマッチを探す
    categories = list(VALID_VOCABULARY.keys())
    for i, category in enumerate(categories):
        options = VALID_VOCABULARY[category]
        matched_tag = None
        
        # 1. 対応する位置のテキストを優先的にチェック
        text_to_check = parts[i] if i < len(parts) else raw_text
        
        for opt in options:
            if re.search(r'\b' + re.escape(opt) + r'\b', text_to_check, re.IGNORECASE):
                matched_tag = opt
                break
        
        # 2. 見つからない場合は全体から探す (ただし Identity は慎重に)
        if not matched_tag:
            for opt in options:
                if re.search(r'\b' + re.escape(opt) + r'\b', raw_text, re.IGNORECASE):
                    # 拒否文によくあるパターンを避ける
                    if category == "Identity" and ("not match" in raw_text.lower() or "not identify" in raw_text.lower()):
                        continue
                    matched_tag = opt
                    break
        
        # 3. それでもない場合はデフォルト
        if matched_tag:
            found_tags.append(matched_tag)
        else:
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
        target_width = int(img.size[0] * 0.25)
        logo = logo.resize((target_width, int(target_width * (logo.size[1]/logo.size[0]))), Image.Resampling.LANCZOS)
        shadow = Image.new("RGBA", logo.size, (0, 0, 0, 255))
        shadow.putalpha(logo.getchannel("A"))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=4))
        combined_logo = Image.new("RGBA", logo.size, (0, 0, 0, 0))
        combined_logo.paste(shadow, (2, 2), shadow)
        combined_logo.paste(logo, (0, 0), logo)
        c_alpha = combined_logo.getchannel('A')
        c_alpha = c_alpha.point(lambda p: p * 0.85)
        combined_logo.putalpha(c_alpha)
        img.paste(combined_logo, (img.size[0]-combined_logo.size[0]-50, img.size[1]-combined_logo.size[1]-50), combined_logo)
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
    """選択されたエンジン（ローカル or クラウド）を使用してタグを生成する"""
    if USE_LOCAL_AI:
        return get_tags_ollama(image_path)
    else:
        return get_tags_gemini(image_path)

def get_tags_ollama(image_path):
    """ローカルの Ollama (Llama 3.2 Vision) を使用"""
    try:
        print(f"    -> ローカルAI ({OLLAMA_MODEL}) で分析中...")
        with Image.open(image_path) as img:
            buffered = BytesIO()
            img.save(buffered, format="JPEG")
            img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        prompt = """
        # イラスト投稿文生成プロンプト v1.0
        分析の過程は出力せず、結果のみを出力すること。

        1. タグ付け (4項目):
           [髪色, 髪型, 服装, キャラ特定(Airi or Original)]
           - Airi判定条件: ピンク髪, ウェーブヘア, ミディアムヘア, 黄色い瞳, 天使の輪っか, 天使の羽。

        2. Xの投稿案 (3パターン):
           A：キャラクターの感情・内面
           B：閲覧者の感情・行動喚起
           C：場面・瞬間の描写
           - 文字数：目標6文字、上限15文字以内。
           - 禁止：ハッシュタグ、絵文字、ブランド名、名前。

        出力フォーマット:
        TAGS: [タグ1, タグ2, タグ3, タグ4]
        A：(本文)
        B：(本文)
        C：(本文)
        """
        
        payload = {"model": OLLAMA_MODEL, "prompt": prompt, "images": [img_str], "stream": False, "options": {"temperature": 0.0}}
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
        if response.status_code == 200:
            raw_text = response.json().get('response', '').strip()
            return parse_ai_response(raw_text)
        return None
    except Exception as e:
        print(f"    [警告] ローカルAI処理中にエラーが発生しました: {e}")
        return None

def get_tags_gemini(image_path):
    """クラウドの Google Gemini を使用"""
    if not gemini_client: return None
    
    prompt = """
    # イラスト投稿文生成プロンプト v1.0
    分析の過程は出力せず、結果のみを出力すること。

    1. タグ付け (4項目):
       [髪色, 髪型, 服装, キャラ特定(Airi or Original)]
       - Airi判定条件: ピンク髪, ウェーブヘア, ミディアムヘア, 黄色い瞳, 天使の輪っか, 天使の羽。

    2. Xの投稿案 (3パターン):
       A：キャラクターの感情・内面
       B：閲覧者の感情・行動喚起
       C：場面・瞬間の描写
       - 文字数：目標6文字、上限15文字以内。
       - 禁止：ハッシュタグ、絵文字、ブランド名、名前。

    出力フォーマット:
    TAGS: [タグ1, タグ2, タグ3, タグ4]
    A：(本文)
    B：(本文)
    C：(本文)
    """
    
    for model_name in GEMINI_MODELS:
        try:
            print(f"    -> Gemini ({model_name}) で分析中...")
            response = gemini_client.models.generate_content(model=model_name, contents=[prompt, Image.open(image_path)])
            if response and response.text:
                return parse_ai_response(response.text)
        except Exception as e:
            print(f"    [警告] Gemini ({model_name}) でエラー: {e}")
            continue
    return None

def parse_ai_response(raw_text):
    """AIの回答からタグと投稿案を抽出して整形"""
    import re
    tags = sanitize_tags(raw_text)
    captions = []
    # A, B, C の投稿案を抽出
    for p in ['A', 'B', 'C']:
        match = re.search(f"{p}[：:\\.](.*?)(?=[A-C][：:\\.]|TAGS|$)", raw_text, re.S)
        if match:
            body = match.group(1).strip().replace('"', '').replace('「', '').replace('」', '')
            # ルール通りタグを付与
            if body:
                captions.append(f"{body}\n\n\n#愛依莉")
    
    # AIが3つの投稿案を作りきれなかった場合、エラーにせずデフォルトの文章で埋める
    while len(captions) < 3:
        captions.append(f"イラストを追加しました！\n\n\n#愛依莉")
    
    # 投稿案の数に関わらず、処理を続行する（エラーで弾かない）
    if tags:
        print(f"    [確定] {tags}")
        return {"tags": tags, "captions": captions}
    else:
        print(f"    [参考] パース失敗、AIの回答内容: \"{raw_text[:100]}...\"")
        return None



def update_gallery():
    image_dir, output_file, cache_file = 'illustrations', 'data.js', 'tags_cache.json'
    
    # 時間帯用サブフォルダの自動生成
    subdirs = ['Morning', 'Noon', 'Night', 'Midnight']
    for d in subdirs:
        os.makedirs(os.path.join(image_dir, d), exist_ok=True)
    
    # 現在のモードを大きく表示
    mode_text = "【ローカルAI (Ollama)】" if USE_LOCAL_AI else "【クラウドAI (Gemini)】"
    print("=" * 40)
    print(f"  AIエンジン: {mode_text}")
    print("=" * 40)
    
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            tags_cache = json.load(f)
    else:
        tags_cache = {}

    # サブフォルダ含め再帰的に画像を取得し、相対パス（例: Morning/001.png）をキーとする
    filenames = []
    for root, dirs, files in os.walk(image_dir):
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                rel_path = os.path.relpath(os.path.join(root, f), image_dir).replace('\\', '/')
                filenames.append(rel_path)
    filenames = sorted(filenames)
    
    artworks = []
    needs_processing = []
    
    for filename in filenames:
        path = os.path.join(image_dir, filename)
        basename = os.path.basename(filename)
        
        # フォルダ名から時間帯を判定
        time_zone = "未指定"
        if "Morning/" in filename: time_zone = "朝"
        elif "Noon/" in filename: time_zone = "昼"
        elif "Night/" in filename: time_zone = "夜"
        elif "Midnight/" in filename: time_zone = "深夜"
        
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
            'filename': filename, 'title': os.path.splitext(basename)[0], 
            'date': datetime.datetime.fromtimestamp(mtime).strftime('%Y.%m.%d'),
            'tags': tags, 'timestamp': mtime,
            'time_zone': time_zone
        })
        # タグがない、またはロゴが入っていない場合に処理対象にする
        if not tags or not is_watermarked:
            needs_processing.append({'filename': filename, 'watermarked': is_watermarked, 'has_tags': bool(tags)})
    
    def save():
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("const ARTWORKS_DATA = ")
            json.dump(sorted(artworks, key=lambda x: x['timestamp'], reverse=True), f, ensure_ascii=False, indent=4)
            f.write(";")
    
    def deploy(msg):
        print(f"    [LOCAL] Git に変更を記録・送信中: {msg}")
        subprocess.run(['git', 'add', '.'], capture_output=True)
        subprocess.run(['git', 'commit', '-m', f"{msg}: {datetime.datetime.now().strftime('%H:%M:%S')}"], capture_output=True)
        subprocess.run(['git', 'push', 'origin', 'main'], capture_output=True)

    if needs_processing:
        print(f"\nローカルで更新を開始 (残り {len(needs_processing)} 枚)...")
        processed_count = 0
        for item in needs_processing[:30]:
            filename = item['filename']
            path = os.path.join(image_dir, filename)
            has_changed = False
            
            # 1. ロゴ入れ
            if not item['watermarked']:
                if apply_watermark(path):
                    if filename not in tags_cache or isinstance(tags_cache[filename], list):
                        tags_cache[filename] = {'tags': tags_cache.get(filename, []), 'watermarked': True}
                    else:
                        tags_cache[filename]['watermarked'] = True
                    has_changed = True
            
            # 2. タグ付け
            target_art = None
            if not item['has_tags']:
                result = get_tags_with_retry(path)
                if result and isinstance(result, dict):
                    new_tags = result['tags']
                    new_captions = result['captions']
                    
                    if filename not in tags_cache or isinstance(tags_cache[filename], list):
                        tags_cache[filename] = {'tags': new_tags, 'captions': new_captions, 'watermarked': True}
                    else:
                        tags_cache[filename]['tags'] = new_tags
                        tags_cache[filename]['captions'] = new_captions
                        tags_cache[filename]['watermarked'] = True
                    
                    for art in artworks:
                        if art['filename'] == filename:
                            art['tags'] = new_tags
                            art['captions'] = new_captions
                            target_art = art
                    has_changed = True
            
            # 変更があればキャッシュとデータを保存
            if has_changed:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(tags_cache, f, ensure_ascii=False, indent=4)
                save()
                processed_count += 1
            
            time.sleep(1)

        if processed_count > 0:
            deploy("Update gallery data and captions")
            print(f"\n[完了] {processed_count} 枚の更新をサイトに送信しました。反映まで数分お待ちください。")
        return True
    return False

if __name__ == '__main__':
    import datetime
    # ギャラリー更新の前にアセット同期とNote RSS取得を実行
    try:
        print("[Assets] Lit.Link/Note の同期を開始します...")
        import subprocess
        subprocess.run(['python', 'download_assets.py'], check=True)
    except Exception as e:
        print(f"[Assets] 同期処理中にエラーが発生しました: {e}")
        
    had_processing = update_gallery()
    
    # ギャラリーの画像処理が何もなかった場合でも、Note等の変更があるかもしれないのでデプロイする
    try:
        status_check = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if status_check.stdout.strip():
            print("\n[LOCAL] アセットまたはNote記事に変更が検出されました。Git に送信します...")
            subprocess.run(['git', 'add', '.'], capture_output=True)
            subprocess.run(['git', 'commit', '-m', f"Sync Note and Assets: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"], capture_output=True)
            subprocess.run(['git', 'push', 'origin', 'main'], capture_output=True)
            print("[LOCAL] 送信完了！")
    except Exception as e:
        print(f"[LOCAL] Git送信中にエラーが発生しました: {e}")
