import os
import time

from deviantart_poster import process_due_posts


def main():
    interval = int(os.getenv("DEVIANTART_SCHEDULER_INTERVAL", "60"))
    dry_run = os.getenv("DEVIANTART_DRY_RUN", "true").lower() != "false"
    mode = "dry-run" if dry_run else "live"
    print(f"DeviantArt scheduler started ({mode}, every {interval}s)")

    while True:
        try:
            processed = process_due_posts(dry_run=dry_run)
            for job in processed:
                print(f"{job.get('id')} {job.get('filename')} -> {job.get('status')}")
        except Exception as exc:
            print(f"Scheduler error: {exc}")
        time.sleep(interval)


if __name__ == "__main__":
    main()
