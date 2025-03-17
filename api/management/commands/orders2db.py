from django.core.management.base import BaseCommand
from api.task import main

class Command(BaseCommand):
    help = "Runs task.py once"

    def handle(self, *args, **kwargs):
        print("Running task.py...")
        main()
        print("Now we wait")