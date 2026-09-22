import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function login(page: Page, viewer = false) {
  await page.goto("/");
  await page
    .getByLabel("Email address")
    .fill(viewer ? "viewer@stratum.local" : "demo@stratum.local");
  await page.getByLabel("Password", { exact: true }).fill("stratum-demo-password");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(page.getByRole("heading", { name: "Reliability overview." })).toBeVisible();
}

test("operator completes the signal-to-resolution workflow", async ({ page }) => {
  await login(page);
  const title = `E2E checkout regression ${Date.now()}`;
  await page.getByRole("button", { name: "Send signal", exact: true }).click();
  await page.getByLabel("Service", { exact: true }).selectOption({ label: "Checkout API" });
  await page.getByLabel("Incident title").fill(title);
  await page.getByLabel("Correlation fingerprint").fill(`e2e.${Date.now()}`);
  await page.getByLabel("Deployment reference (optional)").fill("e2e-v1");
  await page.getByRole("dialog").getByRole("button", { name: "Send signal", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: title })).toBeVisible();
  await expect(
    dialog.getByRole("heading", { name: "Fast error-budget burn detected." }),
  ).toBeVisible({
    timeout: 25000,
  });
  await dialog.getByText("Inspect the latest deployment", { exact: true }).click();
  await dialog
    .getByLabel("Decision rationale")
    .first()
    .fill("Deployment timing matches the first error burst.");
  await dialog.getByRole("button", { name: "Approve investigation" }).first().click();
  await expect(
    dialog.getByText("Approved: Inspect the latest deployment", { exact: true }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Acknowledge incident" }).click();
  await expect(dialog.getByRole("button", { name: "Begin mitigation" })).toBeVisible();
  await dialog.getByRole("button", { name: "Begin mitigation" }).click();
  await dialog
    .getByLabel("Response note")
    .fill("Verified baseline error rates after reviewing the affected deployment.");
  await dialog.getByRole("button", { name: "Resolve incident" }).click();
  await expect(dialog.getByText("resolved", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Close dialog" }).click();
  await page.getByRole("button", { name: "Activity log" }).click();
  await expect(
    page
      .getByText("Verified baseline error rates after reviewing the affected deployment.")
      .first(),
  ).toBeVisible();
});

test("administrator registers a service and duplicate slug is handled", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "Service catalog" }).click();
  await page.getByRole("button", { name: "Register service", exact: true }).click();
  const name = `Inventory ${Date.now()}`;
  await page.getByLabel("Service name").fill(name);
  const slug = `inventory-${Date.now()}`;
  await page.getByLabel("Unique slug").fill(slug);
  await page.getByLabel("Owning team").fill("Fulfillment");
  await page.getByLabel("Description").fill("Tracks available stock and reservation consistency.");
  await page.getByLabel("Dependencies (comma separated)").fill("postgres, event-pipeline");
  await page.getByRole("dialog").getByRole("button", { name: "Register service" }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await page.getByRole("button", { name: "Register service", exact: true }).click();
  await page.getByLabel("Service name").fill(name);
  await page.getByLabel("Unique slug").fill(slug);
  await page.getByLabel("Owning team").fill("Fulfillment");
  await page.getByRole("dialog").getByRole("button", { name: "Register service" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Service slug already exists" }),
  ).toBeVisible();
});

test("viewer has a read-only console and session uses an HttpOnly cookie", async ({
  page,
  context,
}) => {
  await login(page, true);
  await expect(page.getByRole("button", { name: "Send signal" })).toHaveCount(0);
  await page.getByRole("button", { name: "Service catalog" }).click();
  await expect(page.getByRole("button", { name: "Register service" })).toHaveCount(0);
  const cookie = (await context.cookies()).find((c) => c.name === "stratum_session");
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe("Strict");
  expect(await page.evaluate(() => document.cookie)).not.toContain("stratum_session");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Welcome to Stratum" })).toBeVisible();
});

test("dashboard, drawer and mobile layout meet automated accessibility checks", async ({
  page,
}) => {
  await login(page);
  await expect(page.getByRole("heading", { name: "Incident pulse" })).toBeVisible();
  const desktop = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(desktop.violations).toEqual([]);
  await page.getByRole("button", { name: "Incidents", exact: true }).click();
  await page
    .getByRole("button", { name: "Open Elevated 5xx errors on checkout", exact: true })
    .click();
  await expect(
    page.getByRole("dialog").getByRole("heading", { name: "Evidence-based triage" }),
  ).toBeVisible();
  const drawer = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(drawer.violations).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  const mobile = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(mobile.violations).toEqual([]);
});

test("BFF rejects cross-origin state changes and private internal paths", async ({ request }) => {
  const response = await request.post("/api/v1/auth/login", {
    headers: { Origin: "https://evil.example" },
    data: { email: "demo@stratum.local", password: "stratum-demo-password" },
  });
  expect(response.status()).toBe(403);
  expect((await request.get("/api/v1/metrics")).status()).toBe(404);
});
