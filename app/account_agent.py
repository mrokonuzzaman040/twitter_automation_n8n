"""One agent per account. It runs research -> content -> media -> schedule on each cycle,
and publishes due posts in between. Pause / resume / stop are honoured at every checkpoint."""
import threading
import time
from datetime import datetime, timedelta, timezone

from . import content, db, hooks, media, publisher, research, scheduler

RETRY_AFTER_FAILURE = timedelta(minutes=30)
PUBLISH_EVERY = 30  # seconds


class StopAgent(Exception):
    pass


class Control:
    """The agent's link to the control database: reports status, obeys the desired state."""

    def __init__(self, account_id):
        self.id = account_id
        self._status, self._task, self._paused = "starting", "", False

    def status(self, status, task=""):
        self._status, self._task = status, task
        db.update_account(self.id, agent_status=status, current_task=task, heartbeat_at=db.now())

    def task(self, task):
        self.status("working", task)

    def checkpoint(self) -> dict:
        """Block while paused, raise StopAgent when stopped, otherwise return the fresh account row."""
        while True:
            a = db.get_account(self.id)
            if not a or a["deleted"] or a["desired_state"] == "stopped":
                raise StopAgent()
            if a["desired_state"] == "paused":
                if not self._paused:
                    self._paused = True
                    db.log_event(self.id, "agent", "Paused")
                db.update_account(self.id, agent_status="paused", heartbeat_at=db.now())
                time.sleep(2)
                continue
            if self._paused:
                self._paused = False
                db.log_event(self.id, "agent", "Resumed")
                self.status(self._status, self._task)
            return a

    def sleep(self, seconds):
        for _ in range(int(seconds)):
            time.sleep(1)
            self.checkpoint()


class AccountAgent(threading.Thread):
    def __init__(self, account_id):
        super().__init__(name=f"account-{account_id}", daemon=True)
        self.id = account_id
        self.ctl = Control(account_id)

    def run(self):
        db.log_event(self.id, "agent", "Agent started")
        last_publish = 0
        try:
            while True:
                try:
                    a = self.ctl.checkpoint()
                    if time.time() - last_publish >= PUBLISH_EVERY:
                        last_publish = time.time()
                        publisher.publish_due(a, self.ctl)
                    if a["run_now"] or not a["next_cycle_at"] or a["next_cycle_at"] <= db.now():
                        self.cycle(a)
                    self.ctl.status("idle", "Waiting for next cycle")
                    self.ctl.sleep(5)
                except StopAgent:
                    raise
                except Exception as e:  # keep the agent alive through unexpected errors
                    db.log_event(self.id, "agent", f"Unexpected error: {e!r}", "error")
                    db.update_account(self.id, last_error=str(e)[:500])
                    self.ctl.status("error", "Recovering from an error")
                    self.ctl.sleep(60)
        except StopAgent:
            db.log_event(self.id, "agent", "Agent stopped")
        finally:
            db.update_account(self.id, agent_status="stopped", current_task="")

    def cycle(self, a):
        with db.account(self.id) as c:
            run_id = c.execute("INSERT INTO runs(started_at, status) VALUES(?, 'running')", (db.now(),)).lastrowid
        db.update_account(self.id, run_now=0)
        db.log_event(self.id, "agent", f"Cycle #{run_id} started")
        status, error, retry = "done", "", timedelta(hours=int(a["cycle_hours"]))
        try:
            slots = scheduler.free_slots(a)
            if not slots:
                db.log_event(self.id, "scheduler", "All upcoming slots already have content - nothing to create")
            else:
                brief = research.run(a, self.ctl, run_id)
                posts = content.generate(a, brief, len(slots), self.ctl)
                media.attach(a, posts, self.ctl)
                saved = scheduler.schedule(a, posts, slots, run_id, self.ctl)
                mode = "scheduled for auto-posting" if a["post_mode"] == "auto" else "waiting for your approval"
                db.log_event(self.id, "agent", f"Cycle #{run_id} done: {saved} posts {mode}")
        except StopAgent:
            status, error = "stopped", "Stopped by user"
            raise
        except Exception as e:
            status, error, retry = "failed", str(e)[:500], RETRY_AFTER_FAILURE
            db.log_event(self.id, "agent", f"Cycle #{run_id} failed: {error}", "error")
            hooks.emit("cycle_failed", a, {"run_id": run_id, "error": error})
        finally:
            with db.account(self.id) as c:
                c.execute("UPDATE runs SET finished_at=?, status=?, error=? WHERE id=?", (db.now(), status, error, run_id))
            if status != "stopped":
                nxt = (datetime.now(timezone.utc) + retry).isoformat(timespec="seconds")
                db.update_account(self.id, last_cycle_at=db.now(), next_cycle_at=nxt, last_error=error)
