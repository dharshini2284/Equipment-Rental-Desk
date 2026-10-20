import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// Runs top to bottom against freshly seeded data (see playwright.config.ts); later
// scenarios rely on the state earlier ones leave behind.
test.describe.configure({ mode: "serial" });

const memberSelect = (page: Page) => page.locator(".member-picker select");

async function pickMember(page: Page, search: string, memberId: number) {
  await page.getByPlaceholder("Name or phone").fill(search);
  await expect(memberSelect(page).locator("option")).toHaveCount(2);
  await memberSelect(page).selectOption(String(memberId));
}

test("dashboard shows the desk's numbers", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.locator(".stat-card", { hasText: "Overdue" })).toContainText("2");
  await expect(page.locator(".severity-blocked")).toHaveCount(1);
});

test("items can be filtered by live status and searched", async ({ page }) => {
  await page.goto("/items");
  await expect(page.locator(".item-card")).toHaveCount(20);
  await page.locator(".filter-chip.filter-overdue").click();
  await expect(page.locator(".item-card")).toHaveCount(2);
  await page.locator(".filter-chip", { hasText: "All" }).click();
  await page.getByLabel("Search").fill("drill");
  await expect(page.locator(".item-card")).toHaveCount(2);
});

test("reserve, check out and return an item", async ({ page }) => {
  await page.goto("/items?q=Jigsaw");
  await page.locator(".item-card", { hasText: "Jigsaw" }).click();
  await expect(page.getByRole("button", { name: "Check out" })).toHaveCount(0);

  await pickMember(page, "Neha", 10);
  await page.getByRole("button", { name: "Reserve for 48 hours" }).click();
  await expect(page.getByText(/Reserved for Neha Deshpande/)).toBeVisible();

  await page.getByRole("button", { name: "Check out" }).click();
  await expect(page.locator(".hero-title .badge")).toHaveText("Checked out");

  await page.getByRole("button", { name: "Record return" }).click();
  await expect(page.getByText("Returned on time. No fee.")).toBeVisible();
  await expect(page.locator(".hero-title .badge")).toHaveText("Available");
});

test("a blocked member is explained and cannot be reserved for", async ({ page }) => {
  await page.goto("/items?q=Jigsaw");
  await page.locator(".item-card", { hasText: "Jigsaw" }).click();
  await pickMember(page, "Meera", 4);
  await expect(page.getByText(/exceed the ₹100 limit/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Reserve for 48 hours" })).toBeDisabled();
});

test("overpayment is refused, exact payment clears the block", async ({ page }) => {
  await page.goto("/members/4");
  await expect(page.getByText("Why can't Meera Iyer borrow?")).toBeVisible();
  await page.getByLabel("Amount (₹)").fill("120.01");
  await expect(page.getByText(/more than the ₹120 owed/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Record payment" })).toBeDisabled();
  await page.getByLabel("Amount (₹)").fill("120");
  await page.getByRole("button", { name: "Record payment" }).click();
  await expect(page.getByText(/Balance now ₹0/)).toBeVisible();
  await expect(page.getByText("Can reserve and borrow items.")).toBeVisible();
});

test("returning an item hands it to the first member on the waitlist", async ({ page }) => {
  await page.goto("/items?q=Hammer");
  await page.locator(".item-card", { hasText: "Hammer drill" }).click();
  const queue = page.locator(".queue-list li");
  await expect(queue).toHaveCount(2);
  await expect(queue.first()).toContainText("Farhan Qureshi");

  await page.getByRole("button", { name: "Record return" }).click();
  await expect(page.getByText(/Late fee of ₹\d+ added/)).toBeVisible();
  await expect(page.locator(".hero-title .badge")).toHaveText("Reserved");
  await expect(page.locator(".loan-card")).toContainText("Farhan Qureshi");
  await expect(queue).toHaveCount(1);
  await expect(queue.first()).toContainText("Neha Deshpande");

  await page.goto("/outbox?kind=waitlist_reserved");
  await expect(page.locator(".message").first()).toContainText("Farhan Qureshi");
  await expect(page.locator(".message").first()).toContainText("which you were waiting for");
});

test("overdue reminders are queued once per day", async ({ page }) => {
  await page.goto("/outbox");
  await page.getByRole("button", { name: "Send overdue reminders" }).click();
  await expect(page.getByText(/Queued 1 overdue reminder/)).toBeVisible();
  await page.getByRole("button", { name: "Send overdue reminders" }).click();
  await expect(page.getByText(/No reminders queued/)).toBeVisible();
});

test("a new member can be registered, edited and deleted", async ({ page }) => {
  await page.goto("/members");
  await page.getByRole("button", { name: "Register member" }).click();
  await page.getByLabel("Full name").fill("Test Person");
  await page.getByLabel("Phone").fill("+91 90000 12345");
  await page.getByRole("button", { name: "Register", exact: true }).click();
  await expect(page.getByText("Registered Test Person.")).toBeVisible();

  await page.getByRole("link", { name: /Test Person/ }).click();
  await page.getByText("Edit member details").click();
  await page.getByLabel("Full name").fill("Test Person Renamed");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("heading", { name: "Test Person Renamed" })).toBeVisible();

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: /Delete member/ }).click();
  await expect(page).toHaveURL(/\/members$/);
  await expect(page.getByText("Test Person Renamed")).toHaveCount(0);
});

test("the review clock moves every rule forward", async ({ page }) => {
  await page.goto("/overdue");
  const rows = page.locator("table tbody tr");
  await expect(rows.first()).toBeVisible();
  const before = await rows.count();
  await page.getByRole("button", { name: /set review clock/ }).click();
  await page.getByRole("button", { name: "+7 days" }).click();
  await expect(page.getByRole("button", { name: /Review clock:/ })).toBeVisible();
  await expect.poll(() => rows.count()).toBeGreaterThan(before);
  await page.getByRole("button", { name: "Back to real time" }).click();
  await expect(rows).toHaveCount(before);
});

test("pages fit a phone screen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of ["/", "/items", "/items/2", "/members/4", "/overdue", "/outbox"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(0);
  }
  await expect(page.locator(".tab-bar")).toBeVisible();
});

test("an unknown id shows an error instead of a blank page", async ({ page }) => {
  await page.goto("/items/99999");
  await expect(page.getByText("Item 99999 not found.")).toBeVisible();
});

// Last on purpose: under Playwright, Edge (PW_CHANNEL=msedge) can close the browser after a
// download, which would break any test that came after it.
test("member statement downloads as a PDF", async ({ page }) => {
  await page.goto("/members/4");
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: /Statement PDF/ }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe("statement-member-4.pdf");
  // Wait for the file to finish saving, then check it really is a PDF.
  const path = await download.path();
  expect(readFileSync(path).subarray(0, 4).toString()).toBe("%PDF");
});
