from channels.generic.websocket import WebsocketConsumer
import json
from celery.result import AsyncResult


class TaskProgressConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()

    def receive(self, text_data):
        data = json.loads(text_data)
        task_id = data['task_id']
        task = AsyncResult(task_id)

        if task.state == 'PROGRESS':
            self.send(json.dumps({
                'state': task.state,
                'current': task.info.get('current'),
                'total': task.info.get('total'),
            }))
        elif task.state == 'SUCCESS':
            self.send(json.dumps({
                'state': 'SUCCESS',
                'message': task.result['message']
            }))
