import { chromium } from 'playwright';

async function run() {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    const consoleLogs = [];
    const pageErrors = [];
    page.on('console', msg => {
        if (msg.type() === 'error') {
            consoleLogs.push(msg.text());
        }
    });
    page.on('pageerror', err => pageErrors.push(err.message));

    await page.goto('http://localhost:8000/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);

    // Get all buttons on the page
    const buttonData = await page.evaluate(() => {
        const btns = Array.from(document.querySelectorAll('button, .sidebar-item, [data-tab], .btn-tactical, .header-bell-btn, .header-user-profile'));
        return btns.map((b, idx) => ({
            index: idx,
            id: b.id || '',
            className: b.className || '',
            text: (b.innerText || b.textContent || '').trim().replace(/\s+/g, ' ').substring(0, 40),
            dataTab: b.getAttribute('data-tab') || '',
            title: b.title || '',
            tag: b.tagName,
            isVisible: b.offsetParent !== null,
            rect: b.getBoundingClientRect()
        }));
    });

    console.log(`Found ${buttonData.length} total buttons/interactive elements.`);
    console.log(JSON.stringify(buttonData, null, 2));

    await browser.close();
}

run().catch(console.error);
