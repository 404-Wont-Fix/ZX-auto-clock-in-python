from playwright.sync_api import sync_playwright
import sys

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    page.goto('http://localhost:8000/admin')
    page.wait_for_timeout(2000)
    page.screenshot(path='C:/Users/Tian/.codex/visualizations/2026/08/01/019fbcee-6504-7852-bee4-59262fdab4ea/login_page.png', full_page=True)
    browser.close()
    print('screenshot saved')
