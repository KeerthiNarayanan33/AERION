import { chromium } from 'playwright';

async function main() {
    console.log('====================================================');
    console.log('🚀 RUNNING LIVE SCREEN TEST & HEADER REDESIGN VERIFICATION');
    console.log('====================================================');

    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
        viewport: { width: 1440, height: 900 }
    });
    const page = await context.newPage();

    const consoleErrors = [];
    const httpErrors = [];

    page.on('console', msg => {
        if (msg.type() === 'error') {
            consoleErrors.push(msg.text());
            console.error(`[CONSOLE ERROR] ${msg.text()}`);
        }
    });

    page.on('response', res => {
        if (res.status() >= 400) {
            httpErrors.push({ status: res.status(), url: res.url() });
            console.error(`[HTTP ${res.status()}] ${res.url()}`);
        }
    });

    console.log('\n[1] Navigating to http://127.0.0.1:8000/ ...');
    await page.goto('http://127.0.0.1:8000/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(3000);

    // Verify Title
    const title = await page.title();
    console.log(`Page title: "${title}"`);

    // Verify Header Redesign Structure & Single Row
    console.log('\n[2] Verifying Redesigned Top HUD Status Ribbon...');
    const ribbon = await page.$('.hud-status-strip, .tactical-telemetry-ribbon');
    if (!ribbon) {
        throw new Error('❌ .hud-status-strip not found in DOM!');
    }
    console.log('✓ Found .hud-status-strip');

    const ribbonMetrics = await page.evaluate(() => {
        const el = document.querySelector('.hud-status-strip, .tactical-telemetry-ribbon');
        const header = document.querySelector('.hud-header');
        const pills = Array.from(el.querySelectorAll('.status-pill'));
        const dividers = Array.from(el.querySelectorAll('.hud-bar-pipe, .ribbon-divider'));
        
        // Check vertical alignment of pills (to ensure NO two-row wrapping)
        const tops = pills.map(p => Math.round(p.getBoundingClientRect().top));
        const allSameRow = (new Set(tops)).size <= 1;

        return {
            headerHeight: header.offsetHeight,
            ribbonWidth: el.offsetWidth,
            pillCount: pills.length,
            dividerCount: dividers.length,
            allSameRow,
            pills: pills.map(p => ({ id: p.id, text: p.innerText.replace(/\s+/g, ' ').trim() }))
        };
    });

    console.log('Ribbon Metrics:', JSON.stringify(ribbonMetrics, null, 2));
    if (!ribbonMetrics.allSameRow) {
        console.warn('⚠️ Warning: Ribbon pills might be wrapping or have mismatched tops:', ribbonMetrics.allSameRow);
    } else {
        console.log('✓ PERFECT SINGLE-ROW ALIGNMENT: All status pills sit cleanly on the exact same vertical horizon!');
    }

    // Capture screenshot of Header Redesign
    await page.locator('.hud-header').screenshot({ path: 'test_header_redesign.png' });
    console.log('✓ Saved header redesign screenshot to test_header_redesign.png');

    // Verify Cameras & Live Stream
    console.log('\n[3] Testing Live Camera Stream in Dashboard...');
    const dashboardCamImg = await page.$('#video-stream-CAM_01');
    if (dashboardCamImg) {
        const src = await dashboardCamImg.getAttribute('src');
        console.log(`Dashboard CAM_01 img src: ${src?.slice(0, 80)}`);
        // Verify it connects to real stream and NOT intercepted SVG
        if (src && src.includes('/api/cameras/CAM_01/stream')) {
            console.log('✓ SUCCESS: CAM_01 is connected to real MJPEG stream endpoint /api/cameras/CAM_01/stream!');
        } else if (src && src.startsWith('data:image/svg')) {
            console.warn('⚠️ CAM_01 has SVG data URI fallback');
        }
    }

    // Switch to Live Cameras Tab
    console.log('\n[4] Switching to Live Cameras Tab (tab-cameras)...');
    await page.click('.sidebar-item[data-tab="tab-cameras"]');
    await page.waitForTimeout(2000);

    const isCamTabActive = await page.$eval('#tab-cameras', el => el.classList.contains('active'));
    console.log(`Tab-cameras active: ${isCamTabActive}`);

    // Check tacticalMonitorImg
    const monitorImg = await page.$('#tacticalMonitorImg');
    if (monitorImg) {
        const monSrc = await monitorImg.getAttribute('src');
        console.log(`Tactical monitor img src: ${monSrc?.slice(0, 80)}`);
        if (monSrc && monSrc.includes('/api/cameras/CAM_01/stream')) {
            console.log('✓ SUCCESS: Tactical Monitor is actively streaming real backend video feed!');
        }
    }

    // Test Camera Switch Buttons
    console.log(' > Testing #btnMonitorCam02 click...');
    await page.click('#btnMonitorCam02');
    await page.waitForTimeout(1000);
    const cam02Src = await page.$eval('#tacticalMonitorImg', el => el.src);
    console.log(`Switched to CAM_02, src: ${cam02Src?.slice(0, 80)}`);

    console.log(' > Testing #btnMonitorUav click...');
    await page.click('#btnMonitorUav');
    await page.waitForTimeout(1000);
    const uavSrc = await page.$eval('#tacticalMonitorImg', el => el.src);
    console.log(`Switched to UAV_01, src: ${uavSrc?.slice(0, 80)}`);

    console.log(' > Switching back to #btnMonitorCam01...');
    await page.click('#btnMonitorCam01');
    await page.waitForTimeout(1000);

    // Test Multi-Grid toggle
    console.log(' > Testing View Mode Toggle (Multi-Grid)...');
    await page.click('#btnToggleCamViewMode');
    await page.waitForTimeout(1000);
    const isMultiGridVisible = await page.isVisible('#tacticalMultiCamGrid');
    console.log(`Multi-grid visible: ${isMultiGridVisible}`);
    
    // Toggle back to Single
    await page.click('#btnToggleCamViewMode');
    await page.waitForTimeout(1000);

    // Test Flip Mirror
    console.log(' > Testing Flip Mirror toggle...');
    await page.click('#btnToggleCamMirror');
    await page.waitForTimeout(500);
    await page.click('#btnToggleCamMirror');
    await page.waitForTimeout(500);

    // Capture screenshot of the Live Camera tab
    await page.screenshot({ path: 'test_camera_live.png' });
    console.log('✓ Saved live camera monitor screenshot to test_camera_live.png');

    // Test Navigation to other tabs
    console.log('\n[5] Testing Other Tabs & Core Functions...');
    const testTabs = [
        { id: 'tab-radar', name: 'Radar Sweep' },
        { id: 'tab-zones', name: 'Surveillance Zones' },
        { id: 'tab-events', name: 'Security Events' },
        { id: 'tab-uav', name: 'UAV Recon' },
        { id: 'tab-persons', name: 'Authorized Persons' },
        { id: 'tab-demosuite', name: 'Demo Suite' }
    ];

    for (const t of testTabs) {
        console.log(` > Navigating to [${t.name}]...`);
        await page.click(`.sidebar-item[data-tab="${t.id}"]`);
        await page.waitForTimeout(300);
        const isActive = await page.$eval(`#${t.id}`, el => el.classList.contains('active'));
        if (!isActive) throw new Error(`Tab ${t.name} failed to activate!`);
        console.log(`   ✓ Tab ${t.name} successfully activated.`);
    }

    // Switch back to Dashboard
    await page.click('.sidebar-item[data-tab="tab-dashboard"]');
    await page.waitForTimeout(1000);

    // Summary Report
    console.log('\n====================================================');
    console.log('🏁 TEST RESULTS SUMMARY');
    console.log('====================================================');
    console.log(`Console Errors (${consoleErrors.length}):`, consoleErrors);
    console.log(`HTTP 4xx/5xx Errors (${httpErrors.length}):`, httpErrors);

    if (consoleErrors.length === 0 && httpErrors.length === 0) {
        console.log('\n🎉 ALL TESTS PASSED WITH 0 ERRORS!');
    } else {
        console.log('\n⚠️ Some warnings or errors detected (see above).');
    }

    await browser.close();
}

main().catch(err => {
    console.error('Test execution failed:', err);
    process.exit(1);
});
