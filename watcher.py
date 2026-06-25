import os
import time
import update_gallery

def watch_folder():
    image_dir = 'illustrations'
    print(f"監視を開始しました: {image_dir}")
    print("画像の追加・削除を最優先で反映し、バックグラウンドでAI分析を行います。")
    print("停止するには Ctrl+C を押してください。")
    
    last_files = set()
    last_mtime = 0
    work_remains = False # AI分析が残っているか
    
    if not os.path.exists(image_dir):
        os.makedirs(image_dir)

    last_files = set(os.listdir(image_dir))

    while True:
        try:
            current_files = set(os.listdir(image_dir))
            current_mtime = os.path.getmtime(image_dir)
            
            # 最新のファイル更新もチェック
            max_mtime = current_mtime
            for filename in current_files:
                file_path = os.path.join(image_dir, filename)
                if os.path.exists(file_path):
                    m = os.path.getmtime(file_path)
                    if m > max_mtime: max_mtime = m

            # 変化があった場合、またはAI分析が残っている場合
            if current_files != last_files or max_mtime > last_mtime or work_remains:
                
                # 変化があった場合はログを出す
                if current_files != last_files or max_mtime > last_mtime:
                    if last_mtime != 0:
                        print(f"[{time.strftime('%H:%M:%S')}] 新しい変化を検知しました！即時反映します。")
                
                # 更新実行（戻り値で仕事が残っているか確認）
                work_remains = update_gallery.update_gallery(only_watermark=True)
                
                last_files = current_files
                last_mtime = max_mtime
                
                # AI分析が残っている場合は、少し短めの間隔で再開
                if work_remains:
                    time.sleep(3) 
                    continue

            time.sleep(2) # 通常の見回り間隔
            
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            time.sleep(5)

if __name__ == '__main__':
    watch_folder()
