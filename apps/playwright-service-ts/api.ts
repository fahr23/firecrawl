import express, { Request, Response } from 'express';
import bodyParser from 'body-parser';
import { chromium, Browser, BrowserContext, Route, Request as PlaywrightRequest, Page } from 'playwright';
import dotenv from 'dotenv';
import UserAgent from 'user-agents';
import { getError } from './helpers/get_error';

dotenv.config();

const app = express();
const port = process.env.PORT || 3003;

app.use(bodyParser.json());

const BLOCK_MEDIA = (process.env.BLOCK_MEDIA || 'False').toUpperCase() === 'TRUE';
const MAX_CONCURRENT_PAGES = Math.max(1, Number.parseInt(process.env.MAX_CONCURRENT_PAGES ?? '10', 10) || 10);

const PROXY_SERVER = process.env.PROXY_SERVER || null;
const PROXY_USERNAME = process.env.PROXY_USERNAME || null;
const PROXY_PASSWORD = process.env.PROXY_PASSWORD || null;
class Semaphore {
  private permits: number;
  private queue: (() => void)[] = [];

  constructor(permits: number) {
    this.permits = permits;
  }

  async acquire(): Promise<void> {
    if (this.permits > 0) {
      this.permits--;
      return Promise.resolve();
    }

    return new Promise<void>((resolve) => {
      this.queue.push(resolve);
    });
  }

  release(): void {
    this.permits++;
    if (this.queue.length > 0) {
      const nextResolve = this.queue.shift();
      if (nextResolve) {
        this.permits--;
        nextResolve();
      }
    }
  }

  getAvailablePermits(): number {
    return this.permits;
  }

  getQueueLength(): number {
    return this.queue.length;
  }
}
const pageSemaphore = new Semaphore(MAX_CONCURRENT_PAGES);

const AD_SERVING_DOMAINS = [
  'doubleclick.net',
  'adservice.google.com',
  'googlesyndication.com',
  'googletagservices.com',
  'googletagmanager.com',
  'google-analytics.com',
  'adsystem.com',
  'adservice.com',
  'adnxs.com',
  'ads-twitter.com',
  'facebook.net',
  'fbcdn.net',
  'amazon-adsystem.com'
];

interface UrlModel {
  url: string;
  wait_after_load?: number;
  timeout?: number;
  headers?: { [key: string]: string };
  check_selector?: string;
  skip_tls_verification?: boolean;
  action?: string; // 'click', 'write', 'press', etc.
  selector?: string; // selector for the action
  value?: string; // value for write/type actions
}

let browser: Browser;

const initializeBrowser = async () => {
  browser = await chromium.launch({
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-accelerated-2d-canvas',
      '--no-first-run',
      '--no-zygote',
      '--disable-gpu'
    ]
  });
};

const createContext = async (skipTlsVerification: boolean = false, customUserAgent?: string) => {
  const userAgent = customUserAgent || new UserAgent().toString();
  const viewport = { width: 1280, height: 800 };

  const contextOptions: any = {
    userAgent,
    viewport,
    ignoreHTTPSErrors: skipTlsVerification,
  };

  if (PROXY_SERVER && PROXY_USERNAME && PROXY_PASSWORD) {
    contextOptions.proxy = {
      server: PROXY_SERVER,
      username: PROXY_USERNAME,
      password: PROXY_PASSWORD,
    };
  } else if (PROXY_SERVER) {
    contextOptions.proxy = {
      server: PROXY_SERVER,
    };
  }

  const newContext = await browser.newContext(contextOptions);

  if (BLOCK_MEDIA) {
    await newContext.route('**/*.{png,jpg,jpeg,gif,svg,mp3,mp4,avi,flac,ogg,wav,webm}', async (route: Route, request: PlaywrightRequest) => {
      await route.abort();
    });
  }

  // Intercept all requests to avoid loading ads
  await newContext.route('**/*', (route: Route, request: PlaywrightRequest) => {
    const requestUrl = new URL(request.url());
    const hostname = requestUrl.hostname;

    if (AD_SERVING_DOMAINS.some(domain => hostname.includes(domain))) {
      console.log(hostname);
      return route.abort();
    }
    return route.continue();
  });

  return newContext;
};

const shutdownBrowser = async () => {
  if (browser) {
    await browser.close();
  }
};

const isValidUrl = (urlString: string): boolean => {
  try {
    new URL(urlString);
    return true;
  } catch (_) {
    return false;
  }
};

const scrapePage = async (page: Page, url: string, waitUntil: 'load' | 'networkidle', waitAfterLoad: number, timeout: number, checkSelector: string | undefined) => {
  console.log(`Navigating to ${url} with waitUntil: ${waitUntil} and timeout: ${timeout}ms`);
  const response = await page.goto(url, { waitUntil, timeout });

  if (waitAfterLoad > 0) {
    await page.waitForTimeout(waitAfterLoad);
  }

  if (checkSelector) {
    try {
      await page.waitForSelector(checkSelector, { timeout });
    } catch (error) {
      throw new Error('Required selector not found');
    }
  }

  let headers = null, content = await page.content();
  let ct: string | undefined = undefined;
  if (response) {
    headers = await response.allHeaders();
    ct = Object.entries(headers).find(([key]) => key.toLowerCase() === "content-type")?.[1];
    if (ct && (ct.toLowerCase().includes("application/json") || ct.toLowerCase().includes("text/plain"))) {
      content = (await response.body()).toString("utf8"); // TODO: determine real encoding
    }
  }

  return {
    content,
    status: response ? response.status() : null,
    headers,
    contentType: ct,
  };
};

app.get('/health', async (req: Request, res: Response) => {
  try {
    if (!browser) {
      await initializeBrowser();
    }

    const testContext = await createContext();
    const testPage = await testContext.newPage();
    await testPage.close();
    await testContext.close();

    res.status(200).json({
      status: 'healthy',
      maxConcurrentPages: MAX_CONCURRENT_PAGES,
      activePages: MAX_CONCURRENT_PAGES - pageSemaphore.getAvailablePermits()
    });
  } catch (error) {
    console.error('Health check failed:', error);
    res.status(503).json({
      status: 'unhealthy',
      error: error instanceof Error ? error.message : 'Unknown error occurred'
    });
  }
});

app.post('/scrape', async (req: Request, res: Response) => {
  const { url, wait_after_load = 0, timeout = 15000, headers, check_selector, skip_tls_verification = false, action, selector, value }: UrlModel = req.body;

  console.log(`================= Scrape Request =================`);
  console.log(`URL: ${url}`);
  console.log(`Wait After Load: ${wait_after_load}`);
  console.log(`Timeout: ${timeout}`);
  console.log(`Headers: ${headers ? JSON.stringify(headers) : 'None'}`);
  console.log(`Check Selector: ${check_selector ? check_selector : 'None'}`);
  console.log(`Skip TLS Verification: ${skip_tls_verification}`);
  if (action) {
    console.log(`Action: ${action}`);
    console.log(`Selector: ${selector}`);
    console.log(`Value: ${value || 'None'}`);
  }
  console.log(`==================================================`);

  if (!url) {
    return res.status(400).json({ error: 'URL is required' });
  }

  if (!isValidUrl(url)) {
    return res.status(400).json({ error: 'Invalid URL' });
  }

  if (!PROXY_SERVER) {
    console.warn('⚠️ WARNING: No proxy server provided. Your IP address may be blocked.');
  }

  if (!browser) {
    await initializeBrowser();
  }

  await pageSemaphore.acquire();

  let requestContext: BrowserContext | null = null;
  let page: Page | null = null;

  try {
    // Extract User-Agent from headers if present
    const customUserAgent = headers
      ? Object.entries(headers).find(([k]) => k.toLowerCase() === 'user-agent')?.[1]
      : undefined;

    requestContext = await createContext(skip_tls_verification, customUserAgent);
    page = await requestContext.newPage();

    if (headers) {
      await page.setExtraHTTPHeaders(headers);
    }

    const result = await scrapePage(page, url, 'load', wait_after_load, timeout, check_selector);

    // Compatibility with single action
    const actionsToExecute = req.body.actions || [];
    if (action && selector) {
      actionsToExecute.push({ type: action, selector, value });
    }

    // Execute actions sequentially
    for (const act of actionsToExecute) {
      try {
        if (!act.type) continue;
        const actionType = act.type.toLowerCase();

        switch (actionType) {
          case 'wait':
            if (act.milliseconds) {
              console.log(`Waiting for ${act.milliseconds}ms`);
              await page.waitForTimeout(act.milliseconds);
            } else if (act.selector) {
              console.log(`Waiting for selector: ${act.selector}`);
              await page.waitForSelector(act.selector, { timeout: 5000 });
            }
            break;

          case 'click':
            if (act.selector) {
              console.log(`Clicking selector: ${act.selector}`);
              await page.click(act.selector);
            }
            break;

          case 'write':
          case 'type':
            if (act.selector && act.text) {
              console.log(`Writing to selector: ${act.selector}, text: ${act.text}`);
              await page.fill(act.selector, act.text);
            } else if (act.selector && act.value) { // backward compatibility
              console.log(`Writing to selector: ${act.selector}, value: ${act.value}`);
              await page.fill(act.selector, act.value);
            }
            break;

          case 'press':
            if (act.key) {
              console.log(`Pressing key: ${act.key}`);
              await page.keyboard.press(act.key);
            } else if (act.selector && act.value) { // backward compatibility
              console.log(`Pressing key: ${act.value} on selector: ${act.selector}`);
              await page.press(act.selector, act.value);
            }
            break;

          case 'scroll':
            console.log(`Scrolling ${act.direction || 'down'}`);
            if (act.selector) {
              const element = await page.$(act.selector);
              if (element) {
                await element.scrollIntoViewIfNeeded();
              }
            } else {
              if (act.direction === 'up') {
                await page.evaluate(() => window.scrollBy(0, -window.innerHeight));
              } else {
                await page.evaluate(() => window.scrollBy(0, window.innerHeight));
              }
            }
            break;

          case 'screenshot':
            console.log(`Taking screenshot`);
            const screenshot = await page.screenshot({
              fullPage: act.fullPage ?? false
            });
            // We can't easily return multiple screenshots in the current response structure designed for one content
            // So we'll attach the last screenshot to the result or maybe headers?
            // For now, let's just allow it to happen, but maybe we need to return it.
            // valid firecrawl response expects 'screenshot' field in the root or 'screenshots' list.
            // The current API response structure is flat. Let's try to return it in the body if it's the only one, or append to a list if we change the response type.
            // For simplicity and to match the demo requirement ("Take a screenshot"), we will return the base64 of the last screenshot taken.
            res.locals = res.locals || {};
            res.locals.screenshot = screenshot.toString('base64');
            break;

          default:
            console.warn(`Unknown action type: ${actionType}`);
        }

        // Optional: wait a bit after each action
        await page.waitForTimeout(500);
      } catch (actionError) {
        console.warn(`Action ${act.type} failed: ${actionError}`);
      }
    }

    // Get updated content after actions
    const updatedContent = await page.content();
    result.content = updatedContent;

    const pageError = result.status !== 200 ? getError(result.status) : undefined;

    if (!pageError) {
      console.log(`✅ Scrape successful!`);
    } else {
      console.log(`🚨 Scrape failed with status code: ${result.status} ${pageError}`);
    }

    const responseBody: any = {
      content: result.content,
      pageStatusCode: result.status,
      contentType: result.contentType,
      ...(pageError && { pageError })
    };

    // If we took a screenshot, include it
    if (res.locals && res.locals.screenshot) {
      responseBody.screenshot = res.locals.screenshot;
    }

    res.json(responseBody);

  } catch (error) {
    console.error('Scrape error:', error);
    res.status(500).json({ error: 'An error occurred while fetching the page.' });
  } finally {
    if (page) await page.close();
    if (requestContext) await requestContext.close();
    pageSemaphore.release();
  }
});

app.listen(port, () => {
  initializeBrowser().then(() => {
    console.log(`Server is running on port ${port}`);
  });
});

if (require.main === module) {
  process.on('SIGINT', () => {
    shutdownBrowser().then(() => {
      console.log('Browser closed');
      process.exit(0);
    });
  });
}
