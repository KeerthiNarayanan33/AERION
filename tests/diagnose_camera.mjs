import { chromium } from 'playwright';

async function diagnose() {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    const consoleMessages = [];
    const errors = [];
    const failedRequests = [];

    page.on('console', msg => {
        consoleMessages.push(`[${msg.type()}] ${msg.text()}`);
        if (msg.type() === 'error') {
            errors.push(msg.text());
        }
    });

    page.on('pageerror', err => {
        errors.push(`PageError: ${err.message}`);
    });

    page.on('response', res => {
        if (res.status() >= 400) {
            failedRequests.push({ status: res.status(), url: res.url() });
        }
    });

    console.log("Navigating to http://127.0.0.1:8000/...");
    await page.goto('http://127.0.0.1:8000/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(3000);

    console.log("--- FAILED REQUESTS ---");
    console.log(JSON.stringify(failedRequests, null, 2));

    console.log("--- CONSOLE ERRORS ---");
    console.log(JSON.stringify(errors, null, 2));

    // Check camera elements in Dashboard and Live Cameras tab
    const dashCamImg = await page.evaluate(() => {
        const imgs = Array.from(document.querySelectorAll('img')).map(i => ({ id: i.id, src: i.src, naturalWidth: i.naturalWidth, naturalHeight: i.naturalHeight, complete: i.complete, style: i.getAttribute('style'), class: i.className }));
        const videos = Array.from(document.querySelectorAll('video')).map(v => ({ id: v.id, src: v.src, paused: v.paused, readyState: v.readyState }));
        return { imgs, videos };
    });
    console.log("--- DASHBOARD MEDIA ELEMENTS ---");
    console.log(JSON.stringify(dashCamImg, null, 2));

    // Now switch to Live Cameras tab
    console.log("Switching to tab-cameras...");
    await page.click('.sidebar-item[data-tab="tab-cameras"]');
    await page.waitForTimeout(2000);

    const camTabMedia = await page.evaluate(() => {
        const monitor = document.getElementById('tacticalSingleMonitorWrapper');
        const monitorContent = monitor ? monitor.innerHTML : 'NOT FOUND';
        const grid = document.getElementById('cameraGridContainer');
        const gridContent = grid ? grid.innerHTML.slice(0, 300) : 'NOT FOUND';
        return { monitorContent, gridContent };
    });
    console.log("--- TAB CAMERAS MEDIA ---");
    console.log(JSON.stringify(camTabMedia, null, 2));

    await browser.close();
}

diagnose().catch(err => {
    console.error("Diagnostic failed:", err);
    process.exit(1);
});
