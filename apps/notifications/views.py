from django.shortcuts import render
from django.views import View
from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from .services import notification_service

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

        # Enviamos la notificación
        results = notification_service.notify(
            recipient=recipient,
            subject=subject,
            message=message,
            adapter_slug=adapter_slug if adapter_slug != "all" else None,
            use_transaction=False # Envío inmediato para feedback en UI
        )
        
        all_success = all(results.values())
        
        return render(request, self.template_name, {
            'adapters': notification_service.adapters,
            'last_results': results,
            'all_success': all_success,
            'recipient': recipient,
            'subject': subject,
            'message': message,
            'selected_adapter': adapter_slug
        })
