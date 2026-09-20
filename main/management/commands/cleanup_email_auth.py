from django.core.management.base import BaseCommand
from django.utils import timezone

from main.models import EmailRateLimit, PendingSignup


class Command(BaseCommand):
    help = 'Remove only expired signup attempts and expired email request counters.'

    def handle(self, *args, **options):
        now = timezone.now()
        pending, _ = PendingSignup.objects.filter(expires_at__lte=now).delete()
        limits, _ = EmailRateLimit.objects.filter(expires_at__lte=now).delete()
        self.stdout.write(f'Removed expired signups: {pending}; expired counters: {limits}.')
