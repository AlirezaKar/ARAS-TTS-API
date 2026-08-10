from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import settings
from app.schemas import Platform, SendResult
from app.services.messaging.base import normalize_phone


class PlaywrightMessenger:
    """
    Browser-session automation for send-by-phone when bot APIs cannot resolve chat_id.

    Uses installed Microsoft Edge by default (PLAYWRIGHT_CHANNEL=msedge)
    so you do NOT need `playwright install chromium` (CDN is often blocked in Iran).
    """

    def __init__(self, platform: Platform) -> None:
        self.platform = platform

    def send_audio(self, phone_number: str, audio_path: Path, caption: str = "") -> SendResult:
        phone = normalize_phone(phone_number)
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError:
            return SendResult(
                platform=self.platform,
                success=False,
                detail="playwright not installed",
                method="playwright",
            )

        if self.platform == Platform.whatsapp:
            return self._send_whatsapp(phone, audio_path, caption)
        if self.platform == Platform.telegram:
            return self._send_telegram_web(phone, audio_path, caption)
        if self.platform == Platform.bale:
            return self._send_bale_web(phone, audio_path, caption)
        return SendResult(
            platform=self.platform,
            success=False,
            detail=f"Unsupported platform for Playwright: {self.platform}",
            method="playwright",
        )

    def _user_data(self) -> Path:
        if self.platform == Platform.whatsapp:
            return settings.playwright_whatsapp_user_data
        if self.platform == Platform.telegram:
            return settings.playwright_telegram_user_data
        return settings.playwright_bale_user_data

    def _launch_kwargs(self, user_data: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "user_data_dir": user_data,
            "headless": settings.playwright_headless,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        channel = (settings.playwright_channel or "").strip().lower()
        if channel and channel != "chromium":
            # Use installed Microsoft Edge / Google Chrome — no browser download needed
            kwargs["channel"] = channel
        return kwargs

    def _send_whatsapp(self, phone: str, audio_path: Path, caption: str) -> SendResult:
        from playwright.sync_api import sync_playwright

        digits = phone.lstrip("+")
        url = f"https://web.whatsapp.com/send?phone={digits}"
        user_data = str(self._user_data())
        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(**self._launch_kwargs(user_data))
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=120_000)
                page.wait_for_timeout(5000)
                file_inputs = page.locator('input[type="file"]')
                if file_inputs.count() == 0:
                    attach = page.locator(
                        '[data-icon="plus"], [data-icon="attach-menu-plus"], span[data-icon="clip"]'
                    )
                    if attach.count():
                        attach.first.click()
                        page.wait_for_timeout(1000)
                file_inputs = page.locator('input[type="file"]')
                if file_inputs.count() == 0:
                    context.close()
                    return SendResult(
                        platform=Platform.whatsapp,
                        success=False,
                        detail="WhatsApp Web: file input not found (login session may be required)",
                        method="playwright",
                    )
                file_inputs.first.set_input_files(str(audio_path))
                page.wait_for_timeout(2000)
                if caption:
                    caption_box = page.locator(
                        'div[contenteditable="true"][data-tab="10"], div[contenteditable="true"]'
                    )
                    if caption_box.count():
                        caption_box.last.fill(caption)
                send_btn = page.locator('[data-icon="send"], span[data-icon="send"]')
                if send_btn.count():
                    send_btn.last.click()
                else:
                    page.keyboard.press("Enter")
                page.wait_for_timeout(3000)
                context.close()
            return SendResult(
                platform=Platform.whatsapp,
                success=True,
                detail=f"Sent via WhatsApp Web Playwright to {phone}",
                method="playwright",
            )
        except Exception as exc:  # noqa: BLE001
            return SendResult(
                platform=Platform.whatsapp,
                success=False,
                detail=f"WhatsApp Playwright error: {exc}",
                method="playwright",
            )

    def _send_telegram_web(self, phone: str, audio_path: Path, caption: str) -> SendResult:
        from playwright.sync_api import sync_playwright

        user_data = str(self._user_data())
        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(**self._launch_kwargs(user_data))
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(
                    "https://web.telegram.org/k/",
                    wait_until="domcontentloaded",
                    timeout=120_000,
                )
                page.wait_for_timeout(4000)
                search = page.locator(
                    'input[type="search"], #telegram-search-input, .input-search input'
                )
                if search.count():
                    search.first.fill(phone)
                    page.wait_for_timeout(2000)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(2000)
                file_inputs = page.locator('input[type="file"]')
                if file_inputs.count() == 0:
                    attach = page.locator(
                        '.btn-icon, button[title*="Attach"], .attach-file'
                    )
                    if attach.count():
                        attach.first.click()
                        page.wait_for_timeout(800)
                file_inputs = page.locator('input[type="file"]')
                if file_inputs.count() == 0:
                    context.close()
                    return SendResult(
                        platform=Platform.telegram,
                        success=False,
                        detail="Telegram Web: file input not found (login required)",
                        method="playwright",
                    )
                file_inputs.first.set_input_files(str(audio_path))
                page.wait_for_timeout(1500)
                if caption:
                    page.keyboard.type(caption)
                page.keyboard.press("Enter")
                page.wait_for_timeout(2500)
                context.close()
            return SendResult(
                platform=Platform.telegram,
                success=True,
                detail=f"Sent via Telegram Web Playwright to {phone}",
                method="playwright",
            )
        except Exception as exc:  # noqa: BLE001
            return SendResult(
                platform=Platform.telegram,
                success=False,
                detail=f"Telegram Playwright error: {exc}",
                method="playwright",
            )

    def _send_bale_web(self, phone: str, audio_path: Path, caption: str) -> SendResult:
        from playwright.sync_api import sync_playwright

        user_data = str(self._user_data())
        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(**self._launch_kwargs(user_data))
                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://web.bale.ai", wait_until="domcontentloaded", timeout=120_000)
                page.wait_for_timeout(5000)
                search = page.locator(
                    'input[type="search"], input[placeholder*="جست"], input'
                )
                if search.count():
                    search.first.fill(phone)
                    page.wait_for_timeout(2000)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(2000)
                file_inputs = page.locator('input[type="file"]')
                if file_inputs.count() == 0:
                    context.close()
                    return SendResult(
                        platform=Platform.bale,
                        success=False,
                        detail="Bale Web: file input not found (login session may be required)",
                        method="playwright",
                    )
                file_inputs.first.set_input_files(str(audio_path))
                page.wait_for_timeout(1500)
                if caption:
                    page.keyboard.type(caption)
                page.keyboard.press("Enter")
                page.wait_for_timeout(2500)
                context.close()
            return SendResult(
                platform=Platform.bale,
                success=True,
                detail=f"Sent via Bale Web Playwright to {phone}",
                method="playwright",
            )
        except Exception as exc:  # noqa: BLE001
            return SendResult(
                platform=Platform.bale,
                success=False,
                detail=f"Bale Playwright error: {exc}",
                method="playwright",
            )
