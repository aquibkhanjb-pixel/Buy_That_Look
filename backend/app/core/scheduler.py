"""
APScheduler background scheduler — daily price drop checks.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.logging import logger

_scheduler: BackgroundScheduler | None = None


def _cleanup_old_chat_history() -> None:
    """Delete chat sessions older than 30 days."""
    from datetime import datetime, timedelta
    from app.db.database import SessionLocal
    from app.db.models import ChatSession
    from sqlalchemy import text

    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=30)
        result = db.execute(
            text("DELETE FROM chat_sessions WHERE updated_at < :cutoff"),
            {"cutoff": cutoff},
        )
        db.commit()
        logger.info(f"Chat history cleanup: removed {result.rowcount} old session(s)")
    except Exception as exc:
        logger.warning(f"Chat history cleanup failed: {exc}")
    finally:
        db.close()


def start_scheduler() -> None:
    """Start the background scheduler (call once on app startup)."""
    global _scheduler

    # Import here to avoid circular deps at module load time
    from app.services.price_checker import run_price_checks

    _scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    _scheduler.add_job(
        run_price_checks,
        trigger=CronTrigger(hour=9, minute=0),  # Daily at 09:00 IST
        id="price_drop_check",
        name="Daily Price Drop Check",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        _cleanup_old_chat_history,
        trigger=CronTrigger(hour=2, minute=0),  # Daily at 02:00 IST
        id="chat_history_cleanup",
        name="30-day Chat History Cleanup",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info("APScheduler started — price checks 09:00 IST, history cleanup 02:00 IST")


def stop_scheduler() -> None:
    """Gracefully stop the scheduler (call on app shutdown)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
