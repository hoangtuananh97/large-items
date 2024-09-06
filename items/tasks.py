import time

from celery import shared_task
from celery.exceptions import Ignore
from django.core.cache import cache
import hashlib


@shared_task(bind=True)
def process_items(self, items, user_id):
    # Generate an idempotency key
    idempotency_key = hashlib.sha256(f'{user_id}-{str(items)}'.encode()).hexdigest()

    # Check if the task has already been processed
    if cache.get(idempotency_key):
        self.update_state(state='IGNORED', meta={'message': 'Task already processed'})
        print(f'Task {idempotency_key} already processed')
        raise Ignore()

    total_items = len(items)
    for i, item in enumerate(items):
        time.sleep(3)
        # Simulate processing item
        self.update_state(state='PROGRESS', meta={'current': i+1, 'total': total_items})

    # Mark task as completed in cache for idempotency
    cache.set(idempotency_key, 'completed', timeout=86400)
    return {'message': 'Task completed', 'total_items': total_items}
