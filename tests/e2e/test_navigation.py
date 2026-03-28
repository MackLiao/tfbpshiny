"""E2E smoke test: navigation between pages loads without error."""

from playwright.sync_api import Page, expect
from shiny.pytest import create_app_fixture

app = create_app_fixture("../../tfbpshiny/app.py")


def test_home_loads(page: Page, app):
    page.goto(app.url)
    expect(page.locator(".nav-bar")).to_be_visible()


def test_navigate_to_selection(page: Page, app):
    page.goto(app.url)
    page.locator("#selection").click()
    expect(page.locator("#selection-sidebar")).to_be_visible()


def test_navigate_to_binding(page: Page, app):
    page.goto(app.url)
    page.locator("#binding").click()
    expect(page.locator(".context-sidebar")).to_be_visible()
