import time

from app.worker.tasks import cleanup_expired_jobs

INTERVAL = 10 * 60


while True:
    cleanup_expired_jobs()
    time.sleep(INTERVAL)