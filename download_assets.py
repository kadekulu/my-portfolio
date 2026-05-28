import os
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
JSON_OUTPUT = os.path.join(BASE_DIR, 'note_articles.json')

# ダウンロード対象のアセット情報
ASSETS_TO_DOWNLOAD = {
    'avatar.jpg': 'https://prd.resource-api.lit.link/images/creators/1db5b858-0c8c-4600-a061-dd87fbe18447/icons/d101795f-7bb6-430a-97b3-dc4924b3c2e6.jpg',
    'airi_card.png': 'https://prd.storage.lit.link/images/creators/1db5b858-0c8c-4600-a061-dd87fbe18447/profile_links/single_images/01aa1242-916f-49a6-9876-9c041c06dab3.png',
    'booth_card.jpg': 'https://prd.storage.lit.link/images/creators/1db5b858-0c8c-4600-a061-dd87fbe18447/profile_links/single_images/8638336a-bd3b-4c69-8268-4e6272df44c0.jpg'
}

def ensure_dirs():
    if not os.path.exists(ASSETS_DIR):
        os.makedirs(ASSETS_DIR)
        print(f"[Assets] Created directory: {ASSETS_DIR}")

def download_assets():
    print("[Assets] Downloading profile assets from Lit.Link...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    for filename, url in ASSETS_TO_DOWNLOAD.items():
        filepath = os.path.join(ASSETS_DIR, filename)
        if os.path.exists(filepath):
            print(f"[Assets] Already exists, skipping: {filename}")
            continue
            
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req) as response:
                with open(filepath, 'wb') as f:
                    f.write(response.read())
            print(f"[Assets] Successfully downloaded: {filename}")
        except Exception as e:
            print(f"[Assets] Failed to download {filename} from {url}: {e}")

def fetch_note_rss():
    print("[Note] Fetching Note articles from RSS feed...")
    rss_url = "https://note.com/elite_gomi/rss"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        req = urllib.request.Request(rss_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            rss_data = response.read()
            
        root = ET.fromstring(rss_data)
        
        # XMLのネームスペース定義
        namespaces = {
            'media': 'http://search.yahoo.com/mrss/',
            'note': 'https://note.com/rss/' # note独自の拡張タグ用
        }
        
        articles = []
        items = root.findall('.//item')
        
        # 最大4つの記事を抽出
        for item in items[:4]:
            title = item.find('title').text if item.find('title') is not None else "無題の記事"
            link = item.find('link').text if item.find('link') is not None else ""
            
            # 日付のパース
            pub_date_str = item.find('pubDate').text if item.find('pubDate') is not None else ""
            formatted_date = ""
            if pub_date_str:
                try:
                    # RFC 822 format: e.g. "Thu, 28 May 2026 05:00:00 +0900"
                    # 簡易的にパース
                    dt = datetime.strptime(pub_date_str[:25].strip(), "%a, %d %b %Y %H:%M:%S")
                    formatted_date = dt.strftime("%Y.%m.%d")
                except Exception:
                    formatted_date = pub_date_str
            
            # サムネイル画像の抽出
            eyecatch = ""
            # 1. <media:thumbnail> タグのチェック
            media_thumb = item.find('.//media:thumbnail', namespaces)
            if media_thumb is not None:
                eyecatch = media_thumb.text
            
            # 2. `<eyecatch>` タグ（Noteのカスタムタグ）のチェック
            if not eyecatch:
                # ETはデフォルトでプレフィックスを展開するため、{uri}local-name形式で探す
                eyecatch_tag = item.find('.//{https://note.com/rss/}eyecatch')
                if eyecatch_tag is not None:
                    eyecatch = eyecatch_tag.text

            # 3. 見つからない場合はdescriptionからimgタグをパースする（フォールバック）
            if not eyecatch:
                desc = item.find('description')
                if desc is not None and desc.text:
                    import re
                    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc.text)
                    if img_match:
                        eyecatch = img_match.group(1)

            articles.append({
                'title': title,
                'link': link,
                'date': formatted_date,
                'eyecatch': eyecatch
            })
            
        with open(JSON_OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=4)
            
        print(f"[Note] Successfully updated Note articles JSON ({len(articles)} items): {JSON_OUTPUT}")
        
    except Exception as e:
        print(f"[Note] Failed to fetch Note RSS: {e}")
        # エラー発生時はダミーデータまたは空リストを出力してフロントのクラッシュを防ぐ
        if not os.path.exists(JSON_OUTPUT):
            with open(JSON_OUTPUT, 'w', encoding='utf-8') as f:
                json.dump([], f)

if __name__ == '__main__':
    ensure_dirs()
    download_assets()
    fetch_note_rss()
