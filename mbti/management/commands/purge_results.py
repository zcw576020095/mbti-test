from django.core.management.base import BaseCommand
from mbti.models import Result, Response


class Command(BaseCommand):
    help = "Delete all MBTI test results and responses"

    def handle(self, *args, **options):
        resp_count = Response.objects.count()
        res_count = Result.objects.count()
        Response.objects.all().delete()
        Result.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f"Purged {resp_count} responses and {res_count} results."))