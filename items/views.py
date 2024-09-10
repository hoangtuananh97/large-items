import hashlib
import json
import time

import redis
from celery.result import AsyncResult
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import api_view

from .tasks import process_items_idempotency, process_items_lock


@csrf_exempt
@swagger_auto_schema(
    method='post',
    operation_description="Process large data",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={}
    ),
    responses={200: 'Task started', 408: 'Request Timeout', 500: 'Invalid input'}
)
@api_view(['POST'])
def process_large_data(request):
    try:
        # Simulate long running task by looping through 1 million records
        for i in range(1_000_000):
            # Simulate processing time for each record
            time.sleep(0.0001)

            # Print a message every 100,000 records
            if i % 100_000 == 0:
                print(f"Processed {i} records...")
        # If the process completes
        return JsonResponse({"status": "Process completed"}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@swagger_auto_schema(
    method='post',
    operation_description="Start a new task",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'user_id': openapi.Schema(type=openapi.TYPE_NUMBER, description='User ID')
        }
    ),
    responses={201: 'Task started', 400: 'Invalid input'}
)
@api_view(['POST'])
def start_task_idempotency(request):
    try:
        # Assume this API be validated with a token or other means
        # Parse items from request body
        body = json.loads(request.body)
        # Assume user_id is passed in the request body
        user_id = body.get('user_id', 0)
        if not user_id:
            return JsonResponse({'error': 'No user provided'}, status=400)

        # Generate an idempotency key based on user and items
        idempotency_key = hashlib.sha256(f'{user_id}'.encode()).hexdigest()
        # Check if the task has already been processed (idempotency check)
        if cache.get(idempotency_key):
            return JsonResponse({'message': 'Your task already processed'}, status=200)
        else:
            cache.set(idempotency_key, 'processed', timeout=300)  # Cached for 5m

        # Start Celery task
        task = process_items_idempotency.apply_async(args=[idempotency_key])

        # Return task_id in the response
        return JsonResponse({'task_id': task.id, "message": 'Your task is processing'}, status=202)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@swagger_auto_schema(
    method='get',
    manual_parameters=[
        openapi.Parameter(
            'task_id', openapi.IN_PATH, description="Task ID", type=openapi.TYPE_STRING
        )
    ],
    responses={
        200: openapi.Response(
            description="Task status",
            examples={
                'application/json': {
                    "state": "PROGRESS",
                    "current": 3,
                    "total": 10
                }
            }
        ),
        500: openapi.Response(description="Internal server error")
    }
)
@api_view(['GET'])
def get_task_status_idempotency(request, task_id):
    try:
        # Retrieve the task by ID
        task = AsyncResult(task_id)

        # Handle task progress
        if task.state == 'PROGRESS':
            return JsonResponse({
                'state': task.state,
                'current': task.info.get('current', 0),
                'total': task.info.get('total', 1)
            }, status=200)

        # Handle task success
        elif task.state == 'SUCCESS':
            return JsonResponse({
                'state': task.state,
                'result': task.result
            }, status=200)

        # Handle ignored task (idempotency or other reasons)
        elif task.state == 'IGNORED':
            return JsonResponse({
                'state': task.state,
                'message': task.info.get('message', 'Task ignored')
            }, status=200)

        # Handle task failure or other states
        else:
            return JsonResponse({'state': task.state}, status=200)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# APIs for lock

# Configure Redis connection using redis-py
redis_client = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB)


@csrf_exempt
@swagger_auto_schema(
    method='post',
    operation_description="Start a new task",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'user_id': openapi.Schema(type=openapi.TYPE_NUMBER, description='User ID')
        }
    ),
    responses={201: 'Task started', 400: 'Invalid input'}
)
@api_view(['POST'])
def start_task_lock(request):
    try:
        # Assume this API be validated with a token or other means
        # Parse items from request body
        body = json.loads(request.body)
        # Assume user_id is passed in the request body
        user_id = body.get('user_id', 0)
        if not user_id:
            return JsonResponse({'error': 'No user provided'}, status=400)

        # Check or set lock
        hashing = hashlib.sha256(f'{user_id}'.encode()).hexdigest()
        lock_key = f"user:{hashing}:lock"

        if redis_client.exists(lock_key):
            # If the lock exists, return immediately to avoid duplicate task submission
            print("Task already in progress for user")
            return JsonResponse({'message': 'Task is already in progress'}, status=200)
        else:
            redis_client.setnx(lock_key, 'locked')

        # Start Celery task
        task = process_items_lock.apply_async(args=[hashing])

        # Return task_id in the response
        return JsonResponse({
            'task_id': task.id,
            "hashing": hashing,
            "message": 'Your task is processing'
        }, status=202)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@swagger_auto_schema(
    method='get',
    manual_parameters=[
        openapi.Parameter(
            'hashing', openapi.IN_PATH, description="Hashing", type=openapi.TYPE_STRING,
        ),
        openapi.Parameter(
            'task_id', openapi.IN_PATH, description="Task ID", type=openapi.TYPE_STRING,
        )
    ],
    responses={
        200: openapi.Response(
            description="Task status",
            examples={
                'application/json': {
                    "status": "in_progress",
                    "details": {
                        "current": 3,
                        "total": 10
                    }
                }
            }
        ),
        404: openapi.Response(
            description="Task not found",
            examples={
                'application/json': {
                    "status": "not_found"
                }
            }
        ),
        500: openapi.Response(
            description="Task failed",
            examples={
                'application/json': {
                    "status": "failed",
                    "details": "Error details"
                }
            }
        ),
        200: openapi.Response(
            description="Task completed",
            examples={
                'application/json': {
                    "status": "completed",
                    "details": {
                        "result": "Task result data"
                    }
                }
            }
        ),
    }
)
@api_view(['GET'])
def get_task_status_lock(request):
    hashing = request.GET.get('hashing', '')
    task_id = request.GET.get('task_id', '')
    lock_key = f"user:{hashing}:lock"

    task = AsyncResult(task_id)
    # Check if the task is currently locked (i.e., in progress)
    if redis_client.exists(lock_key):

        # Check the task state (progress, failure, or success)
        if task.state == 'PROGRESS':
            task_info = task.info if task.info else {}
            return JsonResponse({'status': 'in_progress', 'details': task_info}, status=200)

        elif task.state == 'SUCCESS':
            task_info = task.result if task.result else {}
            return JsonResponse({'status': 'completed', 'details': task_info}, status=200)

        elif task.state == 'FAILURE':
            return JsonResponse({'status': 'failed', 'details': str(task.result)}, status=500)

        else:
            return JsonResponse({'status': 'unknown', 'details': task.state}, status=200)

    # If no lock exists, return not found status
    if not redis_client.exists(lock_key) and task.state == 'SUCCESS':
        task_info = task.result if task.result else {}
        return JsonResponse({'status': 'completed', 'details': task_info}, status=200)

    return JsonResponse({'status': 'not_found'}, status=404)
