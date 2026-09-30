from core.memory import MemoryStore


def test_memory_is_scoped_by_run_id():
    store = MemoryStore()
    store.add("run-a", "test", "A")
    store.add("run-b", "test", "B")

    rows_a = store.recent(run_id="run-a")
    rows_b = store.recent(run_id="run-b")

    assert any(r["content"] == "A" for r in rows_a)
    assert not any(r["content"] == "B" for r in rows_a)
    assert any(r["content"] == "B" for r in rows_b)
