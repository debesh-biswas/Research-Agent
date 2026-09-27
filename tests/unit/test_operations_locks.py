import os
from pathlib import Path

import pytest

from research_agent.operations.locks import RunLocked, lock_path, run_lock

TOPIC_ID = "spatial_intelligence"


def test_the_lock_is_held_during_a_run_and_released_after(tmp_path: Path) -> None:
    with run_lock(tmp_path, TOPIC_ID) as path:
        assert path.is_file()
        assert path.read_text(encoding="utf-8").strip() == str(os.getpid())

    assert not path.exists()


def test_a_second_run_of_the_same_topic_is_refused(tmp_path: Path) -> None:
    held = run_lock(tmp_path, TOPIC_ID)
    held.__enter__()
    try:
        with pytest.raises(RunLocked, match="in progress"), run_lock(tmp_path, TOPIC_ID):
            pass
    finally:
        held.__exit__(None, None, None)


def test_another_topic_is_not_blocked(tmp_path: Path) -> None:
    with run_lock(tmp_path, TOPIC_ID), run_lock(tmp_path, "other_topic") as second:
        assert second.is_file()


def test_the_lock_is_released_even_when_the_run_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError), run_lock(tmp_path, TOPIC_ID):
        raise RuntimeError("the run failed")

    assert not lock_path(tmp_path, TOPIC_ID).exists()


def test_a_lock_left_by_a_dead_process_is_reclaimed(tmp_path: Path) -> None:
    path = lock_path(tmp_path, TOPIC_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("999999999\n", encoding="utf-8")

    with run_lock(tmp_path, TOPIC_ID) as reclaimed:
        assert reclaimed.read_text(encoding="utf-8").strip() == str(os.getpid())


def test_an_unreadable_lock_is_treated_as_held(tmp_path: Path) -> None:
    path = lock_path(tmp_path, TOPIC_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not a pid", encoding="utf-8")

    with pytest.raises(RunLocked), run_lock(tmp_path, TOPIC_ID):
        pass
