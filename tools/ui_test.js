const puppeteer = require("puppeteer-core");
const path = require("path");

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const OUT = path.resolve(__dirname, "..", "..");

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: "new",
    args: ["--disable-gpu", "--hide-scrollbars"]
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 414, height: 900, deviceScaleFactor: 2 });
  page.on("console", (m) => { if (m.type() === "error") console.log("[console]", m.text()); });
  page.on("pageerror", (e) => console.log("[pageerror]", e.message));

  const url = "http://127.0.0.1:5173/index.html?view=ai";
  await page.goto(url, { waitUntil: "networkidle2" });

  // 填字並翻譯
  await page.click("#src");
  await page.type("#src", "他昨天没来上班，因为发烧了。");
  await page.click("#go");

  await page.waitForFunction(() => {
    const o = document.getElementById("out");
    return o && !o.hidden && document.querySelectorAll("#tokens .tok").length > 3;
  }, { timeout: 90000 });

  await new Promise((r) => setTimeout(r, 400));
  console.log("譯文節點：", await page.$$eval("#tokens .tok", (els) => els.map((e) => e.dataset.t).join(" | ")));
  await page.screenshot({ path: path.join(OUT, "ui_ai.png") });

  // 懸停第一個越南語詞
  const tok = await page.$("#tokens .tok");
  const box = await tok.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await new Promise((r) => setTimeout(r, 600));
  const popText = await page.$eval("#pop", (el) => (el.hidden ? "HIDDEN" : el.innerText.replace(/\n+/g, " / ")));
  console.log("彈窗內容：", popText);
  await page.screenshot({ path: path.join(OUT, "ui_pop.png") });

  // 觸控裝置：點擊詞語
  await page.mouse.move(5, 5);
  await new Promise((r) => setTimeout(r, 300));
  const mob = await browser.newPage();
  await mob.setViewport({ width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  await mob.goto(url, { waitUntil: "networkidle2" });
  await mob.evaluate(() => {
    document.getElementById("src").value = "Hôm qua anh ấy không đi làm vì bị sốt.";
  });
  await mob.click("#dirSeg button[data-dir='vi2zh']");
  await mob.click("#go");
  await mob.waitForFunction(() => {
    const o = document.getElementById("out");
    return o && !o.hidden && document.querySelectorAll("#tokens .tok").length > 3;
  }, { timeout: 90000 });
  await new Promise((r) => setTimeout(r, 400));
  console.log("越→中 譯文節點：", await mob.$$eval("#tokens .tok", (els) => els.map((e) => e.dataset.t).join(" | ")));
  await mob.screenshot({ path: path.join(OUT, "ui_vi2zh.png") });

  const t2 = await mob.$("#tokens .tok");
  await t2.click();
  await new Promise((r) => setTimeout(r, 500));
  console.log("手機彈窗：", await mob.$eval("#pop", (el) => (el.hidden ? "HIDDEN" : el.innerText.replace(/\n+/g, " / "))));
  await mob.screenshot({ path: path.join(OUT, "ui_vi2zh_pop.png") });

  await browser.close();
}

main().catch((e) => { console.error("FAILED", e); process.exit(1); });
