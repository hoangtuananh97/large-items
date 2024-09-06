### **Requirements**
An API is used to perform operations on many items in a loop, that has 2 potential problems:
- The request takes a long time to complete, so the user may suspect the operation has failed, and may retry, running multiple parallel jobs.
- Due to web server request time out of 60 seconds, the user will not get their response. It is not possible to extend the timeout beyond 60 seconds.
 
Advise how we can resolve these issues:
- Protect the server against the user submitting parallel requests, both on the server side, but also to provide the user with partial progress updates so they will get immediate and regular feedback that the task is progressing, increasing user confidence in the operation.
- Ensure that the operation will continue and complete beyond the web server 60 seconds timeout.
 
Please use Django / Python for your solution. The logic and thought process demonstrated are the most important considerations rather than truly functional code, however code presentation is important as well as the technical aspect. If you cannot settle on a single perfect solution, you may also discuss alternative solutions to demonstrate your understanding of potential trade-offs as you encounter them. Of course if you consider a solution is too time consuming you are also welcome to clarify or elaborate on potential improvements or multiple solution approaches conceptually to demonstrate understanding and planned solution.

---
To address these two challenges using Django/Python, we can leverage **Celery** for asynchronous task management, **Redis** as a message broker. Below is a structured approach to solving the problem:

### **Key Requirements**
1. **Handling long-running tasks**: The operation takes too long, leading to web server timeouts (e.g., beyond 60 seconds).
2. **Avoid parallel requests**: Users may retry the operation multiple times, running parallel tasks.
3. **Provide feedback to users**: Users need progress updates to avoid retrying unnecessarily.

### **Solution Overview**
- **Asynchronous Task Processing with Celery**: 
  - Offload the long-running operation to Celery to ensure it runs independently of the request/response cycle. This avoids the server-side timeout.
- **Task Locking Mechanism**:
  - Implement a task locking mechanism (using a database or Redis) to prevent duplicate parallel task submissions by the same user.
  - Implement idempotency checks to ensure that the same task is not processed multiple times.
- **Progress Tracking and Immediate Feedback**: 
  - Use Celery's task state to track progress and provide real-time feedback via polling or WebSockets.
  - Use multiple threads or processes to handle multiple tasks concurrently.

---

### **Step-by-Step Approach**

#### **Step 1: Asynchronous Task Processing with Celery**
To ensure the long-running process continues even after the 60-second web server timeout, offload the task to Celery, which will run the operation in the background.

**Task Example (`tasks.py`)**:
```python
# tasks.py
from celery import shared_task

@shared_task(bind=True)
def process_items(self, items):
    total = len(items)
    for i, item in enumerate(items):
        # Simulate long processing for each item
        process_single_item(item)
        # Update task state with progress
        self.update_state(state='PROGRESS', meta={'current': i+1, 'total': total})

    return {'status': 'completed', 'total_items_processed': total}
```

- **`shared_task`**: Defines a Celery task that can be run asynchronously.
- **`self.update_state()`**: Updates the progress of the task, so users can track it.

#### **Step 2: Task Locking to Prevent Parallel Requests**
##### Option 1. Implement a task locking mechanism (using a database or Redis) to prevent duplicate parallel task submissions by the same user.

Before starting the task, check if a similar task is already running for the user. You can implement this using a Redis key (or a database) as a lock.

**Task Locking Example (`views.py`)**:
```python
# views.py
from celery.result import AsyncResult
from .tasks import process_items
from django.http import JsonResponse
import redis

# Redis client to manage locks
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

def start_task(request):
    user_id = request.user.id
    lock_key = f"user:{user_id}:task_lock"

    # Check if the user already has a task running
    if redis_client.get(lock_key):
        return JsonResponse({'error': 'A task is already in progress.'}, status=400)

    # Set a lock to prevent duplicate task submissions
    redis_client.set(lock_key, '1', ex=300)  # Lock expires after 5 minutes

    # Trigger the Celery task
    items = get_items_for_processing()  # Fetch items to be processed
    task = process_items.delay(items)

    return JsonResponse({'task_id': task.id, 'message': 'Task started successfully!'})
```

- **Redis lock (`redis_client.set()`)**: Sets a lock for the user to prevent duplicate task submissions. The lock expires after a set time (e.g., 5 minutes).
- **Unlocking**: When the task completes, remove the lock. You can add this to the task's `on_success` or `on_failure` hook.

##### Option 2. Implement idempotency checks to ensure that the same task is not processed multiple times.

To implement idempotency checks in Django to ensure the same task isn't processed multiple times, we'll use the concept of idempotency keys.
1. **Create a Model for Idempotency Key (`Model.py`)**
```python
from django.db import models

class IdempotencyKey(models.Model):
    key = models.CharField(max_length=255, unique=True)  # Idempotency Key
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20, 
        choices=[
            ('PENDING', 'Pending'),
            ('IN_PROGRESS', 'In Progress'),
            ('COMPLETED', 'Completed'),
            ('FAILED', 'Failed')
        ]
    )
    result = models.TextField(null=True, blank=True)
```
- The `key` (to uniquely identify each request) (e.g: UUID,...).
- The `status` of the task.
- The `result` of the operation, if it completes successfully.

2. **Middleware for Idempotency Key (`middleware.py`)**
We can create a middleware that checks for the presence of an `Idempotency-Key` header in the request. If the key exists, it checks the database for the key's status and returns the appropriate response.
```python
class IdempotencyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        idempotency_key = request.headers.get('Idempotency-Key')

        if not idempotency_key:
            return JsonResponse({"error": "Idempotency-Key header missing"}, status=400)

        try:
            # Try to find the key in the database
            idempotency_entry = IdempotencyKey.objects.get(key=idempotency_key)
            if idempotency_entry.status == 'COMPLETED':
                # If the task has been completed, return the result
                return JsonResponse({
                    "message": "Task already completed",
                    "result": idempotency_entry.result
                }, status=200)
            elif idempotency_entry.status == 'IN_PROGRESS':
                # If the task is still in progress, return a message indicating it's in progress
                return JsonResponse({"message": "Task in progress"}, status=202)
        except IdempotencyKey.DoesNotExist:
            # If key doesn't exist, create a new entry and proceed
            IdempotencyKey.objects.create(key=idempotency_key, status='PENDING')

        # Process the request normally
        response = self.get_response(request)
        return response
```
3. **Celery Task with Idempotency Check**
In the Celery task, we can update the status of the idempotency key as the task progresses.
```python
from celery import shared_task
from .models import IdempotencyKey

@shared_task(bind=True)
def process_items(self, idempotency_key):
    try:
        # Fetch the idempotency entry
        idempotency_entry = IdempotencyKey.objects.get(key=idempotency_key)

        # Perform your long-running task here
        result = get_items_for_processing()  # Fetch items to be processed

        # Update the idempotency status and save the result
        idempotency_entry.status = 'COMPLETED'
        idempotency_entry.result = result
        idempotency_entry.save()

        return result

    except Exception as e:
        # If there's an error, mark the task as FAILED
        idempotency_entry = IdempotencyKey.objects.get(key=idempotency_key)
        idempotency_entry.status = 'FAILED'
        idempotency_entry.save()
        raise e
```
4. **Using the Idempotency Key in the Request**
When making a request to the API, include the `Idempotency-Key` header with a unique value for each request. This key will be used to track the status of the task.

#### **Step 3: Task Progress Tracking**
Celery’s `self.update_state` allows tracking the progress of the task. Users can periodically query an API endpoint to check the progress of the task.

**Task Progress API (`views.py`)**:
```python
# views.py
from celery.result import AsyncResult

def get_task_progress(request, task_id):
    task = AsyncResult(task_id)

    if task.state == 'PENDING':
        response = {'state': task.state, 'progress': 0}
    elif task.state == 'PROGRESS':
        response = {
            'state': task.state,
            'progress': (task.info.get('current', 0) / task.info.get('total', 1)) * 100,
            'current': task.info.get('current', 0),
            'total': task.info.get('total', 1),
        }
    elif task.state == 'SUCCESS':
        response = {'state': task.state, 'progress': 100, 'result': task.result}
    else:
        response = {'state': task.state, 'error': str(task.info)}

    return JsonResponse(response)
```

- **`task.state`**: Returns the current state of the task (`PENDING`, `PROGRESS`, `SUCCESS`, etc.).
- **`task.info`**: Retrieves the progress information (e.g., current items processed and total items).

#### **Step 4: Optional - Real-time Feedback Using WebSockets**
Instead of polling, you can push real-time progress updates to the frontend using WebSockets.

**WebSocket Consumer for Progress Updates (`consumers.py`)**:
```python
from channels.generic.websocket import WebsocketConsumer
import json

class TaskProgressConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()

    def disconnect(self, close_code):
        pass

    def send_progress(self, progress_data):
        self.send(text_data=json.dumps(progress_data))
```

**Sending Progress Updates via WebSocket in Celery Task**:
```python
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

@shared_task(bind=True)
def process_items(self, items, user_channel_name):
    total = len(items)
    channel_layer = get_channel_layer()

    for i, item in enumerate(items):
        # Simulate processing each item
        process_single_item(item)
        
        # Send progress update to WebSocket
        progress = (i + 1) / total * 100
        async_to_sync(channel_layer.group_send)(
            user_channel_name, {
                "type": "send.progress",
                "progress_data": {'progress': progress}
            }
        )

    return {'status': 'completed', 'total_items_processed': total}
```

The frontend can then subscribe to WebSocket events and update the progress bar in real-time.

---

### **Alternative Solutions**

1. **Polling Only**: If WebSockets are not needed, simply rely on polling via the API. This is simpler to implement but less efficient for long-running tasks.
   
2. **Database-based Locking**: Instead of Redis, task locking can be done using a database model that tracks running tasks per user. This adds some overhead but can be used if Redis is not available.

---

### **Considerations and Trade-offs**

- **Performance**: Celery and Redis are highly scalable, making them suitable for handling multiple background tasks. However, WebSocket real-time updates could add extra complexity.
- **User Experience**: Polling provides basic feedback, while WebSockets offer real-time updates, improving the user experience.
- **Task Locking**: The lock ensures that users don’t submit parallel jobs, preventing potential resource exhaustion or duplicate processing.
  
---

### **Final Summary**

- **Celery** solves the problem of long-running operations by decoupling task execution from the web request.
- **Redis-based locking** prevents users from submitting duplicate or parallel requests.
- **Progress tracking** via `self.update_state` in Celery allows you to inform the user of the task's progress, improving confidence and preventing retries.
- **Real-time feedback** can be achieved via WebSockets, but polling is a simpler alternative.

This design ensures that long-running tasks are handled asynchronously, parallel requests are prevented, and users receive timely feedback on task progress, all while avoiding the 60-second web server timeout limit.