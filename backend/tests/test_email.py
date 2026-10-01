import httpx

from app.core.config import settings
from app.integrations import email


def test_no_api_key_is_a_noop(monkeypatch):
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    assert email.send_email("a@b.co", "s", "<p>x</p>") is None


def test_sends_via_resend(monkeypatch):
    seen = {}

    class R:
        def raise_for_status(self): pass
        def json(self): return {"id": "msg_1"}

    def fake_post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, json=json)
        return R()

    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(settings, "EMAIL_FROM", "CreatorOps <ops@example.com>")
    monkeypatch.setattr(httpx, "post", fake_post)
    assert email.send_email("o@x.co", "Subj", "<p>hi</p>") == "msg_1"
    assert seen["url"] == "https://api.resend.com/emails"
    assert seen["headers"]["Authorization"] == "Bearer re_test"
    assert seen["json"] == {"from": "CreatorOps <ops@example.com>", "to": ["o@x.co"], "subject": "Subj", "html": "<p>hi</p>"}


def test_enqueue_failure_never_breaks_the_caller(monkeypatch):
    from app.tasks import dispatch, email_tasks

    def down(*a, **k):
        raise ConnectionError("redis down")

    monkeypatch.setattr(email_tasks.send_email_task, "delay", down)
    monkeypatch.setattr(settings, "TASKS_EAGER", False)
    dispatch.enqueue_email("a@b.co", "s", "h")  # must not raise
