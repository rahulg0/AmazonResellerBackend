from django.core.management.base import BaseCommand
from api.profit import main
class Command(BaseCommand):
    help = "Runs profit task once"

    def handle(self, *args, **kwargs):
        print("Running profit task...")
        main()
        print("Now we wait")
