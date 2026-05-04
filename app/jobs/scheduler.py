from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from redis import Redis
from app.config import settings

scheduler = AsyncIOScheduler()
redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


def start_scheduler():
    """Start the job scheduler with all recurring jobs."""
    from app.jobs.workers import run_settlement_job, cleanup_stale_payments, retry_dead_letter_payments

    # Settlement job - runs at end of day (23:59)
    scheduler.add_job(
        run_settlement_job,
        CronTrigger(hour=23, minute=59),
        id="settlement_job",
        replace_existing=True,
    )

    # Cleanup job - runs every hour
    scheduler.add_job(
        cleanup_stale_payments,
        "interval",
        hours=1,
        id="cleanup_job",
        replace_existing=True,
    )

    # Dead-letter retry job - runs every 15 minutes
    scheduler.add_job(
        retry_dead_letter_payments,
        "interval",
        minutes=15,
        id="dead_letter_retry_job",
        replace_existing=True,
    )

    scheduler.start()
    print("Job scheduler started")


def stop_scheduler():
    scheduler.shutdown()
    redis_client.close()
