from django.shortcuts import render
from django.views import View
from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django_q.models import Task
from .services import notification_service

class TaskStatusView(UserPassesTestMixin, View):
    """
    Vista para consultar el estado de una tarea de fondo (polling).
    """
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff

    def get(self, request, task_id):
        # Buscamos la tarea en los registros de Django Q
        task = Task.objects.filter(id=task_id).first()
        
        context = {
            'task': task,
            'task_id': task_id
        }
        return render(request, 'notifications/partials/_task_status.html', context)

class TestNotificationView(UserPassesTestMixin, View):
    template_name = 'notifications/test_send.html'

    def test_func(self):
        """Solo permite el acceso a administradores o staff."""
        return self.request.user.is_authenticated and self.request.user.is_staff

    def get(self, request):
        context = {
            'adapters': notification_service.adapters
        }
        return render(request, self.template_name, context)

    def post(self, request):
        recipient = request.POST.get('recipient')
        subject = request.POST.get('subject', 'Test Notification')
        message = request.POST.get('message', 'This is a test notification from the UI.')
        adapter_slug = request.POST.get('adapter_slug')
        
        if not recipient:
            messages.error(request, "Recipient is required")
            return self.get(request)

        # Obtenemos resultados del servicio
        raw_results = notification_service.notify(
            recipient=recipient,
            subject=subject,
            message=message,
            adapter_slug=adapter_slug if adapter_slug != "all" else None
        )
        
        # Formateamos los resultados para la plantilla
        # Si el resultado es un string, es un task_id (asíncrono)
        processed_results = []
        for slug, res in raw_results.items():
            is_async = isinstance(res, str)
            processed_results.append({
                'slug': slug,
                'is_async': is_async,
                'value': res
            })
        
        all_success = all(bool(r['value']) for r in processed_results)
        
        context = {
            'adapters': notification_service.adapters,
            'results': processed_results,
            'all_success': all_success,
            'recipient': recipient,
            'subject': subject,
            'message': message,
            'selected_adapter': adapter_slug
        }

        if request.headers.get('HX-Request'):
            return render(request, 'notifications/_test_send.html', context)
            
        return render(request, self.template_name, context)
