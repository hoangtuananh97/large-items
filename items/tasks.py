import time

from celery import shared_task
from django.core.cache import cache


@shared_task(bind=True)
def process_items(self, items, idempotency_key):
    # Process the items
    total_items = len(items)
    for i, item in enumerate(items):
        time.sleep(3)  # Simulate time taken to process each item
        self.update_state(state='PROGRESS', meta={'current': i + 1, 'total': total_items})

    # Mark task as completed in Redis cache to prevent reprocessing
    cache.set(idempotency_key, 'completed', timeout=300)  # Cached for 5m

    return {'message': 'Task completed', 'total_items': total_items}
