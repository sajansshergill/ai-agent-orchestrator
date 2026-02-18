from app.tasks.celery_app import celery

@celery.task(name="tasks.ping")
def ping() -> dict:
    return {"pong": True}