from __future__ import annotations

from dataclasses import dataclass

from typing import Any


@dataclass
class BrowserSession:
    browser: Any
    context: Any
    page: Any
    playwright: Any

    async def close(self) -> None:
        await self.context.close()
        await self.browser.close()
        await self.playwright.stop()


async def open_live_page(url: str, headless: bool = False) -> BrowserSession:
    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=headless,
        args=["--autoplay-policy=no-user-gesture-required"],
    )
    context = await browser.new_context()
    page = await context.new_page()
    await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    await unmute_page(page)
    return BrowserSession(browser=browser, context=context, page=page, playwright=playwright)


async def unmute_page(page: Any) -> None:
    await page.wait_for_timeout(2_000)
    for _ in range(5):
        player = page.locator(".main-player, .player-el, .xgplayer").first
        if await player.count():
            try:
                await player.hover(timeout=2_000)
            except Exception:
                pass

        muted_button = page.locator(".xgplayer-icon-muted").first
        if await muted_button.count():
            try:
                await muted_button.click(timeout=3_000)
            except Exception:
                box = await muted_button.bounding_box()
                if box:
                    await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

        await page.evaluate(
            """() => {
                for (const media of document.querySelectorAll('video,audio')) {
                    media.muted = false;
                    media.volume = 1;
                    if (typeof media.play === 'function') {
                        media.play().catch(() => {});
                    }
                }
            }"""
        )
        ready = await page.evaluate(
            """() => {
                const mediaReady = Array.from(document.querySelectorAll('video,audio')).some(
                    media => media.volume > 0 && !media.muted && !media.paused && media.readyState >= 2
                );
                return mediaReady && !document.querySelector('.xgplayer-volume-muted');
            }"""
        )
        if ready:
            break
        await page.wait_for_timeout(1_000)


async def inspect_live_state(page: Any) -> dict[str, Any]:
    return await page.evaluate(
        """() => {
            const endedKeywords = [
                '直播已结束',
                '直播结束',
                '主播已离开',
                '主播暂时离开',
                '本场直播已结束',
                '已下播',
                '回放'
            ];
            const bodyText = (document.body && document.body.innerText || '').slice(0, 5000);
            const keyword = endedKeywords.find(item => bodyText.includes(item)) || null;
            const media = Array.from(document.querySelectorAll('video,audio')).map(item => ({
                ended: item.ended,
                paused: item.paused,
                muted: item.muted,
                volume: item.volume,
                currentTime: item.currentTime,
                readyState: item.readyState,
                networkState: item.networkState,
                duration: Number.isFinite(item.duration) ? item.duration : null
            }));
            const anyEnded = media.some(item => item.ended);
            const anyPlaying = media.some(item => !item.paused && !item.ended && item.readyState >= 2);
            return {
                ended: Boolean(keyword || anyEnded),
                reason: keyword || (anyEnded ? 'media-ended' : null),
                anyPlaying,
                media
            };
        }"""
    )
