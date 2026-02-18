from fastapi import APIRouter
from app.tasks.example_tasks import ping

router = APIRouter()

@router.post("/tasks/ping")
def enqueue_ping():
    job = ping.delay()
    return {"task_id": job.id, "status": "queued"}

@router.get("/tasks/{task_id}")
def get_task_status(task_id: str):
    res = ping.AsyncResult(task_id)
    payload = {"task_id": task_id, "state": res.state}
    if res.successful():
        payload["result"] = res.result
    elif res.failed():
        payload["error"] = str(res.result)
    return payload