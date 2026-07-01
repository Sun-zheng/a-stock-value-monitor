from __future__ import annotations

import argparse
import re
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8506")
    parser.add_argument("--username", default="test")
    parser.add_argument("--password", default="123456")
    parser.add_argument("--run-etf", action="store_true")
    parser.add_argument("--output-dir", default="../reports/browser_smoke")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page_errors: list[str] = []
        failed_requests: list[str] = []
        console_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("requestfailed", lambda req: failed_requests.append(req.url))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        page.goto(args.url, wait_until="domcontentloaded", timeout=60_000)
        page.locator("input").first.wait_for(timeout=90_000)
        inputs = page.locator("input")
        inputs.nth(0).fill(args.username)
        inputs.nth(1).fill(args.password)
        page.get_by_text("登录", exact=True).last.click()
        page.wait_for_timeout(10_000)
        _assert_text(page, "ETF板块", failures, "login/sidebar")
        page.screenshot(path=str(output_dir / "after_login.png"), full_page=True)

        _click_visible_button(page, "每日价值策略")
        page.wait_for_timeout(8_000)
        _assert_text(page, "全局后台定时配置", failures, "daily value schedule")
        page.screenshot(path=str(output_dir / "daily_value.png"), full_page=True)

        _click_visible_button(page, "ETF策略工具箱")
        page.wait_for_timeout(10_000)
        for text in ("运行与监控配置", "监控触发", "缓存与历史", "运行ETF策略工具箱"):
            _assert_text(page, text, failures, "ETF toolkit")

        if args.run_etf:
            page.get_by_role("button", name="运行ETF策略工具箱").click(timeout=10_000)
            page.wait_for_function(
                "() => document.body.innerText.includes('分析完成') || document.body.innerText.includes('选择功能')",
                timeout=180_000,
            )
            _assert_text(page, "选择功能", failures, "ETF toolkit run")
        page.screenshot(path=str(output_dir / "etf_toolkit.png"), full_page=True)

        _click_visible_button(page, "ETF分析")
        page.wait_for_function(
            "() => document.body.innerText.includes('ETF主题') || document.body.innerText.includes('未获取到ETF快照')",
            timeout=180_000,
        )
        for text in ("ETF分析", "最低成交额", "历史起始日"):
            _assert_text(page, text, failures, "ETF analysis")
        if "未获取到ETF快照" not in page.locator("body").inner_text(timeout=10_000):
            page.wait_for_function(
                "() => document.body.innerText.includes('直接定位ETF') && document.body.innerText.includes('选中代码')",
                timeout=60_000,
            )
            for text in ("启用AI复核", "AI复核模型", "分析方式", "ETF主题", "分析模块", "选择ETF", "模糊搜索", "直接定位ETF", "选中代码"):
                _assert_text(page, text, failures, "ETF analysis")
            page.get_by_placeholder("输入代码、名称、主题，例如 300、沪深300、红利、半导体").fill("300")
            page.wait_for_timeout(3_000)
            page.get_by_placeholder("输入完整/部分代码或名称后点击定位").fill("300")
            page.get_by_role("button", name="定位ETF").click(timeout=10_000)
            page.wait_for_timeout(5_000)
            selected_code = _selected_etf_code(page)
            if not selected_code:
                failures.append("ETF analysis: no selected ETF code after direct locate")
            else:
                page.get_by_placeholder("输入完整/部分代码或名称后点击定位").fill("300 rerun")
                page.wait_for_timeout(3_000)
                selected_after_rerun = _selected_etf_code(page)
                if selected_after_rerun != selected_code:
                    failures.append(
                        f"ETF analysis: selected ETF changed after rerun {selected_code} -> {selected_after_rerun}"
                    )
            page.get_by_text("批量ETF", exact=True).click(timeout=10_000)
            page.wait_for_function(
                "() => document.body.innerText.includes('选择多只ETF') && document.body.innerText.includes('批量补充代码/名称')",
                timeout=60_000,
            )
            for text in ("选择多只ETF", "批量补充代码/名称"):
                _assert_text(page, text, failures, "ETF batch analysis")
        page.screenshot(path=str(output_dir / "etf_single_analysis.png"), full_page=True)

        _click_visible_button(page, "ETF历史记录")
        page.wait_for_timeout(5_000)
        for text in ("ETF历史记录", "data/etf_toolkit/history"):
            _assert_text(page, text, failures, "ETF history")
        page.screenshot(path=str(output_dir / "etf_history.png"), full_page=True)

        body = page.locator("body").inner_text(timeout=10_000)
        for token in ("Traceback", "ModuleNotFoundError", "ModuleNotFound"):
            if token in body:
                failures.append(f"page contains {token}")
        if page_errors:
            failures.append(f"page errors: {page_errors[:3]}")
        if failed_requests:
            failures.append(f"failed requests: {failed_requests[:3]}")
        if console_errors:
            failures.append(f"console errors: {console_errors[:3]}")
        browser.close()

    if failures:
        print("BROWSER_SMOKE_FAILED")
        for failure in failures:
            print("-", failure)
        return 2
    print("BROWSER_SMOKE_PASSED")
    print(f"screenshots: {output_dir}")
    return 0


def _click_visible_button(page, text: str) -> None:
    button = page.locator("button").filter(has_text=text).first
    button.scroll_into_view_if_needed(timeout=10_000)
    button.click(timeout=10_000)


def _assert_text(page, text: str, failures: list[str], context: str) -> None:
    body = page.locator("body").inner_text(timeout=10_000)
    if text not in body:
        failures.append(f"{context}: missing text {text}")


def _selected_etf_code(page) -> str | None:
    body = page.locator("body").inner_text(timeout=10_000)
    match = re.search(r"选中代码\s+(\d{6})", body)
    return match.group(1) if match else None


if __name__ == "__main__":
    raise SystemExit(main())
