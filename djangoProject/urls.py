"""
URL configuration for djangoProject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, re_path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

from items.views import start_task_idempotency, get_task_status_idempotency, start_task_lock, get_task_status_lock, \
    process_large_data

schema_view = get_schema_view(
   openapi.Info(
      title="Task API",
      default_version='v1',
      description="API documentation for task management",
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)
urlpatterns = [
    # Swagger documentation
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    re_path(r'^swagger/$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    re_path(r'^redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('admin/', admin.site.urls),

    # API endpoints for processing large data time out (60s)
    path('process-large-items/', process_large_data, name='process_large_items'),

    # API endpoints for idempotency
    path('api/start-task-idempotency/', start_task_idempotency, name='start_task_idempotency'),
    path('api/task-status-idempotency/<str:task_id>/', get_task_status_idempotency, name='get_task_status_idempotency'),
    # API endpoints for lock
    path('api/start-task-lock/', start_task_lock, name='start_task_lock'),
    path('api/task-status-lock/', get_task_status_lock, name='get_task_status_lock'),

]
