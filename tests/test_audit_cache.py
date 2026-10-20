from app.services import storage
from app.services.storage import ObservationRepository


def _repo(result):
    r = ObservationRepository.__new__(ObservationRepository)
    r.calls = 0

    def build():
        r.calls += 1
        return result

    r._build_pipeline_audit = build
    return r


def test_audit_with_data_is_cached_then_invalidated():
    storage.invalidate_cache()
    r = _repo({"reports_summary": {"total_public": 5}, "logs": []})
    r.get_pipeline_audit(); r.get_pipeline_audit()
    assert r.calls == 1
    storage.invalidate_cache()
    r.get_pipeline_audit()
    assert r.calls == 2


def test_empty_or_failed_audit_is_never_cached():
    storage.invalidate_cache()
    r = _repo({"reports_summary": {"total_public": 0, "total_raw": 0}, "logs": []})
    r.get_pipeline_audit(); r.get_pipeline_audit()
    assert r.calls == 2
