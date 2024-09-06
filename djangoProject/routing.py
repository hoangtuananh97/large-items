from django.urls import path
from items.consumers import TaskProgressConsumer

websocket_urlpatterns = [
    path('ws/progress/', TaskProgressConsumer.as_asgi()),
]
