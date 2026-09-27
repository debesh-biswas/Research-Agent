"""Local scheduling, deliberately outside the graph.

The TRD keeps scheduling external: launchd or cron triggers the same `research-agent run` an
operator would type, and the AWS equivalent later is EventBridge calling that same command. Nothing
here holds a secret; a rendered schedule contains a command and paths only.
"""

from datetime import time
from pathlib import Path
from typing import Literal, Protocol

from pydantic import Field, field_validator

from research_agent.config import SchedulingSettings, StrictModel, TopicSettings

SchedulerBackend = Literal["launchd", "cron"]

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


def build_scheduler(backend: SchedulerBackend) -> Scheduler:
    """Resolve a configured backend to its implementation."""
    return LaunchdScheduler() if backend == "launchd" else CronScheduler()


def render_schedule(
    topic: TopicSettings, backend: SchedulerBackend, **overrides: object
) -> ScheduleArtifact:
    """Render one topic's schedule for a backend, validating the request first."""
    request = ScheduleRequest.model_validate(
        {"topic_id": topic.id, "scheduling": topic.scheduling, **overrides}
    )
    return build_scheduler(backend).render(request)
