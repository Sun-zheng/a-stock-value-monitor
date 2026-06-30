from __future__ import annotations

import argparse
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
        page.wait_for_timeout(12_000)
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


if __name__ == "__main__":
    raise SystemExit(main())
