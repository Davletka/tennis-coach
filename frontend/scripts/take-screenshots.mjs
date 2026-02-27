import puppeteer from "puppeteer";
import { execSync, spawn } from "child_process";
import { mkdirSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOTS_DIR = path.join(__dirname, "..", "screenshots");
const PORT = 3000;
const BASE_URL = `http://localhost:${PORT}`;
const WAIT_MS = 1500; // settle time after nav
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

mkdirSync(SCREENSHOTS_DIR, { recursive: true });

// Helper to make a simple URL-navigation scenario
const nav = (name, description, url) => ({
  name,
  description,
  setup: async (page) => {
    await page.goto(`${BASE_URL}${url}`, { waitUntil: "networkidle2" });
    await sleep(WAIT_MS);
  },
});

// Tab states to capture by setting localStorage + clicking tabs
const SCENARIOS = [
  {
    name: "01-analyze-idle",
    description: "Analyze tab — idle (no file selected)",
    setup: async (page) => {
      await page.goto(BASE_URL, { waitUntil: "networkidle2" });
      await sleep(WAIT_MS);
    },
  },
  {
    name: "02-history-signed-out",
    description: "History tab — unauthenticated sign-in prompt",
    setup: async (page) => {
      await page.goto(BASE_URL, { waitUntil: "networkidle2" });
      await sleep(WAIT_MS);
      await page.evaluate(() => {
        localStorage.removeItem("courtcoach_jwt");
      });
      await page.reload({ waitUntil: "networkidle2" });
      await sleep(WAIT_MS);
      // Click History tab
      const tabs = await page.$$("header button");
      for (const tab of tabs) {
        const text = await tab.evaluate((el) => el.textContent?.trim());
        if (text === "History") {
          await tab.click();
          break;
        }
      }
      await sleep(WAIT_MS);
    },
  },
  {
    name: "03-compare-signed-out",
    description: "Compare tab — unauthenticated sign-in prompt",
    setup: async (page) => {
      await page.goto(BASE_URL, { waitUntil: "networkidle2" });
      await sleep(WAIT_MS);
      const tabs = await page.$$("header button");
      for (const tab of tabs) {
        const text = await tab.evaluate((el) => el.textContent?.trim());
        if (text === "Compare") {
          await tab.click();
          break;
        }
      }
      await sleep(WAIT_MS);
    },
  },
  {
    name: "04-progress-signed-out",
    description: "Progress tab — unauthenticated sign-in prompt",
    setup: async (page) => {
      await page.goto(BASE_URL, { waitUntil: "networkidle2" });
      await sleep(WAIT_MS);
      const tabs = await page.$$("header button");
      for (const tab of tabs) {
        const text = await tab.evaluate((el) => el.textContent?.trim());
        if (text === "Progress") {
          await tab.click();
          break;
        }
      }
      await sleep(WAIT_MS);
    },
  },
  // Learn tab — all sub-routes (IDs match learn-content.ts)
  nav("05-learn-sports", "Learn — sport selector", "/learn"),
  nav("06-learn-tennis-modules", "Learn — Tennis modules grid", "/learn/tennis"),
  nav("07-learn-tennis-forehand-variants", "Learn — Forehand grip variants", "/learn/tennis/forehand"),
  nav("08-learn-tennis-forehand-eastern-lessons", "Learn — Eastern grip lessons", "/learn/tennis/forehand/eastern"),
  nav("09-learn-tennis-forehand-eastern-flat", "Learn — Flat Forehand lesson", "/learn/tennis/forehand/eastern/flat-forehand"),
  nav("10-learn-tennis-backhand-variants", "Learn — Backhand variants", "/learn/tennis/backhand"),
  nav("11-learn-tennis-backhand-two-handed", "Learn — Two-handed backhand lessons", "/learn/tennis/backhand/two-handed"),
  nav("12-learn-tennis-serve-lessons", "Learn — Serve direct lessons", "/learn/tennis/serve"),
  nav("13-learn-tennis-serve-flat", "Learn — Flat Serve lesson", "/learn/tennis/serve/flat-serve"),
  nav("14-learn-gym-modules", "Learn — Gym modules grid", "/learn/gym"),
  nav("15-learn-gym-chest-variants", "Learn — Chest variants", "/learn/gym/chest"),
  nav("16-learn-gym-chest-barbell-lessons", "Learn — Barbell chest lessons", "/learn/gym/chest/barbell"),
  nav("17-learn-gym-chest-barbell-bench", "Learn — Bench Press lesson", "/learn/gym/chest/barbell/bench-press"),
  nav("18-learn-gym-plans-list", "Learn — Workout plans list", "/learn/gym/plans"),
  nav("19-learn-gym-plans-ppl", "Learn — PPL plan detail", "/learn/gym/plans/ppl"),
];

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "mobile", width: 390, height: 844 },
];

async function waitForServer(url, retries = 30, delay = 2000) {
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(url);
      if (res.ok || res.status === 404) return true;
    } catch {
      // not ready yet
    }
    if (i < retries - 1) {
      process.stdout.write(`  Waiting for server (${i + 1}/${retries})...\r`);
      await new Promise((r) => setTimeout(r, delay));
    }
  }
  throw new Error(`Server at ${url} did not become ready`);
}

async function isPortInUse(port) {
  try {
    await fetch(`http://localhost:${port}`);
    return true;
  } catch {
    return false;
  }
}

async function main() {
  console.log("CourtCoach Screenshot Capture\n");

  // Start dev server if not already running
  let devServer = null;
  const serverRunning = await isPortInUse(PORT);

  if (!serverRunning) {
    console.log(`Starting Next.js dev server on port ${PORT}...`);
    devServer = spawn("npm", ["run", "dev"], {
      cwd: path.join(__dirname, ".."),
      stdio: "pipe",
      env: { ...process.env, PORT: String(PORT) },
    });
    devServer.stderr.on("data", () => {}); // suppress stderr
    await waitForServer(BASE_URL);
    console.log("  Server ready.\n");
  } else {
    console.log(`  Using existing server at ${BASE_URL}\n`);
  }

  const browser = await puppeteer.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  let captured = 0;
  let failed = 0;

  try {
    for (const scenario of SCENARIOS) {
      for (const viewport of VIEWPORTS) {
        const filename = `${scenario.name}-${viewport.name}.png`;
        const filepath = path.join(SCREENSHOTS_DIR, filename);

        const page = await browser.newPage();
        await page.setViewport({ width: viewport.width, height: viewport.height });

        try {
          await scenario.setup(page);
          await page.screenshot({ path: filepath, fullPage: true });
          console.log(`  ✓ ${filename}`);
          captured++;
        } catch (err) {
          console.error(`  ✗ ${filename}: ${err.message}`);
          failed++;
        } finally {
          await page.close();
        }
      }
    }
  } finally {
    await browser.close();
    if (devServer) {
      devServer.kill();
    }
  }

  console.log(`\n📸 Done: ${captured} captured, ${failed} failed`);
  console.log(`📁 Saved to: screenshots/`);

  if (failed > 0) process.exit(1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
