import time

import redis
from celery import shared_task
from django.conf import settings
from django.core.cache import cache


@shared_task(bind=True)
def process_items_idempotency(self, idempotency_key):
    # Process the items
    total_items = 1_000_000
    for i in range(total_items):
        time.sleep(0.0001)

        if i % 100_000 == 0:
            self.update_state(state='PROGRESS', meta={'current': i, 'total': total_items})

    # Mark task as completed in Redis cache to prevent reprocessing
    # cache.set(idempotency_key, 'completed', timeout=300)  # Cached for 5m
    cache.delete(idempotency_key)
    return {'message': 'Task completed', 'total_items': total_items}


# For locked task processing
# Configure Redis connection using redis-py
redis_client = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB)

# Lock key timeout in seconds (e.g., 10 minutes)
LOCK_TIMEOUT = 600


@shared_task(bind=True)
def process_items_lock(self, hashing):
    lock_key = f"user:{hashing}:lock"

    try:
        # Set an expiration on the lock to avoid indefinitely locked tasks
        redis_client.expire(lock_key, LOCK_TIMEOUT)
        total_items = 1_000_000
        for i in range(total_items):
            time.sleep(0.0001)

            if i % 100_000 == 0:
                self.update_state(state='PROGRESS', meta={'current': i, 'total': total_items})

        # Task is complete
        return {'message': 'Task completed', 'total_items': total_items}

    finally:
        # Release the lock after the task is completed
        redis_client.delete(lock_key)
        print(f"Lock released for user")
