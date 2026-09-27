from datetime import time
from pathlib import Path
from typing import Literal, cast

import pytest
from pydantic import ValidationError

from research_agent.config import SchedulingSettings, TopicSettings
from research_agent.operations.scheduling import (
    CronScheduler,
    LaunchdScheduler,
    SchedulerBackend,
    ScheduleRequest,
    build_scheduler,
    command,
    render_schedule,
)

Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def topic(day: Weekday = "sunday") -> TopicSettings:
    return TopicSettings.model_validate(
        {
            "id": "spatial_intelligence",
            "name": "Spatial Intelligence",
            "scheduling": {"frequency": "weekly", "day": day},
        }
    )


def request(**overrides: object) -> ScheduleRequest:
    payload: dict[str, object] = {
        "topic_id": "spatial_intelligence",
        "scheduling": SchedulingSettings(day="sunday"),
        "working_directory": Path(),
        "at": time(7, 30),
    }
    payload.update(overrides)
    return ScheduleRequest.model_validate(payload)


def test_the_scheduled_command_is_the_one_an_operator_would_type() -> None:
    assert command(request()) == ["research-agent", "run", "spatial_intelligence"]


def test_a_launchd_agent_is_deterministic_and_weekly() -> None:
    first = LaunchdScheduler().render(request())
    second = LaunchdScheduler().render(request())

    assert first.content == second.content
    assert first.filename == "com.research-agent.spatial-intelligence.plist"
    assert "<key>Weekday</key>" in first.content and "<integer>0</integer>" in first.content
    assert "<integer>7</integer>" in first.content and "<integer>30</integer>" in first.content
    assert "launchctl bootstrap" in first.install_hint


def test_a_cron_line_is_deterministic_and_weekly() -> None:
    artifact = CronScheduler().render(request(scheduling=SchedulingSettings(day="wednesday")))

    assert artifact.content.startswith("30 7 * * 3 cd ")
    assert "research-agent run spatial_intelligence" in artifact.content
    assert "crontab" in artifact.install_hint


def test_each_weekday_maps_to_its_own_number() -> None:
    numbers = [
        CronScheduler().render(request(scheduling=SchedulingSettings(day=day))).content.split()[4]
        for day in cast(tuple[Weekday, ...], ("sunday", "monday", "friday", "saturday"))
    ]

    assert numbers == ["0", "1", "5", "6"]


def test_no_secret_or_shell_syntax_can_reach_a_rendered_schedule() -> None:
    with pytest.raises(ValidationError):
        request(executable="RESEARCH_AGENT_MODELS__NIM__API_KEY=abc research-agent")

    with pytest.raises(ValidationError):
        request(executable="research-agent; curl evil.example")


def test_a_rendered_schedule_contains_no_environment_values() -> None:
    for backend in cast(tuple[SchedulerBackend, ...], ("launchd", "cron")):
        artifact = render_schedule(topic(), backend, at=time(7, 0))

        assert "API_KEY" not in artifact.content
        assert "RESEARCH_AGENT_" not in artifact.content


def test_the_backend_factory_resolves_both_backends() -> None:
    assert build_scheduler("launchd").backend == "launchd"
    assert build_scheduler("cron").backend == "cron"
