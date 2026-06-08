import os
import json
import subprocess
import time
import requests
import datetime
import uuid
import base64
import hashlib
import secrets
from flask import Flask, render_template_string, request, jsonify, send_from_directory

app = Flask(__name__)

# パスの設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(BASE_DIR, 'illustrations')
CACHE_FILE = os.path.join(BASE_DIR, 'tags_cache.json')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
DEVIANTART_SCHEDULE_FILE = os.path.join(BASE_DIR, 'deviantart_schedule.json')
DEVIANTART_TOKENS_FILE = os.path.join(BASE_DIR, 'deviantart_tokens.json')
DEVIANTART_OAUTH_STATE_FILE = os.path.join(BASE_DIR, 'deviantart_oauth_state.json')
DEVIANTART_AUTH_URL = 'https://www.deviantart.com/oauth2/authorize'
DEVIANTART_TOKEN_URL = 'https://www.deviantart.com/oauth2/token'
DEVIANTART_REDIRECT_URI = 'http://localhost:5000/auth/deviantart/callback'
DEVIANTART_SCOPE = 'basic stash publish'

# Make.com 設定
MAKE_WEBHOOK_URL = "https://hook.us2.make.com/bbo1mnja6ckamv2dx0uyn98dy85m777p"
GITHUB_PAGES_BASE_URL = "https://kadekulu.github.io/my-portfolio/"

# 正解リスト
VALID_VOCABULARY = {
    "Hair Color": ["Pink Hair", "Blue Hair", "Blonde Hair", "White Hair", "Black Hair", "Silver Hair", "Brown Hair"],
    "Hair Style": ["Twin Tails", "Wavy Hair", "Straight Hair", "Pony Tail", "Short Hair", "Long Hair", "Medium Hair"],
    "Clothing": ["School Uniform", "Dress", "Lingerie", "Swimsuit", "Casual", "Gothic"],
    "Identity": ["Airi", "Original"]
}

def is_ollama_running():
    try:
        output = subprocess.check_output('tasklist /FI "IMAGENAME eq ollama.exe"', shell=True).decode('cp932', errors='ignore')
        return "ollama.exe" in output.lower()
    except:
        return False

def start_ollama():
    if not is_ollama_running():
        print("    [System] Ollama を起動しています...")
        subprocess.Popen(["ollama", "serve"], creationflags=subprocess.CREATE_NO_WINDOW)
        time.sleep(2)

def stop_ollama():
    if is_ollama_running():
        print("    [System] Ollama を終了して VRAM を解放します...")
        subprocess.run('taskkill /F /IM ollama.exe /T', shell=True, capture_output=True)
        subprocess.run('taskkill /F /IM Ollama.exe /T', shell=True, capture_output=True)
        time.sleep(1)

def determine_time_zone(filename):
    if "Morning/" in filename: return "朝"
    if "Noon/" in filename: return "昼"
    if "Night/" in filename: return "夜"
    if "Midnight/" in filename: return "深夜"
    return "未指定"

def load_deviantart_schedule():
    if os.path.exists(DEVIANTART_SCHEDULE_FILE):
        with open(DEVIANTART_SCHEDULE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_deviantart_schedule(queue):
    with open(DEVIANTART_SCHEDULE_FILE, 'w', encoding='utf-8') as f:
        json.dump(queue, f, ensure_ascii=False, indent=4)

def load_deviantart_tokens():
    if os.path.exists(DEVIANTART_TOKENS_FILE):
        with open(DEVIANTART_TOKENS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_deviantart_tokens(tokens):
    with open(DEVIANTART_TOKENS_FILE, 'w', encoding='utf-8') as f:
        json.dump(tokens, f, ensure_ascii=False, indent=4)

def save_deviantart_oauth_state(state_data):
    with open(DEVIANTART_OAUTH_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state_data, f, ensure_ascii=False, indent=4)

def load_deviantart_oauth_state():
    if os.path.exists(DEVIANTART_OAUTH_STATE_FILE):
        with open(DEVIANTART_OAUTH_STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def get_deviantart_client_config():
    return {
        "client_id": os.getenv("DEVIANTART_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("DEVIANTART_CLIENT_SECRET", "").strip(),
        "redirect_uri": os.getenv("DEVIANTART_REDIRECT_URI", DEVIANTART_REDIRECT_URI).strip()
    }

def build_deviantart_auth_url():
    config = get_deviantart_client_config()
    if not config["client_id"]:
        raise RuntimeError("DEVIANTART_CLIENT_ID is not set in .env")

    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    state = secrets.token_urlsafe(24)
    save_deviantart_oauth_state({
        "state": state,
        "code_verifier": verifier,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    })

    params = {
        "response_type": "code",
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "scope": DEVIANTART_SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256"
    }
    from urllib.parse import urlencode
    return f"{DEVIANTART_AUTH_URL}?{urlencode(params)}"

def normalize_deviantart_tags(tags):
    normalized = []
    for tag in tags or []:
        clean = ''.join(ch for ch in str(tag).replace(' ', '_') if ch.isalnum() or ch == '_')
        if clean and clean.lower() != 'other':
            normalized.append(clean[:50])
    return normalized[:30]

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Elite Gallery - Post Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Outfit:wght@500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-color: #f8fafc;
            --accent-color: #38bdf8;
            --danger-color: #ef4444;
            --success-color: #10b981;
            --border-radius: 12px;
        }

        body { font-family: 'Inter', sans-serif; background-color: var(--bg-color); color: var(--text-color); margin: 0; padding: 20px; }
        header { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; margin-bottom: 30px; border-bottom: 1px solid #334155; padding-bottom: 20px; }
        h1 { font-family: 'Outfit', sans-serif; font-size: 2rem; margin: 0; background: linear-gradient(to right, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .btn { padding: 10px 20px; border-radius: var(--border-radius); border: none; cursor: pointer; font-weight: 600; transition: all 0.2s; }
        .btn-save { background-color: var(--accent-color); color: white; }
        .btn-save:hover { background-color: #0ea5e9; transform: scale(1.05); }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none !important; }

        .ai-switch-container { display: flex; align-items: center; justify-content: flex-end; gap: 12px; flex-wrap: wrap; }
        .ollama-status { font-size: 0.75rem; color: #94a3b8; background: #1e293b; padding: 5px 12px; border-radius: 15px; display: flex; align-items: center; border: 1px solid #334155; }
        .deviantart-status { font-size: 0.75rem; color: #94a3b8; background: #1e293b; padding: 5px 12px; border-radius: 15px; display: flex; align-items: center; gap: 8px; border: 1px solid #334155; }
        .btn-da-auth { background: #05cc47; color: #04130a; padding: 6px 10px; border-radius: 10px; font-size: 0.75rem; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 8px; }
        .status-on { background-color: var(--success-color); box-shadow: 0 0 8px var(--success-color); }
        .status-off { background-color: #64748b; }
        .ai-switch { display: flex; align-items: center; background: #334155; padding: 5px 15px; border-radius: 20px; gap: 10px; font-size: 0.9rem; }
        .switch { position: relative; display: inline-block; width: 40px; height: 20px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #475569; transition: .4s; border-radius: 20px; }
        .slider:before { position: absolute; content: ""; height: 14px; width: 14px; left: 3px; bottom: 3px; background-color: white; transition: .4s; border-radius: 50%; }
        input:checked + .slider { background-color: var(--accent-color); }
        input:checked + .slider:before { transform: translateX(20px); }
        .ai-label { font-weight: 600; color: #94a3b8; }
        .active-ai { color: var(--accent-color); }

        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; }
        .card { position: relative; background-color: var(--card-bg); border-radius: var(--border-radius); overflow: hidden; border: 1px solid #334155; display: flex; flex-direction: column; transition: transform 0.2s; }
        .card:hover { transform: translateY(-5px); border-color: var(--accent-color); }
        
        .status-badge { position: absolute; top: 10px; right: 10px; padding: 5px 10px; border-radius: 6px; font-size: 0.8rem; font-weight: bold; z-index: 10; box-shadow: 0 2px 4px rgba(0,0,0,0.5); }
        .badge-approved { background: var(--success-color); color: white; }
        
        .img-container { width: 100%; height: 200px; background-color: #000; overflow: hidden; display: flex; align-items: center; justify-content: center; }
        .img-container img { width: 100%; height: 100%; object-fit: contain; }
        .card-content { padding: 15px; }
        .filename { font-size: 0.8rem; color: #94a3b8; margin-bottom: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center; gap: 8px; }
        .tag-row { display: grid; grid-template-columns: 100px 1fr; align-items: center; margin-bottom: 8px; font-size: 0.9rem; }
        select { background-color: #334155; color: white; border: 1px solid #475569; border-radius: 4px; padding: 4px; width: 100%; }
        
        .actions { display: flex; justify-content: flex-end; align-items: center; margin-top: 10px; gap: 10px; }
        .btn-clear { background-color: transparent; color: var(--danger-color); border: 1px solid var(--danger-color); font-size: 0.8rem; padding: 5px 10px; border-radius: 6px; }
        .btn-clear:hover { background-color: var(--danger-color); color: white; }

        /* Modal Styles */
        .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.8); display: none; justify-content: center; align-items: flex-start; z-index: 2000; backdrop-filter: blur(5px); overflow-y: auto; padding: 24px; }
        .modal-content { background: var(--card-bg); width: min(960px, 100%); max-height: calc(100vh - 48px); border-radius: var(--border-radius); padding: 24px; border: 1px solid #334155; display: grid; grid-template-columns: minmax(220px, 0.9fr) minmax(0, 1.5fr); gap: 24px; overflow: hidden; }
        .modal-left { display: flex; flex-direction: column; gap: 15px; }
        .modal-left img { width: 100%; border-radius: 8px; border: 1px solid #475569; }
        .modal-right { display: flex; flex-direction: column; gap: 12px; min-height: 0; overflow-y: auto; padding-right: 4px; }
        .modal-header { font-size: 1.5rem; font-weight: bold; color: var(--accent-color); margin: 0; }
        .caption-option { background: #0f172a; padding: 12px; border-radius: 8px; border: 1px solid #334155; cursor: pointer; font-size: 0.9rem; line-height: 1.5; transition: all 0.2s; }
        .caption-option:hover { border-color: var(--accent-color); background: #1e293b; }
        .textarea-container { margin-top: 10px; }
        textarea { width: 100%; height: 120px; background: #0f172a; color: white; border: 1px solid #38bdf8; border-radius: 8px; padding: 15px; font-family: inherit; font-size: 1rem; resize: vertical; box-sizing: border-box; }
        .modal-actions { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 12px; margin-top: 12px; }
        .btn-cancel { background: #475569; color: white; }
        .btn-cancel:hover { background: #64748b; transform: scale(1.05); }
        .btn-approve { background: var(--success-color); color: white; font-size: 1.1rem; padding: 12px 30px; }
        .btn-approve:hover { background: #059669; transform: scale(1.05); }
        .btn-deviantart { background: #05cc47; color: #04130a; font-size: 1rem; padding: 12px 22px; }
        .btn-deviantart:hover { background: #39e675; transform: scale(1.05); }
        .schedule-panel { background: #0f172a; border: 1px solid #334155; border-radius: 10px; padding: 14px; display: grid; gap: 10px; }
        .schedule-panel label { display: grid; gap: 5px; color: #cbd5e1; font-size: 0.85rem; font-weight: 600; }
        .schedule-panel input,
        .schedule-panel textarea { width: 100%; box-sizing: border-box; background: #020617; color: white; border: 1px solid #475569; border-radius: 8px; padding: 10px; font-family: inherit; }
        .schedule-panel textarea { height: 110px; resize: vertical; }
        .schedule-note { color: #94a3b8; font-size: 0.78rem; line-height: 1.5; }
        .badge-da { background: #05cc47; color: #04130a; top: 48px; }
        @media (max-width: 760px) {
            .modal-content { grid-template-columns: 1fr; max-height: none; overflow: visible; }
            .modal-right { overflow: visible; }
            .modal-left img { max-height: 260px; object-fit: contain; }
        }

        #toast { position: fixed; bottom: 20px; right: 20px; padding: 15px 25px; border-radius: var(--border-radius); background-color: var(--success-color); color: white; box-shadow: 0 4px 12px rgba(0,0,0,0.3); display: none; z-index: 1000; font-weight: bold; }
    </style>
</head>
<body>
    <header>
        <h1>Elite Post Dashboard</h1>
        <div class="ai-switch-container">
            <div class="ollama-status">
                <span id="statusDot" class="status-dot status-off"></span>
                Ollama: <span id="statusText" style="font-weight: 600; margin-left: 5px;">Checking...</span>
            </div>
            <div class="deviantart-status">
                <span id="deviantartAuthText">DeviantArt: Checking...</span>
                <button class="btn btn-da-auth" onclick="startDeviantArtAuth()">認証</button>
            </div>
            <div class="ai-switch">
                <span class="ai-label" id="geminiLabel">Gemini</span>
                <label class="switch">
                    <input type="checkbox" id="aiToggle" onchange="toggleAI(this.checked)">
                    <span class="slider"></span>
                </label>
                <span class="ai-label" id="ollamaLabel">Local AI</span>
            </div>
            <button class="btn btn-save" onclick="saveAll()">変更を一括保存</button>
        </div>
    </header>

    <div class="grid" id="imageGrid">
        <!-- JSで生成 -->
    </div>

    <!-- 投稿エディターモーダル -->
    <div class="modal-overlay" id="postModal">
        <div class="modal-content">
            <div class="modal-left">
                <img id="modalImage" src="" alt="preview">
                <div id="modalTimezone" style="font-weight: bold; text-align: center; font-size: 1.2rem; color: #94a3b8;"></div>
            </div>
            <div class="modal-right">
                <h2 class="modal-header">SNS投稿を作成</h2>
                <p style="color: #94a3b8; font-size: 0.9rem; margin: 0;">AIの提案をクリックしてテキストボックスに入力し、自由に編集してください。</p>
                <div id="captionOptions" style="display: flex; flex-direction: column; gap: 10px; max-height: 250px; overflow-y: auto;">
                    <!-- AI Proposals -->
                </div>
                <div class="textarea-container">
                    <textarea id="finalCaption" placeholder="ここに最終的な投稿文を入力..."></textarea>
                </div>
                <div class="schedule-panel">
                    <div class="schedule-note">
                        DeviantArtタイトルはSNS投稿文の1行目をそのまま使います。
                    </div>
                    <label>
                        DeviantArt説明欄
                        <textarea id="deviantartDescription" placeholder="DeviantArtの説明欄に載せる文章"></textarea>
                    </label>
                    <label>
                        予約日時
                        <input id="deviantartScheduleAt" type="datetime-local">
                    </label>
                    <div class="schedule-note">
                        AI作品として送信し、NoAI設定も有効にします。実投稿はDeviantArt認証後に予約キューから実行します。
                    </div>
                </div>
                <div class="modal-actions">
                    <button class="btn btn-cancel" onclick="closePostEditor()">キャンセル</button>
                    <button class="btn btn-deviantart" id="deviantartScheduleBtn" onclick="scheduleDeviantArt()">DeviantArt予約</button>
                    <button class="btn btn-approve" id="approveBtn" onclick="approvePost()">✅ 承認 ＆ 送信</button>
                </div>
            </div>
        </div>
    </div>

    <div id="toast">保存しました！</div>

    <script>
        const VOCAB = {{ vocab | tojson }};
        let tagCache = {{ cache | tojson }};
        let deviantArtSchedules = {{ deviantart_schedule | tojson }};
        const filenames = {{ filenames | tojson }};
        let config = {{ config | tojson }};
        let currentEditFname = null;

        function getTimezoneBadge(fname) {
            if (fname.startsWith('Morning/')) return '<span style="background: #fcd34d; color: #78350f; padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: 600;">朝</span>';
            if (fname.startsWith('Noon/')) return '<span style="background: #fb923c; color: #7c2d12; padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: 600;">昼</span>';
            if (fname.startsWith('Night/')) return '<span style="background: #3b82f6; color: #eff6ff; padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: 600;">夜</span>';
            if (fname.startsWith('Midnight/')) return '<span style="background: #312e81; color: #e0e7ff; padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: 600;">深夜</span>';
            return '<span style="background: #475569; color: #f8fafc; padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: 600;">未指定</span>';
        }

        function init() {
            const toggle = document.getElementById('aiToggle');
            toggle.checked = config.USE_LOCAL_AI;
            updateAILabels(config.USE_LOCAL_AI);
            checkOllamaStatus();
            checkDeviantArtAuthStatus();
            
            const grid = document.getElementById('imageGrid');
            grid.innerHTML = '';

            filenames.forEach(fname => {
                const data = tagCache[fname] || { tags: [], watermarked: false };
                let tags = Array.isArray(data) ? data : (data.tags || []);
                while(tags.length < 4) tags.push("Other");
                
                const isApproved = data.status === 'approved';
                const daJob = deviantArtSchedules.find(job => job.filename === fname && ['queued', 'ready'].includes(job.status));

                const card = document.createElement('div');
                card.className = 'card';
                card.innerHTML = `
                    ${isApproved ? `<div class="status-badge badge-approved">✅ 承認済</div>` : ''}
                    ${daJob ? `<div class="status-badge badge-da">DA予約済</div>` : ''}
                    <div class="img-container">
                        <img src="/img/${fname}" loading="lazy">
                    </div>
                    <div class="card-content">
                        <div class="filename">
                            ${getTimezoneBadge(fname)}
                            <span style="overflow: hidden; text-overflow: ellipsis;">${fname.split('/').pop()}</span>
                        </div>
                        ${(() => {
                            const CATEGORIES = ["Hair Color", "Hair Style", "Clothing", "Identity"];
                            return CATEGORIES.map((cat, i) => {
                                const currentTag = tags[i] || "Other";
                                const isInVocab = (VOCAB[cat] || []).includes(currentTag) || currentTag === "Other";
                                return `
                                    <div class="tag-row">
                                        <span>${cat}</span>
                                        <select onchange="updateTag('${fname}', ${i}, this.value)" ${isApproved ? 'disabled' : ''}>
                                            <option value="Other" ${currentTag === 'Other' ? 'selected' : ''}>Other</option>
                                            ${!isInVocab ? `<option value="${currentTag}" selected>⚠️ ${currentTag}</option>` : ''}
                                            ${(VOCAB[cat] || []).map(opt => `<option value="${opt}" ${currentTag === opt ? 'selected' : ''}>${opt}</option>`).join('')}
                                        </select>
                                    </div>
                                `;
                            }).join('');
                        })()}
                        <div class="actions" style="margin-top: 15px; display: flex; flex-direction: column;">
                            ${isApproved 
                                ? `<button class="btn" style="background:#1e293b; color:#94a3b8; border:1px solid #334155; width:100%; cursor:not-allowed;" disabled>承認・送信済み</button>` 
                                : `<button class="btn btn-save" style="width:100%; padding:12px; font-size:1.1rem;" onclick="openPostEditor('${fname}')">✨ 投稿を作成</button>`
                            }
                        </div>
                        <div class="actions" style="margin-top: 15px;">
                            <div style="font-size: 0.7rem; color: #64748b; flex-grow: 1;">Raw: ${tags.join(', ')}</div>
                            ${!isApproved ? `<button class="btn btn-clear" onclick="clearTags('${fname}')">再判定</button>` : ''}
                        </div>
                    </div>
                `;
                grid.appendChild(card);
            });
        }

        async function checkOllamaStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                const dot = document.getElementById('statusDot');
                const text = document.getElementById('statusText');
                if (data.running) {
                    dot.className = 'status-dot status-on'; text.innerText = 'Running'; text.style.color = '#10b981';
                } else {
                    dot.className = 'status-dot status-off'; text.innerText = 'Stopped'; text.style.color = '#94a3b8';
                }
            } catch (e) {}
        }

        async function checkDeviantArtAuthStatus() {
            try {
                const res = await fetch('/api/deviantart/auth/status');
                const data = await res.json();
                const text = document.getElementById('deviantartAuthText');
                if (!data.configured) {
                    text.innerText = 'DeviantArt: .env未設定';
                    text.style.color = '#fbbf24';
                } else if (data.authenticated) {
                    text.innerText = 'DeviantArt: 認証済み';
                    text.style.color = '#10b981';
                } else {
                    text.innerText = 'DeviantArt: 未認証';
                    text.style.color = '#94a3b8';
                }
            } catch (e) {
                document.getElementById('deviantartAuthText').innerText = 'DeviantArt: 確認失敗';
            }
        }

        async function startDeviantArtAuth() {
            try {
                const res = await fetch('/api/deviantart/auth/start', { method: 'POST' });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || '認証URLを作れませんでした');
                window.open(data.auth_url, '_blank', 'noopener,noreferrer');
            } catch (e) {
                alert('DeviantArt認証エラー: ' + e.message);
            }
        }

        function updateAILabels(isLocal) {
            document.getElementById('ollamaLabel').className = isLocal ? 'ai-label active-ai' : 'ai-label';
            document.getElementById('geminiLabel').className = !isLocal ? 'ai-label active-ai' : 'ai-label';
        }

        async function toggleAI(isLocal) {
            config.USE_LOCAL_AI = isLocal; updateAILabels(isLocal);
            await fetch('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) });
            setTimeout(checkOllamaStatus, 1000);
        }

        function updateTag(fname, index, val) {
            if (!tagCache[fname]) tagCache[fname] = { tags: ["Other", "Other", "Other", "Original"], watermarked: false };
            if (Array.isArray(tagCache[fname])) tagCache[fname] = { tags: tagCache[fname], watermarked: false };
            tagCache[fname].tags[index] = val;
        }

        function clearTags(fname) {
            if (confirm(fname + ' のタグを消去して、AIで再判定させますか？')) {
                tagCache[fname] = { tags: [], watermarked: false };
                init();
            }
        }

        async function saveAll() {
            const res = await fetch('/api/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(tagCache) });
            if (res.ok) {
                const toast = document.getElementById('toast');
                toast.innerText = "変更を保存しました！"; toast.style.display = 'block'; setTimeout(() => toast.style.display = 'none', 3000);
            }
        }

        function openPostEditor(fname) {
            currentEditFname = fname;
            const data = tagCache[fname];
            let captions = data.captions || [];
            if (captions.length === 0) captions = ["イラストを追加しました！\\n\\n\\n#愛依莉"];
            
            document.getElementById('modalImage').src = `/img/${fname}`;
            document.getElementById('modalTimezone').innerHTML = getTimezoneBadge(fname) + " " + fname.split('/').pop();
            
            const optionsContainer = document.getElementById('captionOptions');
            optionsContainer.innerHTML = '';
            captions.forEach((cap, i) => {
                const div = document.createElement('div');
                div.className = 'caption-option';
                div.innerText = cap;
                div.onclick = () => { document.getElementById('finalCaption').value = cap; };
                optionsContainer.appendChild(div);
            });
            
            document.getElementById('finalCaption').value = data.final_caption || captions[0];
            document.getElementById('deviantartDescription').value = data.deviantart_description || '';
            document.getElementById('deviantartScheduleAt').value = makeDefaultScheduleTime();
            document.getElementById('postModal').style.display = 'flex';
        }

        function closePostEditor() {
            document.getElementById('postModal').style.display = 'none';
        }

        function makeTitleFromCaption(caption) {
            const firstLine = (caption || '').split('\n').map(line => line.trim()).find(Boolean) || 'Untitled';
            return firstLine.length > 50 ? firstLine.slice(0, 50) : firstLine;
        }

        function makeDefaultScheduleTime() {
            const d = new Date(Date.now() + 60 * 60 * 1000);
            d.setMinutes(0, 0, 0);
            const pad = n => String(n).padStart(2, '0');
            return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
        }

        function getCurrentTags(fname) {
            const data = tagCache[fname] || {};
            const tags = Array.isArray(data) ? data : (data.tags || []);
            return tags.filter(t => t && t !== 'Other');
        }

        async function scheduleDeviantArt() {
            const finalCaption = document.getElementById('finalCaption').value.trim();
            const title = makeTitleFromCaption(finalCaption);
            const description = document.getElementById('deviantartDescription').value.trim();
            const scheduledAt = document.getElementById('deviantartScheduleAt').value;
            const btn = document.getElementById('deviantartScheduleBtn');

            if (!currentEditFname || !finalCaption || !description || !scheduledAt) {
                alert('SNS投稿文、DeviantArt説明欄、予約日時を入力してください。');
                return;
            }

            btn.innerText = '予約中...';
            btn.disabled = true;

            try {
                const res = await fetch('/api/deviantart/schedule', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        filename: currentEditFname,
                        title,
                        final_caption: finalCaption,
                        description,
                        scheduled_at: scheduledAt,
                        tags: getCurrentTags(currentEditFname)
                    })
                });
                const result = await res.json();
                if (!res.ok) {
                    throw new Error(result.error || '予約に失敗しました');
                }

                deviantArtSchedules = result.queue;
                if (!tagCache[currentEditFname]) tagCache[currentEditFname] = {};
                tagCache[currentEditFname].final_caption = finalCaption;
                tagCache[currentEditFname].deviantart_description = description;
                closePostEditor();
                init();
                const toast = document.getElementById('toast');
                toast.innerText = 'DeviantArt予約を保存しました';
                toast.style.display = 'block';
                setTimeout(() => toast.style.display = 'none', 3000);
            } catch (e) {
                alert('DeviantArt予約エラー: ' + e.message);
            } finally {
                btn.innerText = 'DeviantArt予約';
                btn.disabled = false;
            }
        }

        async function approvePost() {
            const finalCap = document.getElementById('finalCaption').value;
            const btn = document.getElementById('approveBtn');
            btn.innerText = "送信中..."; btn.disabled = true;
            
            try {
                const res = await fetch('/api/approve', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ filename: currentEditFname, final_caption: finalCap })
                });
                
                if (res.ok) {
                    if (!tagCache[currentEditFname]) tagCache[currentEditFname] = {};
                    tagCache[currentEditFname].status = 'approved';
                    tagCache[currentEditFname].final_caption = finalCap;
                    closePostEditor();
                    init(); 
                    const toast = document.getElementById('toast');
                    toast.innerText = "承認＆SNSへ送信完了！"; toast.style.display = 'block'; setTimeout(() => toast.style.display = 'none', 3000);
                } else {
                    alert("送信に失敗しました");
                }
            } catch (e) {
                alert("エラーが発生しました: " + e);
            } finally {
                btn.innerText = "✅ 承認 ＆ 送信"; btn.disabled = false;
            }
        }

        setInterval(checkOllamaStatus, 5000);
        setInterval(checkDeviantArtAuthStatus, 15000);
        init();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = json.load(f)
    else:
        cache = {}
    
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
    else:
        config = {"USE_LOCAL_AI": True}
    
    file_with_time = []
    for root, dirs, files in os.walk(IMAGE_DIR):
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, IMAGE_DIR).replace('\\', '/')
                try:
                    mtime = os.path.getmtime(full_path)
                except OSError:
                    mtime = 0
                file_with_time.append((rel_path, mtime))
    
    # 更新日時の降順（最新のものが最初）でソート
    file_with_time.sort(key=lambda x: x[1], reverse=True)
    filenames = [x[0] for x in file_with_time]
    
    return render_template_string(
        HTML_TEMPLATE,
        vocab=VALID_VOCABULARY,
        cache=cache,
        filenames=filenames,
        config=config,
        deviantart_schedule=load_deviantart_schedule()
    )

@app.route('/img/<path:filename>')
def serve_image(filename):
    return send_from_directory(IMAGE_DIR, filename)

@app.route('/api/save', methods=['POST'])
def save_cache():
    new_cache = request.json
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_cache, f, ensure_ascii=False, indent=4)
    return jsonify({"status": "success"})

@app.route('/api/config', methods=['POST'])
def save_config():
    new_config = request.json
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_config, f, ensure_ascii=False, indent=4)
    
    if new_config.get("USE_LOCAL_AI"):
        start_ollama()
    else:
        stop_ollama()
        
    return jsonify({"status": "success"})

@app.route('/api/status')
def get_status():
    return jsonify({"running": is_ollama_running()})

@app.route('/api/deviantart/schedule', methods=['GET'])
def get_deviantart_schedule():
    return jsonify({"queue": load_deviantart_schedule()})

@app.route('/api/deviantart/auth/status')
def get_deviantart_auth_status():
    config = get_deviantart_client_config()
    tokens = load_deviantart_tokens()
    return jsonify({
        "configured": bool(config["client_id"]),
        "authenticated": bool(tokens.get("refresh_token")),
        "redirect_uri": config["redirect_uri"],
        "scope": DEVIANTART_SCOPE
    })

@app.route('/api/deviantart/auth/start', methods=['POST'])
def start_deviantart_auth():
    try:
        return jsonify({"auth_url": build_deviantart_auth_url()})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/auth/deviantart/callback')
def deviantart_auth_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    if error:
        return f"<h1>DeviantArt認証エラー</h1><p>{error}</p>", 400
    if not code or not state:
        return "<h1>DeviantArt認証エラー</h1><p>code/state がありません。</p>", 400

    state_data = load_deviantart_oauth_state()
    if state != state_data.get("state"):
        return "<h1>DeviantArt認証エラー</h1><p>state が一致しません。</p>", 400

    config = get_deviantart_client_config()
    payload = {
        "grant_type": "authorization_code",
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "code": code,
        "code_verifier": state_data.get("code_verifier")
    }
    if config["client_secret"]:
        payload["client_secret"] = config["client_secret"]

    try:
        res = requests.post(DEVIANTART_TOKEN_URL, data=payload, timeout=30)
        res.raise_for_status()
        tokens = res.json()
        if "access_token" not in tokens:
            return f"<h1>DeviantArt認証エラー</h1><pre>{json.dumps(tokens, ensure_ascii=False, indent=2)}</pre>", 400
        tokens["expires_at"] = time.time() + int(tokens.get("expires_in", 3600))
        save_deviantart_tokens(tokens)
        return """
        <h1>DeviantArt認証が完了しました</h1>
        <p>タグ編集画面に戻ってください。予約投稿の実行準備ができました。</p>
        <script>setTimeout(() => window.close(), 1200);</script>
        """
    except Exception as e:
        return f"<h1>DeviantArt認証エラー</h1><p>{e}</p>", 500

@app.route('/api/deviantart/schedule', methods=['POST'])
def create_deviantart_schedule():
    data = request.json or {}
    filename = data.get('filename')
    final_caption = (data.get('final_caption') or '').strip()
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    scheduled_at = (data.get('scheduled_at') or '').strip()

    if not filename or not final_caption or not description or not scheduled_at:
        return jsonify({"error": "filename, final_caption, description, scheduled_at are required"}), 400

    image_path = os.path.abspath(os.path.join(IMAGE_DIR, filename))
    if not image_path.startswith(os.path.abspath(IMAGE_DIR)) or not os.path.exists(image_path):
        return jsonify({"error": "image file not found"}), 404

    if not title:
        title = next((line.strip() for line in final_caption.splitlines() if line.strip()), 'Untitled')
    title = title[:50]

    try:
        local_dt = datetime.datetime.fromisoformat(scheduled_at)
    except ValueError:
        return jsonify({"error": "scheduled_at must be a valid datetime"}), 400

    if local_dt.tzinfo is None:
        local_dt = local_dt.astimezone()

    queue = load_deviantart_schedule()
    job = {
        "id": str(uuid.uuid4()),
        "platform": "deviantart",
        "filename": filename,
        "title": title,
        "final_caption": final_caption,
        "description": description,
        "tags": normalize_deviantart_tags(data.get('tags', [])),
        "scheduled_at": local_dt.astimezone(datetime.timezone.utc).isoformat(),
        "scheduled_local": scheduled_at,
        "status": "queued",
        "is_ai_generated": True,
        "noai": True,
        "is_mature": bool(data.get('is_mature', False)),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    queue.append(job)
    save_deviantart_schedule(queue)
    return jsonify({"status": "success", "job": job, "queue": queue})

@app.route('/api/approve', methods=['POST'])
def approve_post():
    data = request.json
    filename = data.get('filename')
    final_caption = data.get('final_caption')
    
    if not filename or not final_caption:
        return jsonify({"error": "Bad request"}), 400
        
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = json.load(f)
    else:
        cache = {}
        
    if filename not in cache:
        cache[filename] = {}
        
    cache[filename]['status'] = 'approved'
    cache[filename]['final_caption'] = final_caption
    
    # Save cache
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=4)
        
    # Send to Make.com Webhook
    try:
        path = os.path.join(IMAGE_DIR, filename)
        mtime = os.path.getmtime(path) if os.path.exists(path) else time.time()
        
        image_url = f"{GITHUB_PAGES_BASE_URL}illustrations/{filename}"
        payload = {
            "title": os.path.splitext(os.path.basename(filename))[0],
            "date": datetime.datetime.fromtimestamp(mtime).strftime('%Y.%m.%d'),
            "tags": cache[filename].get('tags', []),
            "captions": [final_caption], # 配列の最初の要素に最終文章を入れる
            "time_zone": determine_time_zone(filename),
            "image_url": image_url,
            "portfolio_url": GITHUB_PAGES_BASE_URL,
            "status": "承認" # 直接「承認」として送るため、スプレッドシートを開く必要がなくなる
        }
        res = requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=10)
        if res.status_code != 200:
            print(f"    [Make] 送信失敗 (Status: {res.status_code})")
            return jsonify({"error": "Make webhook failed"}), 500
    except Exception as e:
        print(f"    [Make] エラーが発生しました: {e}")
        return jsonify({"error": str(e)}), 500
        
    return jsonify({"status": "success"})

if __name__ == '__main__':
    print(f"Server starting at http://localhost:5000")
    app.run(debug=True, port=5000)
