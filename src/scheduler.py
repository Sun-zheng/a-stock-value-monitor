from __future__ import annotations

import json
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


TASK_NAME = "A股主板低估股票每日分析自动化"
FALLBACK_TASK_NAME = "A股主板低估股票每日交付兜底"
SYSTEMD_ANALYSIS_SERVICE = "stock-daily-analysis.service"
SYSTEMD_ANALYSIS_TIMER = "stock-daily-analysis.timer"
SYSTEMD_DELIVERY_SERVICE = "stock-final-delivery.service"
SYSTEMD_DELIVERY_TIMER = "stock-final-delivery.timer"
SYSTEMD_SITE_SERVICE = "stock-site.service"
SYSTEMD_LOW_PRICE_BULL_SERVICE = "stock-low-price-bull.service"
SYSTEMD_LOW_PRICE_BULL_TIMER = "stock-low-price-bull.timer"
LOW_PRICE_BULL_RUN_TIME = "14:00"


@dataclass(frozen=True)
class ScheduledCommand:
    name: str
    description: str
    service_name: str
    timer_name: str
    command: str
    calendar: str
    order: int


@dataclass(frozen=True)
class SystemdUnitSpec:
    name: str
    content: str
    enable_now: bool
    order: int


def _ps_quote(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def add_minutes(run_time: str, minutes: int) -> str:
    value = datetime.strptime(run_time, "%H:%M") + timedelta(minutes=minutes)
    return value.strftime("%H:%M")


def configure_windows_task(project_root: Path, run_time: str) -> dict:
    python_exe = Path(sys.executable).resolve()
    main_path = (project_root / "main.py").resolve()
    argument = f'"{main_path}" --run-pipeline --no-delivery'
    fallback_time = add_minutes(run_time, 30)
    fallback_argument = f'"{main_path}" --deliver-final-report'
    script = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f"$action = New-ScheduledTaskAction -Execute {_ps_quote(python_exe)} "
            f"-Argument {_ps_quote(argument)} -WorkingDirectory {_ps_quote(project_root)}",
            f"$trigger = New-ScheduledTaskTrigger -Daily -At {_ps_quote(run_time)}",
            "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun "
            "-MultipleInstances IgnoreNew -RestartCount 3 "
            "-RestartInterval (New-TimeSpan -Minutes 5) "
            "-ExecutionTimeLimit (New-TimeSpan -Hours 2) "
            "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries",
            f"Register-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} -Action $action "
            "-Trigger $trigger -Settings $settings "
            f"-Description {_ps_quote(f'Daily {run_time}; A-share trading days only; run after startup if missed.')} "
            "-Force -ErrorAction Stop | Out-Null",
            f"$fallbackAction = New-ScheduledTaskAction -Execute {_ps_quote(python_exe)} "
            f"-Argument {_ps_quote(fallback_argument)} "
            f"-WorkingDirectory {_ps_quote(project_root)}",
            f"$fallbackTrigger = New-ScheduledTaskTrigger -Daily -At {_ps_quote(fallback_time)}",
            f"Register-ScheduledTask -TaskName {_ps_quote(FALLBACK_TASK_NAME)} "
            "-Action $fallbackAction -Trigger $fallbackTrigger -Settings $settings "
            f"-Description {_ps_quote(f'Daily {fallback_time}; idempotent delivery fallback.')} "
            "-Force -ErrorAction Stop | Out-Null",
            f"$task = Get-ScheduledTask -TaskName {_ps_quote(TASK_NAME)}",
            f"$info = Get-ScheduledTaskInfo -TaskName {_ps_quote(TASK_NAME)}",
            f"$fallbackTask = Get-ScheduledTask -TaskName {_ps_quote(FALLBACK_TASK_NAME)}",
            f"$fallbackInfo = Get-ScheduledTaskInfo -TaskName {_ps_quote(FALLBACK_TASK_NAME)}",
            f"if ($task.Triggers.StartBoundary -notmatch 'T{run_time}:') "
            "{ throw '任务触发时间回读校验失败' }",
            f"if ($fallbackTask.Triggers.StartBoundary -notmatch 'T{fallback_time}:') "
            "{ throw '交付兜底触发时间回读校验失败' }",
            "[pscustomobject]@{TaskName=$task.TaskName;State=$task.State;"
            "NextRunTime=$info.NextRunTime.ToString('yyyy-MM-dd HH:mm:ss');"
            "StartWhenAvailable=$task.Settings.StartWhenAvailable;"
            "WakeToRun=$task.Settings.WakeToRun;TriggerStart=$task.Triggers.StartBoundary;"
            "Arguments=$task.Actions.Arguments;"
            "FallbackTaskName=$fallbackTask.TaskName;"
            "FallbackNextRunTime=$fallbackInfo.NextRunTime.ToString('yyyy-MM-dd HH:mm:ss');"
            "FallbackTriggerStart=$fallbackTask.Triggers.StartBoundary;"
            "FallbackArguments=$fallbackTask.Actions.Arguments} "
            "| ConvertTo-Json -Compress",
        ]
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    lines = [line for line in result.stdout.splitlines() if line.strip().startswith("{")]
    if not lines:
        raise RuntimeError(f"任务计划程序未返回状态: {result.stdout}")
    return json.loads(lines[-1])


def _run_command(args: list[str], timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _systemctl_user(*args: str, timeout: int = 90) -> subprocess.CompletedProcess:
    return _run_command(["systemctl", "--user", *args], timeout=timeout)


def _write_user_unit(name: str, content: str) -> Path:
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    path = unit_dir / name
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def scheduled_commands(run_time: str) -> list[ScheduledCommand]:
    """Standard timer jobs.

    Add future scheduled CLI jobs here. The same definitions drive unit
    generation, enablement, status collection, and tests.
    """
    fallback_time = add_minutes(run_time, 30)
    return [
        ScheduledCommand(
            name="daily-analysis",
            description="A-share daily Buffett-Munger analysis pipeline",
            service_name=SYSTEMD_ANALYSIS_SERVICE,
            timer_name=SYSTEMD_ANALYSIS_TIMER,
            command="--run-pipeline",
            calendar=f"Mon..Fri {run_time}:00",
            order=20,
        ),
        ScheduledCommand(
            name="low-price-bull",
            description="Low-price bull daily selector and email report",
            service_name=SYSTEMD_LOW_PRICE_BULL_SERVICE,
            timer_name=SYSTEMD_LOW_PRICE_BULL_TIMER,
            command="--run-low-price-bull",
            calendar=f"Mon..Fri {LOW_PRICE_BULL_RUN_TIME}:00",
            order=30,
        ),
        ScheduledCommand(
            name="final-delivery",
            description="A-share final report delivery fallback",
            service_name=SYSTEMD_DELIVERY_SERVICE,
            timer_name=SYSTEMD_DELIVERY_TIMER,
            command="--deliver-final-report",
            calendar=f"Mon..Fri {fallback_time}:00",
            order=40,
        ),
    ]


def _oneshot_service_content(
    description: str, project_root: Path, python_exe: Path, command: str
) -> str:
    return f"""
    [Unit]
    Description={description}
    After=network-online.target
    Wants=network-online.target

    [Service]
    Type=oneshot
    WorkingDirectory={project_root}
    Environment=PYTHONUNBUFFERED=1
    ExecStart={python_exe} main.py {command}
    """


def _timer_content(description: str, service_name: str, calendar: str) -> str:
    return f"""
    [Unit]
    Description=Run {description}

    [Timer]
    OnCalendar={calendar}
    Persistent=true
    Unit={service_name}

    [Install]
    WantedBy=timers.target
    """


def build_systemd_unit_specs(
    project_root: Path,
    run_time: str,
    site_project_root: Path,
    python_exe: Path,
    site_python_exe: Path,
    site_port: int,
    site_env_file: Path,
) -> list[SystemdUnitSpec]:
    specs = [
        SystemdUnitSpec(
            name=SYSTEMD_SITE_SERVICE,
            enable_now=True,
            order=10,
            content=f"""
            [Unit]
            Description=Unified stock analysis Streamlit console
            After=network-online.target
            Wants=network-online.target

            [Service]
            Type=simple
            WorkingDirectory={site_project_root}
            Environment=PYTHONUNBUFFERED=1
            Environment=A_STOCK_VALUE_MONITOR_ROOT={project_root}
            Environment=AIAGENTS_ENV_FILE={site_env_file}
            ExecStart={site_python_exe} -m streamlit run frontend/app.py --server.port {site_port} --server.address 127.0.0.1 --server.headless true
            Restart=always
            RestartSec=8
            TimeoutStopSec=20

            [Install]
            WantedBy=default.target
            """,
        )
    ]
    for job in scheduled_commands(run_time):
        specs.append(
            SystemdUnitSpec(
                name=job.timer_name,
                content=_timer_content(job.description, job.service_name, job.calendar),
                enable_now=True,
                order=job.order,
            )
        )
        specs.append(
            SystemdUnitSpec(
                name=job.service_name,
                content=_oneshot_service_content(
                    job.description, project_root, python_exe, job.command
                ),
                enable_now=False,
                order=job.order + 100,
            )
        )
    return sorted(specs, key=lambda spec: spec.order)


def systemd_unit_names() -> list[str]:
    return [
        spec.name
        for spec in build_systemd_unit_specs(
            project_root=Path.cwd(),
            run_time="14:10",
            site_project_root=Path.cwd() / "aiagents-stock-main",
            python_exe=Path(sys.executable),
            site_python_exe=Path(sys.executable),
            site_port=8503,
            site_env_file=Path.home()
            / ".config"
            / "a-stock-value-monitor"
            / "aiagents.env",
        )
    ]


def configure_systemd_user_services(
    project_root: Path,
    run_time: str,
    site_project_root: Path | None = None,
    python_exe: Path | None = None,
    site_python_exe: Path | None = None,
    site_port: int = 8503,
) -> dict:
    """Install and enable user-level systemd timers for this project."""
    python_exe = python_exe or project_root / ".venv/bin/python"
    if not python_exe.exists():
        python_exe = Path(sys.executable)
    site_project_root = site_project_root or project_root / "aiagents-stock-main"
    site_python_exe = site_python_exe or site_project_root / ".venv/bin/python"
    site_env_file = Path.home() / ".config" / "a-stock-value-monitor" / "aiagents.env"

    specs = build_systemd_unit_specs(
        project_root=project_root,
        run_time=run_time,
        site_project_root=site_project_root,
        python_exe=python_exe,
        site_python_exe=site_python_exe,
        site_port=site_port,
        site_env_file=site_env_file,
    )
    for spec in specs:
        _write_user_unit(spec.name, spec.content)
    reload_result = _systemctl_user("daemon-reload")
    if reload_result.returncode:
        raise RuntimeError((reload_result.stderr or reload_result.stdout).strip())
    enable_result = _systemctl_user(
        "enable",
        "--now",
        *(spec.name for spec in specs if spec.enable_now),
    )
    if enable_result.returncode:
        raise RuntimeError((enable_result.stderr or enable_result.stdout).strip())
    return systemd_status()


def systemd_status() -> dict:
    units = systemd_unit_names()
    result = _systemctl_user(
        "show",
        *units,
        "--property=Id,ActiveState,SubState,UnitFileState,NextElapseUSecRealtime,LastTriggerUSec",
    )
    if result.returncode:
        return {"available": False, "error": (result.stderr or result.stdout).strip()}
    return {"available": True, "units": parse_systemctl_show(result.stdout)}


def parse_systemctl_show(output: str) -> list[dict]:
    entries: list[dict] = []
    current: dict[str, str] = {}
    for line in output.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue
        key, _, value = line.partition("=")
        current[key] = value
    if current:
        entries.append(current)
    return entries


def configure_native_schedule(project_root: Path, run_time: str) -> dict:
    if platform.system().lower() == "windows":
        return {"kind": "windows-task", "status": configure_windows_task(project_root, run_time)}
    return {"kind": "systemd-user", "status": configure_systemd_user_services(project_root, run_time)}


def native_schedule_status() -> dict:
    if platform.system().lower() == "windows":
        return {"kind": "windows-task", "status": {}}
    return {"kind": "systemd-user", "status": systemd_status()}
