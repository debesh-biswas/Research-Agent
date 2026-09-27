"""Local scheduling, deliberately outside the graph.

The TRD keeps scheduling external: launchd or cron triggers the same `research-agent run` an
operator would type, and the AWS equivalent later is EventBridge calling that same command. Nothing
here holds a secret; a rendered schedule contains a command and paths only.
"""

import json
from datetime import time
from pathlib import Path
from typing import Literal, Protocol

from pydantic import Field, field_validator

from research_agent.config import SchedulingSettings, StrictModel, TopicSettings

SchedulerBackend = Literal["launchd", "cron", "eventbridge"]

ROLE_ARN_PLACEHOLDER = "arn:aws:iam::000000000000:role/research-agent-scheduler"
TARGET_ARN_PLACEHOLDER = "arn:aws:lambda:us-east-1:000000000000:function:research-agent-start-run"

# EventBridge cron uses three-letter day names rather than launchd's and cron's numbers.
_CRON_DAYS: dict[str, str] = {
    "sunday": "SUN",
    "monday": "MON",
    "tuesday": "TUE",
    "wednesday": "WED",
    "thursday": "THU",
    "friday": "FRI",
    "saturday": "SAT",
}

_WEEKDAYS: dict[str, int] = {
    "sunday": 0,
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
}

_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
{arguments}
  </array>
  <key>WorkingDirectory</key>
  <string>{working_directory}</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>{weekday}</integer>
    <key>Hour</key>
    <integer>{hour}</integer>
    <key>Minute</key>
    <integer>{minute}</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>{log_directory}/{topic_id}.out.log</string>
  <key>StandardErrorPath</key>
  <string>{log_directory}/{topic_id}.err.log</string>
</dict>
</plist>
"""


class ScheduleRequest(StrictModel):
    """What to schedule, and when. Validated before anything is rendered."""

    topic_id: str = Field(min_length=1)
    scheduling: SchedulingSettings
    executable: str = "research-agent"
    working_directory: Path = Path()
    log_directory: Path = Path("data/logs")
    at: time = time(7, 0)

    @field_validator("executable")
    @classmethod
    def reject_a_command_line(cls, value: str) -> str:
        """The executable is a program, not a shell string, so nothing can be smuggled into it."""
        if not value.strip() or any(character in value for character in " \t\n;&|$"):
            raise ValueError("executable must be a single program path with no shell syntax")
        return value


class ScheduleArtifact(StrictModel):
    """A ready-to-install schedule plus the one command that installs it."""

    backend: SchedulerBackend
    filename: str = Field(min_length=1)
    content: str = Field(min_length=1)
    install_hint: str = Field(min_length=1)


class Scheduler(Protocol):
    """One local scheduling backend; the AWS equivalent later implements the same shape."""

    @property
    def backend(self) -> SchedulerBackend: ...

    def render(self, request: ScheduleRequest) -> ScheduleArtifact: ...


def command(request: ScheduleRequest) -> list[str]:
    """The exact command a schedule runs, which is also what an operator can type."""
    return [request.executable, "run", request.topic_id]


class LaunchdScheduler:
    """macOS launchd agent, the local default."""

    backend: SchedulerBackend = "launchd"

    def render(self, request: ScheduleRequest) -> ScheduleArtifact:
        label = f"com.research-agent.{request.topic_id.replace('_', '-')}"
        arguments = "\n".join(f"    <string>{part}</string>" for part in command(request))
        content = _PLIST.format(
            label=label,
            arguments=arguments,
            working_directory=request.working_directory.resolve(),
            weekday=_WEEKDAYS[request.scheduling.day],
            hour=request.at.hour,
            minute=request.at.minute,
            log_directory=request.log_directory,
            topic_id=request.topic_id,
        )
        filename = f"{label}.plist"
        return ScheduleArtifact(
            backend=self.backend,
            filename=filename,
            content=content,
            install_hint=(
                f"Write this to ~/Library/LaunchAgents/{filename}, then run "
                f"`launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/{filename}`. "
                f"Remove it with `launchctl bootout gui/$(id -u)/{label}`."
            ),
        )


class CronScheduler:
    """A crontab line, for Linux or an operator who prefers cron."""

    backend: SchedulerBackend = "cron"

    def render(self, request: ScheduleRequest) -> ScheduleArtifact:
        weekday = _WEEKDAYS[request.scheduling.day]
        line = (
            f"{request.at.minute} {request.at.hour} * * {weekday} "
            f"cd {request.working_directory.resolve()} && {' '.join(command(request))} "
            f">> {request.log_directory}/{request.topic_id}.out.log 2>&1"
        )
        return ScheduleArtifact(
            backend=self.backend,
            filename=f"{request.topic_id}.crontab",
            content=line + "\n",
            install_hint=(
                "Append this line to your crontab with `crontab -e`, or install it with "
                f"`(crontab -l 2>/dev/null; cat {request.topic_id}.crontab) | crontab -`."
            ),
        )


class EventBridgeScheduler:
    """An EventBridge Scheduler schedule, rendered rather than created.

    This is the AWS substitution for launchd or cron (TRD section 50). It emits the JSON an operator
    or a deployment tool passes to `aws scheduler create-schedule`; nothing here calls AWS, so it
    needs no credentials, no dependency, and cannot become required locally. The target invokes the
    long-running worker — never the whole graph inside one Lambda (TRD section 51).
    """

    backend: SchedulerBackend = "eventbridge"

    def __init__(
        self, role_arn: str = ROLE_ARN_PLACEHOLDER, target_arn: str = TARGET_ARN_PLACEHOLDER
    ) -> None:
        self._role_arn = role_arn
        self._target_arn = target_arn

    def render(self, request: ScheduleRequest) -> ScheduleArtifact:
        name = f"research-agent-{request.topic_id.replace('_', '-')}"
        schedule = {
            "Name": name,
            "ScheduleExpression": (
                f"cron({request.at.minute} {request.at.hour} ? * "
                f"{_CRON_DAYS[request.scheduling.day]} *)"
            ),
            "ScheduleExpressionTimezone": "UTC",
            "FlexibleTimeWindow": {"Mode": "OFF"},
            "Description": f"Weekly research run for {request.topic_id}",
            "Target": {
                "Arn": self._target_arn,
                "RoleArn": self._role_arn,
                "Input": json.dumps({"command": command(request)}),
                "RetryPolicy": {"MaximumRetryAttempts": 0},
            },
        }
        return ScheduleArtifact(
            backend=self.backend,
            filename=f"{name}.schedule.json",
            content=json.dumps(schedule, indent=2, sort_keys=True) + "\n",
            install_hint=(
                f"Create it with `aws scheduler create-schedule --cli-input-json file://{name}"
                ".schedule.json` once Arn and RoleArn are real. Retries are off because the run is "
                "idempotent and long: a retry would collide with the per-topic lock."
            ),
        )


def build_scheduler(backend: SchedulerBackend) -> Scheduler:
    """Resolve a configured backend to its implementation."""
    if backend == "launchd":
        return LaunchdScheduler()
    if backend == "cron":
        return CronScheduler()
    return EventBridgeScheduler()


def render_schedule(
    topic: TopicSettings, backend: SchedulerBackend, **overrides: object
) -> ScheduleArtifact:
    """Render one topic's schedule for a backend, validating the request first."""
    request = ScheduleRequest.model_validate(
        {"topic_id": topic.id, "scheduling": topic.scheduling, **overrides}
    )
    return build_scheduler(backend).render(request)
