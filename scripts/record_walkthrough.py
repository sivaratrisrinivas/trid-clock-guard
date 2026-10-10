# Records the walkthrough: headless Playwright against the live demo, then ffmpeg to H.264 (see README).
import asyncio, json, time, urllib.request, sys
from playwright.async_api import async_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else "https://trid-clock-guard.onrender.com"

def mk(scenario, n):
    req = urllib.request.Request(BASE + "/api/files", data=json.dumps({"scenario": scenario, "play_until": n}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())["id"]

async def main():
    urllib.request.urlopen(BASE + "/api/health", timeout=90).read()
    fid = mk("maya", 11)
    pid = mk("priya", 11)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1280, "height": 720}, record_video_dir="video-raw",
                                  record_video_size={"width": 1280, "height": 720})
        t_ctx = time.monotonic()
        pg = await ctx.new_page()
        await pg.goto(f"{BASE}/?file={fid}&step=11")
        await pg.wait_for_selector("#items .it")
        await pg.wait_for_timeout(600)
        cap = lambda t: pg.evaluate("t => tcg.setCaption(t)", t)
        nxt = lambda: pg.evaluate("tcg.next()")
        scroll_mid = lambda y: pg.evaluate("y => document.querySelector('.mid').scrollTo({top: y, behavior: 'smooth'})", y)
        t0 = time.monotonic() - t_ctx
        await cap("5 of 6 Reg Z application items are in. Penny asks for the SSN.")
        await pg.wait_for_timeout(1200)
        await nxt()
        await cap("6th item lands. Application received. Loan Estimate due Wed Oct 14.")
        await pg.wait_for_timeout(2000)
        await nxt()
        await cap("Penny tries to charge the appraisal fee. Blocked.")
        await pg.wait_for_timeout(4500)
        await scroll_mid(300)
        await pg.evaluate("document.querySelectorAll('#items .it').forEach(e => e.classList.add('flash'))")
        await cap("Each item keeps its source message and time. The SSN is stored masked.")
        await pg.wait_for_timeout(5000)
        await scroll_mid(0)
        await pg.evaluate("document.querySelector('.days').classList.add('flash')")
        await cap("Due date uses the lender's open days. Saturday counts, Columbus Day does not.")
        await pg.wait_for_timeout(5000)
        await nxt()
        await cap("The credit report fee is the one allowed exception.")
        await pg.wait_for_timeout(3800)
        await nxt()
        await cap("Loan Estimate emailed Saturday. Mailbox rule: considered received Thu Oct 15.")
        await pg.wait_for_timeout(5000)
        await nxt()
        await cap("Appraisal fee tried again. Blocked: the LE is not received yet.")
        await pg.wait_for_timeout(4200)
        await nxt()
        await cap("A week later the borrower is silent. Still blocked. Silence is not intent.")
        await pg.wait_for_timeout(5000)
        await nxt()
        await cap("Borrower says to proceed after receiving the LE. Intent logged with its source.")
        await pg.wait_for_timeout(4800)
        await nxt()
        await cap("Now the appraisal fee is allowed, with the reason in the audit log.")
        await pg.wait_for_timeout(4200)
        await pg.evaluate("tcg.switchTenant('ridgeline')")
        await cap("Same file, lender closed Saturdays: the LE due date moves to Thu Oct 15.")
        await pg.wait_for_timeout(5500)
        await pg.goto(f"{BASE}/?file={pid}&step=11")
        await pg.wait_for_selector("#items .it")
        await cap("Another chat: 5 of 6 items, SSN promised tomorrow. No application yet, clock not started.")
        await pg.wait_for_timeout(5500)
        await cap("TRID Clock Guard. FastAPI + Postgres. Synthetic data. Not legal advice.")
        await pg.wait_for_timeout(3500)
        total = time.monotonic() - t_ctx
        path = await pg.video.path()
        await ctx.close(); await b.close()
        print(json.dumps({"t0": t0, "total": total, "video": path}))

asyncio.run(main())
