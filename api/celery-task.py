from django_celery_beat.models import PeriodicTask, IntervalSchedule
import json

def main():
    # Create an interval for add_to_db (every 1.5 hours)
    schedule_add_to_db, created = IntervalSchedule.objects.get_or_create(
        every=90,  # 90 minutes (1.5 hours)
        period=IntervalSchedule.MINUTES
    )

    # Create an interval for update_profit (every 2 hours)
    schedule_update_profit, created = IntervalSchedule.objects.get_or_create(
        every=120,  # 120 minutes (2 hours)
        period=IntervalSchedule.MINUTES
    )

    # Add 'add_to_db' task
    PeriodicTask.objects.create(
        interval=schedule_add_to_db,
        name="Add to DB Task",
        task="api.tasks.main",
        kwargs=json.dumps({})  # Pass empty JSON if no arguments
    )

    # Add 'update_profit' task
    PeriodicTask.objects.create(
        interval=schedule_update_profit,
        name="Update Profit Task",
        task="api.profit.main",
        kwargs=json.dumps({})
    )

    print("Tasks added successfully!")
