import { chromium } from 'playwright';

async function testAllButtons() {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    const errors = [];
    page.on('console', msg => {
        if (msg.type() === 'error') {
            errors.push(`Console error: ${msg.text()}`);
        }
    });
    page.on('pageerror', err => {
        errors.push(`Page error: ${err.message}`);
    });

    await page.goto('http://localhost:8000/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);

    const tabs = [
        'tab-dashboard',
        'tab-cameras',
        'tab-radar',
        'tab-zones',
        'tab-events',
        'tab-uav',
        'tab-persons',
        'tab-location',
        'tab-devices',
        'tab-telemetry',
        'tab-config',
        'tab-demosuite'
    ];

    console.log('--- Testing Navigation Tabs ---');
    for (const tabId of tabs) {
        const btn = await page.$(`.sidebar-item[data-tab="${tabId}"]`);
        if (btn) {
            console.log(`Clicking sidebar item for ${tabId}...`);
            await btn.click();
            await page.waitForTimeout(300);
            const pane = await page.$(`#${tabId}`);
            const isActive = await pane.evaluate(el => el.classList.contains('active'));
            console.log(`   ${tabId} active: ${isActive}`);
            if (!isActive) errors.push(`Tab ${tabId} did not become active`);
        } else {
            errors.push(`Sidebar item not found for ${tabId}`);
        }
    }

    console.log('\n--- Testing Header Buttons ---');
    const sihBtn = await page.$('#navTabDemoSuite');
    if (sihBtn) {
        await sihBtn.click();
        await page.waitForTimeout(300);
        const isDemoActive = await page.$eval('#tab-demosuite', el => el.classList.contains('active'));
        console.log(`navTabDemoSuite clicked -> tab-demosuite active: ${isDemoActive}`);
        if (!isDemoActive) errors.push('navTabDemoSuite did not activate tab-demosuite');
    }

    // Now test buttons on each tab
    for (const tabId of tabs) {
        console.log(`\n=== Testing Buttons on ${tabId} ===`);
        await page.click(`.sidebar-item[data-tab="${tabId}"]`);
        await page.waitForTimeout(400);

        const buttonsOnTab = await page.$$(`#${tabId} button`);
        console.log(`Found ${buttonsOnTab.length} buttons on ${tabId}`);

        for (let i = 0; i < buttonsOnTab.length; i++) {
            const b = buttonsOnTab[i];
            const isVis = await b.isVisible();
            const btnInfo = await b.evaluate(el => ({
                id: el.id,
                text: (el.innerText || '').trim().replace(/\s+/g, ' ').substring(0, 30),
                disabled: el.disabled
            }));

            if (isVis && !btnInfo.disabled) {
                // Avoid buttons that delete data or reset entire database unless safe
                if (btnInfo.id === 'btnResetDb' || btnInfo.id === 'btnClearAllData') {
                    console.log(`   [SKIP DESTRUCTIVE] #${btnInfo.id} ("${btnInfo.text}")`);
                    continue;
                }
                try {
                    console.log(`   Clicking #${btnInfo.id || `btn-${i}`} ("${btnInfo.text}")...`);
                    await b.click({ timeout: 2000 });
                    await page.waitForTimeout(200);
                } catch (clickErr) {
                    console.warn(`   Could not click #${btnInfo.id}: ${clickErr.message}`);
                    errors.push(`Failed to click #${btnInfo.id}: ${clickErr.message}`);
                }
            } else {
                // Not visible or disabled
            }
        }
    }

    console.log(`\nTotal errors encountered: ${errors.length}`);
    if (errors.length > 0) {
        console.log('Errors:');
        errors.forEach(e => console.log(' - ' + e));
    }

    await browser.close();
}

testAllButtons().catch(console.error);
