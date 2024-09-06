import json
import uuid

from django.http import JsonResponse
from celery.result import AsyncResult
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .tasks import process_items


@csrf_exempt
@require_http_methods(["POST"])
def start_task(request):
    try:
        # Assume this API be validated with a token or other means
        # Parse items from request body
        body = json.loads(request.body)
        items = body.get('items', [])
        # Assume user_id is passed in the request body
        user_id = body.get('user_id', 0)

        if not items:
            return JsonResponse({'error': 'No items provided'}, status=400)

        # Start Celery task
        task = process_items.apply_async(args=[items, user_id])

        # Return task_id in the response
        return JsonResponse({'task_id': task.id}, status=202)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_task_status(request, task_id):
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
