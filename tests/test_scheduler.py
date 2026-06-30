from pathlib import Path

from src.scheduler import (
    LOW_PRICE_BULL_RUN_TIME,
    SYSTEMD_ANALYSIS_TIMER,
    SYSTEMD_DELIVERY_TIMER,
    SYSTEMD_ETF_TOOLKIT_TIMER,
    SYSTEMD_LOW_PRICE_BULL_TIMER,
    add_minutes,
    build_systemd_unit_specs,
    parse_systemctl_show,
    scheduled_commands,
)


def test_delivery_fallback_runs_thirty_minutes_later():
    assert add_minutes("14:10", 30) == "14:40"
    assert add_minutes("23:50", 30) == "00:20"


def test_low_price_bull_runs_at_two_pm():
    assert LOW_PRICE_BULL_RUN_TIME == "14:00"


def test_scheduled_commands_define_extensible_timer_contract(tmp_path):
    jobs = scheduled_commands("14:10", tmp_path)
    by_name = {job.name: job for job in jobs}

    assert by_name["daily-analysis"].timer_name == SYSTEMD_ANALYSIS_TIMER
    assert by_name["daily-analysis"].calendar == "Mon..Fri 14:10:00"
    assert by_name["low-price-bull"].timer_name == SYSTEMD_LOW_PRICE_BULL_TIMER
    assert by_name["final-delivery"].timer_name == SYSTEMD_DELIVERY_TIMER
    assert by_name["final-delivery"].calendar == "Mon..Fri 14:40:00"
    assert by_name["etf-toolkit-1"].timer_name == f"{SYSTEMD_ETF_TOOLKIT_TIMER}-1.timer"
    assert by_name["etf-toolkit-1"].calendar == "Mon..Fri 15:20:00"


def test_build_systemd_unit_specs_includes_services_and_enabled_timers(tmp_path):
    specs = build_systemd_unit_specs(
        project_root=tmp_path,
        run_time="14:10",
        site_project_root=tmp_path / "aiagents-stock-main",
        python_exe=Path("/usr/bin/python3"),
        site_python_exe=Path("/usr/bin/python3"),
        site_port=8503,
        site_env_file=tmp_path / "aiagents.env",
    )
    by_name = {spec.name: spec for spec in specs}

    assert by_name[SYSTEMD_ANALYSIS_TIMER].enable_now is True
    assert "ExecStart=/usr/bin/python3 main.py --run-pipeline" in by_name[
        "stock-daily-analysis.service"
    ].content
    assert "OnCalendar=Mon..Fri 14:00:00" in by_name[
        SYSTEMD_LOW_PRICE_BULL_TIMER
    ].content
    assert "ExecStart=/usr/bin/python3 main.py --run-etf-toolkit-monitor" in by_name[
        "stock-etf-toolkit-1.service"
    ].content


def test_parse_systemctl_show_multiple_units():
    output = """Id=stock-site.service
ActiveState=active
SubState=running

Id=stock-daily-analysis.timer
ActiveState=active
SubState=waiting
NextElapseUSecRealtime=Fri 2026-06-26 14:10:00 CST
"""

    units = parse_systemctl_show(output)

    assert units[0]["Id"] == "stock-site.service"
    assert units[0]["ActiveState"] == "active"
    assert units[1]["Id"] == "stock-daily-analysis.timer"
    assert units[1]["NextElapseUSecRealtime"] == "Fri 2026-06-26 14:10:00 CST"
