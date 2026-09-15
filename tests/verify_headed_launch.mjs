import { chromium } from 'playwright';

async function main() {
    console.log("Attempting to launch Chromium in headed mode...");
    const browser = await chromium.launch({
        headless: false,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    console.log("Chromium launched successfully in headed mode!");
    const version = browser.version();
    console.log("Browser version:", version);
    const page = await browser.newPage();
    await page.goto("http://localhost:8000/");
    const title = await page.title();
    console.log("Successfully connected to http://localhost:8000/! Page title:", title);
    await browser.close();
    console.log("Chromium closed successfully.");
}

main().catch(err => {
    console.error("Launch error:", err);
    process.exit(1);
});
