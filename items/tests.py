from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from unittest.mock import patch
from celery.result import AsyncResult
import json


class TaskAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch('items.views.process_items_idempotency.apply_async')
    def test_start_task_idempotency(self, mock_apply_async):
        mock_apply_async.return_value.id = 'test_task_id'
        url = reverse('start_task_idempotency')
        data = {'items': [1, 2, 3], 'user_id': 1}
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, 202)
        content = json.loads(response.content)
        self.assertIn('task_id', content)
        self.assertEqual(content['task_id'], 'test_task_id')

    @patch('items.views.AsyncResult')
    def test_get_task_status_idempotency(self, mock_async_result):
        mock_task = mock_async_result.return_value
        mock_task.state = 'PROGRESS'
        mock_task.info = {'current': 2, 'total': 3}

        url = reverse('get_task_status_idempotency', args=['test_task_id'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content)
        self.assertEqual(content['state'], 'PROGRESS')
        self.assertEqual(content['current'], 2)
        self.assertEqual(content['total'], 3)

    @patch('items.views.process_items_lock.apply_async')
    @patch('items.views.redis_client.exists')
    @patch('items.views.redis_client.setnx')
    def test_start_task_lock(self, mock_setnx, mock_exists, mock_apply_async):
        mock_exists.return_value = False
        mock_setnx.return_value = True
        mock_apply_async.return_value.id = 'test_task_id'

        url = reverse('start_task_lock')
        data = {'items': [1, 2, 3], 'user_id': 1}
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, 202)
        content = json.loads(response.content)
        self.assertIn('task_id', content)
        self.assertEqual(content['task_id'], 'test_task_id')

    @patch('items.views.AsyncResult')
    @patch('items.views.redis_client.exists')
    def test_get_task_status_lock(self, mock_exists, mock_async_result):
        mock_exists.return_value = True
        mock_task = mock_async_result.return_value
        mock_task.state = 'PROGRESS'
        mock_task.info = {'current': 2, 'total': 3}

        url = reverse('get_task_status_lock')
        response = self.client.get(url, {'hashing': 'test_hash', 'task_id': 'test_task_id'})

        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content)
        self.assertEqual(content['status'], 'in_progress')
        self.assertEqual(content['details']['current'], 2)
        self.assertEqual(content['details']['total'], 3)