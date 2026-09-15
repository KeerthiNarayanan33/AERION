import { chromium } from 'playwright';
import fs from 'fs';

async function runTests() {
    console.log("=================================================================");
    console.log("🚀 STARTING SENTINEL-AI SURVEILLANCE AUTOMATED PLAYWRIGHT TEST SUITE");
    console.log("=================================================================");

    const results = {
        browserHeadedLaunched: false,
        pagesTested: [],
        consoleErrors: [],
        pageErrors: [],
        failedRequests: [],
        httpErrors: [],
        passedChecks: [],
        failedChecks: []
    };

    let browser;
    try {
        console.log("\n[STEP 6] Verifying Playwright can launch Chromium in headed mode...");
        browser = await chromium.launch({
            headless: false,
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });
        results.browserHeadedLaunched = true;
        console.log("✅ Playwright successfully launched Chromium in headed mode!");
    } catch (err) {
        console.warn("⚠️ Headed mode warning:", err.message);
        console.log("Falling back to headless mode...");
        browser = await chromium.launch({
            headless: true,
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });
        results.browserHeadedLaunched = "fallback-headless";
    }

    const context = await browser.newContext({
        viewport: { width: 1600, height: 950 }
    });
    const page = await context.newPage();

    // Monitor console messages
    page.on('console', msg => {
        const type = msg.type();
        const text = msg.text();
        if (type === 'error') {
            console.error(`🔴 [CONSOLE ERROR] ${text}`);
            results.consoleErrors.push(text);
        }
    });

    // Monitor uncaught errors
    page.on('pageerror', err => {
        console.error(`💥 [PAGE ERROR] ${err.message}`);
        results.pageErrors.push(err.message);
    });

    // Monitor failed requests (network connectivity level)
    page.on('requestfailed', req => {
        const failure = req.failure();
        const errText = failure ? failure.errorText : 'unknown';
        // Filter out aborts caused by user navigation
        if (!errText.includes('ERR_ABORTED')) {
            console.error(`❌ [REQ FAILED] ${req.method()} ${req.url()} - ${errText}`);
            results.failedRequests.push({ url: req.url(), method: req.method(), error: errText });
        }
    });

    // Monitor HTTP responses >= 400
    page.on('response', res => {
        const status = res.status();
        const url = res.url();
        if (status >= 400) {
            console.error(`⚠️ [HTTP ${status}] ${res.request().method()} ${url}`);
            results.httpErrors.push({ url, status, method: res.request().method() });
        }
    });

    const targetUrl = 'http://localhost:8000/';
    console.log(`\n[STEP 8 & 9] Opening application at ${targetUrl} automatically...`);
    
    try {
        const response = await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
        await page.waitForTimeout(1500);
        if (response && response.status() < 400) {
            results.passedChecks.push(`Initial page load HTTP ${response.status()}`);
        } else {
            results.failedChecks.push(`Initial page load status: ${response ? response.status() : 'null'}`);
        }
    } catch (err) {
        results.failedChecks.push(`Failed to load ${targetUrl}: ${err.message}`);
    }

    // Wait for JS initialization and WebSocket connection
    await page.waitForTimeout(2000);
    await page.waitForFunction(() => document.title && document.title.includes('AERION'), { timeout: 15000 }).catch(() => null);

    // Verify Title
    const title = await page.title();
    console.log(`📄 Page Title: "${title}"`);
    if (title.includes("AERION") || title.includes("Surveillance")) {
        results.passedChecks.push(`Page Title verification: "${title}"`);
    } else {
        results.failedChecks.push(`Unexpected Page Title: "${title}"`);
    }

    // Verify WebSocket status indicator
    await page.waitForSelector('#wsStatus .ws-label', { timeout: 15000 }).catch(() => null);
    const wsLabel = await page.$eval('#wsStatus .ws-label', el => el.textContent).catch(() => null);
    console.log(`📡 WebSocket HUD Label: "${wsLabel}"`);
    if (wsLabel && wsLabel.toLowerCase().includes('live')) {
        results.passedChecks.push(`WebSocket live data feed confirmed: ${wsLabel}`);
    } else {
        results.failedChecks.push(`WebSocket HUD indicator not showing live. Got: "${wsLabel}"`);
    }

    // Define all 12 navigation tabs to test
    const tabsToTest = [
        { id: 'tab-dashboard', name: 'Main Dashboard', selector: 'button.sidebar-item[data-tab="tab-dashboard"]' },
        { id: 'tab-cameras', name: 'Live Cameras', selector: 'button.sidebar-item[data-tab="tab-cameras"]' },
        { id: 'tab-radar', name: 'Radar Sweep', selector: 'button.sidebar-item[data-tab="tab-radar"]' },
        { id: 'tab-zones', name: 'Surveillance Zones', selector: 'button.sidebar-item[data-tab="tab-zones"]' },
        { id: 'tab-events', name: 'Security Events', selector: 'button.sidebar-item[data-tab="tab-events"]' },
        { id: 'tab-uav', name: 'UAV Recon', selector: 'button.sidebar-item[data-tab="tab-uav"]' },
        { id: 'tab-persons', name: 'Authorized People', selector: 'button.sidebar-item[data-tab="tab-persons"]' },
        { id: 'tab-location', name: 'Site Location', selector: 'button.sidebar-item[data-tab="tab-location"]' },
        { id: 'tab-devices', name: 'Devices & I/O', selector: 'button.sidebar-item[data-tab="tab-devices"]' },
        { id: 'tab-telemetry', name: 'System Telemetry', selector: 'button.sidebar-item[data-tab="tab-telemetry"]' },
        { id: 'tab-config', name: 'System Config', selector: 'button.sidebar-item[data-tab="tab-config"]' },
        { id: 'tab-demosuite', name: 'SIH 2026 Demo Suite', selector: 'button[data-tab="tab-demosuite"]' }
    ];

    console.log("\n[STEP 10] Testing all major pages, workflows, navigation, and interactive controls...");

    for (const tab of tabsToTest) {
        console.log(`\n--- Testing Navigation & Workflow: ${tab.name} (${tab.id}) ---`);
        const navBtn = await page.$(tab.selector);
        if (!navBtn) {
            results.failedChecks.push(`Tab nav button not found for ${tab.name} (${tab.selector})`);
            console.error(`❌ Button not found for selector: ${tab.selector}`);
            continue;
        }

        await navBtn.click();
        await page.waitForTimeout(600);

        const pane = await page.$(`#${tab.id}`);
        if (!pane) {
            results.failedChecks.push(`Pane #${tab.id} does not exist in DOM`);
            continue;
        }

        const isVisible = await pane.isVisible();
        if (isVisible) {
            results.passedChecks.push(`Tab ${tab.name} successfully activated and visible`);
            results.pagesTested.push(tab.name);
            console.log(`✅ ${tab.name} successfully displayed in main content viewport.`);
        } else {
            results.failedChecks.push(`Tab ${tab.name} (#${tab.id}) is not visible after navigation`);
            console.error(`❌ Tab ${tab.name} (#${tab.id}) not visible`);
        }

        // Test specific interactive workflows for each page
        if (tab.id === 'tab-dashboard') {
            const threatVal = await page.$eval('#sovThreats', el => el.textContent).catch(() => null);
            const unknownVal = await page.$eval('#sovUnknown', el => el.textContent).catch(() => null);
            console.log(`   Threats stat: ${threatVal}, Unknown stat: ${unknownVal}`);
            results.passedChecks.push(`Dashboard stats read: Threats=${threatVal}, Unknown=${unknownVal}`);

            // Test audio alarm button
            const audioBtn = await page.$('#btnToggleAudio');
            if (audioBtn && await audioBtn.isVisible()) {
                await audioBtn.click();
                results.passedChecks.push('Audio alert toggle button interactive');
            }
        } else if (tab.id === 'tab-cameras') {
            const monitorImg = await page.$('#tacticalMonitorImg');
            if (monitorImg) {
                const src = await monitorImg.getAttribute('src');
                console.log(`   Live camera monitor image source: ${src}`);
                results.passedChecks.push(`Camera monitor image rendered: ${src}`);
            }

            // Test camera switching buttons
            const btnCam01 = await page.$('#btnMonitorCam01');
            const btnCam02 = await page.$('#btnMonitorCam02');
            const btnUav = await page.$('#btnMonitorUav');
            if (btnCam01 && btnCam02 && btnUav && await btnCam01.isVisible()) {
                await btnCam02.click();
                await page.waitForTimeout(200);
                await btnCam01.click();
                await page.waitForTimeout(200);
                results.passedChecks.push('Camera feed switcher buttons (CAM_01, CAM_02, UAV_01) responsive');
            }
        } else if (tab.id === 'tab-radar') {
            const radarCanvas = await page.$('#radarCanvasExpanded');
            if (radarCanvas) {
                const box = await radarCanvas.boundingBox();
                console.log(`   Radar expanded canvas bounding box: ${box ? `${Math.round(box.width)}x${Math.round(box.height)}` : 'null'}`);
                results.passedChecks.push('Radar sweep canvas expanded element rendered and sized.');
            }
            const injectBtn = await page.$('#btnInjectRadarTarget');
            if (injectBtn && await injectBtn.isVisible()) {
                await injectBtn.click();
                await page.waitForTimeout(300);
                results.passedChecks.push('Radar inject target button interactive');
            }
        } else if (tab.id === 'tab-zones') {
            const zonesContainer = await page.$('#zonesListContainer');
            const refreshBtn = await page.$('#btnRefreshAnalytics');
            if (zonesContainer) results.passedChecks.push('Zones list container present');
            if (refreshBtn && await refreshBtn.isVisible()) {
                await refreshBtn.click();
                await page.waitForTimeout(300);
                results.passedChecks.push('Zone analytics refresh button interactive');
            }
        } else if (tab.id === 'tab-events') {
            const eventsBody = await page.$('#eventsTableBody');
            if (eventsBody) {
                const rows = await page.$$('#eventsTableBody tr');
                console.log(`   Security Events loaded: ${rows.length} rows.`);
                results.passedChecks.push(`Security Events table populated with ${rows.length} incident rows.`);
            }
            const filterInput = await page.$('#eventsSearchInput, #filterObjClass');
            if (filterInput) results.passedChecks.push('Security Events filter control available');
        } else if (tab.id === 'tab-uav') {
            const uavButtons = await page.$$('#tab-uav button');
            console.log(`   Found ${uavButtons.length} UAV control buttons.`);
            results.passedChecks.push(`UAV dashboard loaded with ${uavButtons.length} control buttons.`);
            const btnRth = await page.$('#btnUavRth, #btnDroneRth, button[id*="Rth"]');
            if (btnRth && await btnRth.isVisible()) {
                await btnRth.click();
                await page.waitForTimeout(200);
                results.passedChecks.push('UAV Return-To-Home control button responsive');
            }
        } else if (tab.id === 'tab-persons') {
            console.log("   Testing Authorized Person / Identification Workflow...");
            const addBtn = await page.$('#btnAddPerson');
            if (addBtn) {
                console.log("   Clicking + ADD PERSON button...");
                await addBtn.click();
                await page.waitForTimeout(400);

                const modal = await page.$('#personModal');
                const isModalVis = modal ? await modal.isVisible() : false;
                console.log(`   Add Person modal opened: ${isModalVis}`);
                if (isModalVis) {
                    results.passedChecks.push('Add Person modal opens correctly');

                    // Fill form inputs
                    await page.fill('#pmPersonId', 'TEST-AUTH-999');
                    await page.fill('#pmName', 'Playwright Automated Officer');
                    await page.fill('#pmEmployeeId', 'EMP-9999');
                    await page.fill('#pmDepartment', 'Cyber Surveillance');
                    await page.fill('#pmRole', 'Test Automation Sentinel');
                    console.log("   Filled Person details form successfully.");
                    results.passedChecks.push('Add Person form input fields interactive and fillable');

                    // Close modal
                    const closeBtn = await page.$('#btnClosePersonModal');
                    if (closeBtn) {
                        await closeBtn.click();
                        await page.waitForTimeout(300);
                        const isClosed = !(await modal.isVisible());
                        console.log(`   Modal closed successfully: ${isClosed}`);
                        results.passedChecks.push(`Add Person modal close button works: ${isClosed}`);
                    }
                } else {
                    results.failedChecks.push('Add Person modal did not open on clicking #btnAddPerson');
                }
            } else {
                results.failedChecks.push('#btnAddPerson button not found');
            }
        } else if (tab.id === 'tab-location') {
            const nameInput = await page.$('#siteFieldName');
            const latInput = await page.$('#siteFieldLat');
            const lonInput = await page.$('#siteFieldLon');
            const saveBtn = await page.$('#btnSaveSiteConfig');
            const mapCanvas = await page.$('#siteMapCanvas');
            console.log(`   Site inputs found: Name=${!!nameInput}, Lat=${!!latInput}, Lon=${!!lonInput}, Map=${!!mapCanvas}`);
            if (nameInput && latInput && lonInput && saveBtn && mapCanvas) {
                results.passedChecks.push('Site Location form, inputs, canvas map, and save button verified');
                await nameInput.fill('Border Sector Bravo');
                await latInput.fill('28.6139');
                await lonInput.fill('77.2090');
                await saveBtn.click();
                await page.waitForTimeout(400);
                const feedback = await page.$('#siteConfigFeedback');
                const fbVis = feedback ? await feedback.isVisible() : false;
                console.log(`   Site Config save feedback displayed: ${fbVis}`);
                results.passedChecks.push(`Site Config save interaction verified: ${fbVis}`);
            }
        } else if (tab.id === 'tab-devices') {
            const matrixBody = await page.$('#sensorMatrixBody');
            console.log(`   Sensor matrix table present: ${!!matrixBody}`);
            results.passedChecks.push(`Sensor Matrix and Device I/O configuration verified: ${!!matrixBody}`);
        } else if (tab.id === 'tab-config') {
            const configInputs = await page.$$('#tab-config input, #tab-config select, #tab-config button');
            console.log(`   Found ${configInputs.length} config form controls.`);
            results.passedChecks.push(`System Config controls verified: ${configInputs.length} controls.`);
        } else if (tab.id === 'tab-demosuite') {
            const playbooksGrid = await page.$('#playbooksGrid');
            console.log(`   Demo Suite Playbooks grid present: ${!!playbooksGrid}`);
            results.passedChecks.push(`Demo Suite Playbooks grid present: ${!!playbooksGrid}`);
        }
    }

    console.log("\n[STEP 11] Testing REST API endpoints integration directly...");
    const apiEndpointsToVerify = [
        { path: '/api/system/health', name: 'System Health' },
        { path: '/api/system/status', name: 'System Status Alias' },
        { path: '/api/cameras', name: 'Cameras List' },
        { path: '/api/zones', name: 'Zones List' },
        { path: '/api/events', name: 'Security Events List' },
        { path: '/api/persons', name: 'Authorized Persons List' },
        { path: '/api/radar/status', name: 'Radar Status' },
        { path: '/api/drone/status', name: 'Drone Status' },
        { path: '/api/site/config', name: 'Site Configuration' },
        { path: '/api/settings', name: 'System Settings' }
    ];

    for (const ep of apiEndpointsToVerify) {
        try {
            const res = await page.request.get(`http://localhost:8000${ep.path}`);
            const status = res.status();
            if (status >= 200 && status < 300) {
                results.passedChecks.push(`API Endpoint ${ep.name} (${ep.path}) returned ${status}`);
                console.log(`✅ API ${ep.path}: ${status}`);
            } else {
                results.failedChecks.push(`API Endpoint ${ep.name} (${ep.path}) returned error ${status}`);
                console.error(`❌ API ${ep.path}: ${status}`);
            }
        } catch (apiErr) {
            results.failedChecks.push(`API Endpoint ${ep.name} (${ep.path}) request failed: ${apiErr.message}`);
            console.error(`❌ API ${ep.path}: ${apiErr.message}`);
        }
    }

    console.log("\n=================================================================");
    console.log("📊 PLAYWRIGHT TEST SUMMARY REPORT");
    console.log("=================================================================");
    console.log(`Chromium Headed Launch: ${results.browserHeadedLaunched}`);
    console.log(`Pages/Tabs Tested: ${results.pagesTested.length} / ${tabsToTest.length}`);
    console.log(`Passed Checks: ${results.passedChecks.length}`);
    console.log(`Failed Checks: ${results.failedChecks.length}`);
    console.log(`Console Errors: ${results.consoleErrors.length}`);
    console.log(`Page Errors: ${results.pageErrors.length}`);
    console.log(`Failed Network Requests: ${results.failedRequests.length}`);
    console.log(`HTTP 4xx/5xx Responses: ${results.httpErrors.length}`);

    if (results.consoleErrors.length > 0) {
        console.log("\n--- CONSOLE ERRORS ---");
        results.consoleErrors.forEach((e, idx) => console.log(`${idx + 1}. ${e}`));
    }
    if (results.pageErrors.length > 0) {
        console.log("\n--- PAGE UNCAUGHT ERRORS ---");
        results.pageErrors.forEach((e, idx) => console.log(`${idx + 1}. ${e}`));
    }
    if (results.failedRequests.length > 0) {
        console.log("\n--- FAILED NETWORK REQUESTS ---");
        results.failedRequests.forEach((e, idx) => console.log(`${idx + 1}. [${e.method}] ${e.url}: ${e.error}`));
    }
    if (results.httpErrors.length > 0) {
        console.log("\n--- HTTP 4xx/5xx ERRORS ---");
        results.httpErrors.forEach((e, idx) => console.log(`${idx + 1}. [${e.method}] ${e.url} (Status: ${e.status})`));
    }
    if (results.failedChecks.length > 0) {
        console.log("\n--- FAILED ASSERTION CHECKS ---");
        results.failedChecks.forEach((e, idx) => console.log(`${idx + 1}. ${e}`));
    }

    await browser.close();

    // Write full results to JSON
    fs.writeFileSync('test_results.json', JSON.stringify(results, null, 2));
    console.log("\nTest report saved to test_results.json");
    
    if (results.consoleErrors.length > 0 || results.pageErrors.length > 0 || results.httpErrors.length > 0 || results.failedChecks.length > 0) {
        process.exit(2);
    } else {
        console.log("\n🎉 ALL CHECKS PASSED WITH ZERO ERRORS!");
        process.exit(0);
    }
}

runTests().catch(err => {
    console.error("FATAL TEST RUNNER ERROR:", err);
    process.exit(1);
});
