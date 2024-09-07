import time

import redis
from celery import shared_task
from django.conf import settings
from django.core.cache import cache


@shared_task(bind=True)
def process_items_idempotency(self, items, idempotency_key):
    # Process the items
    total_items = len(items)
    for i, item in enumerate(items):
        time.sleep(2)  # Simulate time taken to process each item
        self.update_state(state='PROGRESS', meta={'current': i + 1, 'total': total_items})

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
def process_items_lock(self, items, hashing):
    lock_key = f"user:{hashing}:lock"

    # Try to acquire the lock using Redis
    is_locked = redis_client.setnx(lock_key, 'locked')

    if not is_locked:
        # If the lock exists, return immediately to avoid duplicate task submission
        print("Task already in progress for user")
        return {'message': 'Task is already in progress', 'status': 'ignored'}

    try:
        # Set an expiration on the lock to avoid indefinitely locked tasks
        redis_client.expire(lock_key, LOCK_TIMEOUT)

        # Simulate the task processing
        total_items = len(items)
        for i, item in enumerate(items):
            time.sleep(2)  # Simulate time taken to process each item
            self.update_state(state='PROGRESS', meta={'current': i + 1, 'total': total_items})

        # Task is complete
        return {'message': 'Task completed', 'total_items': total_items}

    finally:
        # Release the lock after the task is completed
        redis_client.delete(lock_key)
        print(f"Lock released for user")
