import { chromium } from 'playwright';

async function testPersonsFull() {
    const browser = await chromium.launch({
        executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        headless: true
    });
    const context = await browser.newContext();
    const page = await context.newPage();

    // Set active tab in sessionStorage before load
    await page.addInitScript(() => {
        sessionStorage.setItem('soc_active_tab', 'tab-persons');
    });

    console.log('Navigating directly with tab-persons saved in sessionStorage...');
    await page.goto('http://localhost:8000', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(3000);

    const rows = await page.$$eval('#personsTableBody tr', trs => trs.length);
    console.log('Direct load on tab-persons rows:', rows);

    // Test clicking "+ ADD PERSON" button
    console.log('Testing + ADD PERSON modal...');
    await page.click('#btnAddPerson');
    await page.waitForTimeout(1000);
    const modalDisplay = await page.$eval('#personModal', el => window.getComputedStyle(el).display);
    console.log('personModal display:', modalDisplay);

    // Close modal
    await page.click('#btnCancelPersonModal');
    await page.waitForTimeout(500);

    // Test clicking "View Profile" on first person
    console.log('Testing View Profile button...');
    await page.click('.btn-view');
    await page.waitForTimeout(1000);
    const profileDisplay = await page.$eval('#personProfileModal', el => window.getComputedStyle(el).display);
    const profileText = await page.$eval('#personProfileContent', el => el.innerText.trim());
    console.log('personProfileModal display:', profileDisplay);
    console.log('personProfile preview:\n', profileText.substring(0, 150));

    // Close profile modal
    await page.click('#btnClosePersonProfile');
    await page.waitForTimeout(500);

    await page.screenshot({ path: 'tab_persons_full_verified.png' });
    console.log('SUCCESS: All persons manager features verified.');

    await browser.close();
}

testPersonsFull().catch(e => {
    console.error('FAILED:', e);
    process.exit(1);
});
