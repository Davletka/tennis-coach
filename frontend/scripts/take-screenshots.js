// scripts/take-screenshots.js
// Captures screenshots of every page at desktop / tablet / mobile viewports.
// Usage: node scripts/take-screenshots.js
//        (dev server will be started automatically if not already running)

const puppeteer = require("puppeteer");
const { execSync, spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const http = require("http");

const BASE_URL = "http://localhost:3000";
const SCREENSHOTS_DIR = path.join(__dirname, "..", "screenshots");

const routes = [
  { path: "/analyze",  name: "analyze"  },
  { path: "/history",  name: "history"  },
  { path: "/compare",  name: "compare"  },
  { path: "/progress", name: "progress" },
  { path: "/learn",    name: "learn"    },
];

const viewports = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "tablet",  width: 768,  height: 1024 },
  { name: "mobile",  width: 375,  height: 812 },
];

function isServerRunning() {
  return new Promise((resolve) => {
    const req = http.get(BASE_URL, () => resolve(true));
    req.on("error", () => resolve(false));
    req.setTimeout(1500, () => { req.destroy(); resolve(false); });
  });
}

function waitForServer(maxMs = 30000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const check = async () => {
      if (await isServerRunning()) return resolve();
      if (Date.now() - start > maxMs) return reject(new Error("Dev server did not start in time"));
      setTimeout(check, 1000);
    };
    check();
  });
}

async function main() {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

  // Start dev server if not already running
  let devServer = null;
  if (!(await isServerRunning())) {
    console.log("Starting dev server…");
    devServer = spawn("npm", ["run", "dev"], {
      cwd: path.join(__dirname, ".."),
      stdio: "ignore",
      detached: false,
    });
    await waitForServer();
    console.log("Dev server ready.");
  } else {
    console.log("Dev server already running.");
  }

  const browser = await puppeteer.launch({ headless: "new" });
  const page = await browser.newPage();

  let captured = 0;
  const failed = [];

  for (const route of routes) {
    for (const vp of viewports) {
      const filename = `${route.name}-${vp.name}.png`;
      const outPath = path.join(SCREENSHOTS_DIR, filename);
      try {
        await page.setViewport({ width: vp.width, height: vp.height });
        await page.goto(`${BASE_URL}${route.path}`, { waitUntil: "networkidle2", timeout: 20000 });
        // Wait for React hydration + auth context to settle
        await new Promise((r) => setTimeout(r, 2000));
        await page.screenshot({ path: outPath, fullPage: true });
        console.log(`  ✓ ${filename}`);
        captured++;
      } catch (err) {
        console.error(`  ✗ ${filename}: ${err.message}`);
        failed.push(filename);
      }
    }
  }

  await browser.close();
  if (devServer) devServer.kill();

  console.log(`\n${captured} screenshot(s) saved to screenshots/`);
  if (failed.length) console.log(`Failed: ${failed.join(", ")}`);
}

main().catch((err) => { console.error(err); process.exit(1); });
