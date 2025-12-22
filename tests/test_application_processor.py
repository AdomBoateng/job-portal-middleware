import pytest

from app.services import application_processor
from app.services import job_portal_client


def test_process_match_results_for_job_portal_mapping():
    input_results = [
        {"cv_id": "1", "total_score": 0.8, "category":"REJECT", "rationale":"No fit"},
        {"cv_id": "2", "total_score": 0.9, "category":"ACCEPT", "rationale":"Great", "sim_embed":0.95},
        {"cv_id": "3", "total_score": 0.6, "category":"Maybe", "rationale":"Average", "skill_coverage":0.7}
    ]
    out = application_processor.process_match_results_for_job_portal(input_results)
    assert out[0]["category"] == "weak"
    assert out[1]["category"] == "strong"
    assert out[1]["sim_embed"] == 0.95
    assert out[2]["category"] == "maybe"
    assert out[2]["skill_coverage"] == 0.7


@pytest.mark.asyncio
async def test_send_results_to_job_portal_calls_job_portal_client(monkeypatch):
    called = {}

    async def fake_update(job_id_arg, results_arg):
        called['job_id'] = job_id_arg
        called['results'] = results_arg
        return {"ok": True}

    # Patch the client function that will be imported inside the function
    monkeypatch.setattr(job_portal_client, "update_application_match", fake_update)

    session_id = "session-123"
    job_id = "job-456"
    match_report = {"match_results": [
        {"cv_id":"1","total_score":0.5,"category":"ACCEPT","rationale":"ok"}
    ]}

    # adapt to whichever signature is present (some modules used db_session as first arg)
    import inspect
    sig = inspect.signature(application_processor.send_results_to_job_portal)
    params = list(sig.parameters.keys())
    if params and params[0] == "db_session":
        await application_processor.send_results_to_job_portal(None, session_id, job_id, match_report)
    else:
        await application_processor.send_results_to_job_portal(session_id=session_id, job_id=job_id, match_report=match_report)

    assert called.get("job_id") == job_id
    assert isinstance(called.get("results"), list)
    assert called["results"][0]["cv_id"] == "1"
    assert called["results"][0]["category"] == "strong"


@pytest.mark.asyncio
async def test_send_results_handles_match_results_dict(monkeypatch):
    called = {}

    async def fake_update(job_id_arg, results_arg):
        called['job_id'] = job_id_arg
        called['results'] = results_arg
        return {"ok": True}

    monkeypatch.setattr(job_portal_client, "update_application_match", fake_update)

    session_id = "s2"
    job_id = "j2"
    match_report = {"match_results": {"results":[{"cv_id":"x","total_score":0.1,"category":"REJECT","rationale":""}]}}

    import inspect
    sig = inspect.signature(application_processor.send_results_to_job_portal)
    params = list(sig.parameters.keys())
    if params and params[0] == "db_session":
        await application_processor.send_results_to_job_portal(None, session_id, job_id, match_report)
    else:
        await application_processor.send_results_to_job_portal(session_id=session_id, job_id=job_id, match_report=match_report)

    assert called["job_id"] == job_id
    assert called["results"][0]["category"] == "weak"
