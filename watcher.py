import os
import time
import update_gallery

def watch_folder():
    image_dir = 'illustrations'
    print(f"監視を開始しました: {image_dir}")
    print("画像の追加・削除・変更を自動で検知して反映します。")
    print("停止するには Ctrl+C を押してください。")
    
    # 前回のファイル状態（名前のセット）を記憶
    last_files = set()
    last_mtime = 0
    
    if not os.path.exists(image_dir):
        os.makedirs(image_dir)

    # 初回の状態を記録
    last_files = set(os.listdir(image_dir))

    while True:
        try:
            # 現在のファイルリストを取得
            current_files = set(os.listdir(image_dir))
            
            # フォルダ内の最大更新日時をチェック
            current_mtime = os.path.getmtime(image_dir)
            for filename in current_files:
                file_path = os.path.join(image_dir, filename)
                if os.path.exists(file_path):
                    mtime = os.path.getmtime(file_path)
                    if mtime > current_mtime:
                        current_mtime = mtime

            # 1. ファイルの顔ぶれが変わったか？（追加・削除）
            # 2. 既存のファイルが更新されたか？
            if current_files != last_files or current_mtime > last_mtime:
                if last_mtime != 0: # 初回スキップ
                    print(f"[{time.strftime('%H:%M:%S')}] 変化を検知しました（追加/削除/更新）。実行中...")
                    update_gallery.update_gallery()
                
                last_files = current_files
                last_mtime = current_mtime
                
            time.sleep(2) # 2秒おきにチェック
            
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            time.sleep(5)

if __name__ == '__main__':
    watch_folder()
