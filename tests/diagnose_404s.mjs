import { chromium } from 'playwright';

async function main() {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    page.on('response', res => {
        if (res.status() >= 400) {
            console.log(`[HTTP ${res.status()}] ${res.request().method()} ${res.url()}`);
        }
    });

    page.on('console', msg => {
        if (msg.type() === 'error') {
            console.log(`[CONSOLE ERROR] ${msg.text()}`);
        }
    });

    console.log("Loading http://localhost:8000/ ...");
    await page.goto('http://localhost:8000/', { waitUntil: 'networkidle' });
    console.log("Done loading initial page.");

    await browser.close();
}

main();
