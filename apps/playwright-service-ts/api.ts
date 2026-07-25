import express, { Request, Response } from 'express';
import {
  chromium,
  Browser,
  BrowserContext,
  Route,
  Request as PlaywrightRequest,
  Page,
} from 'playwright';
import dotenv from 'dotenv';
import UserAgent from 'user-agents';
import { getError } from './helpers/get_error';
import { lookup } from 'dns/promises';
import IPAddr from 'ipaddr.js';
import { Server, RequestError } from 'proxy-chain';

dotenv.config();

const app = express();
const port = process.env.PORT || 3003;

app.use(express.json());

const BLOCK_MEDIA =
  (process.env.BLOCK_MEDIA || 'False').toUpperCase() === 'TRUE';
const MAX_CONCURRENT_PAGES = Math.max(
  1,
  Number.parseInt(process.env.MAX_CONCURRENT_PAGES ?? '10', 10) || 10,
);
const ALLOW_LOCAL_WEBHOOKS =
  (process.env.ALLOW_LOCAL_WEBHOOKS || 'False').toUpperCase() === 'TRUE';

const PROXY_SERVER = process.env.PROXY_SERVER || null;
const PROXY_USERNAME = process.env.PROXY_USERNAME || null;
const PROXY_PASSWORD = process.env.PROXY_PASSWORD || null;

class InsecureConnectionError extends Error {
  constructor(
    public readonly blockedUrl: string,
    reason: string,
  ) {
    super(`Blocked insecure target URL "${blockedUrl}": ${reason}`);
    this.name = 'InsecureConnectionError';
  }
}

const isInternalHost = async (hostname: string): Promise<boolean> => {
  const host = hostname.toLowerCase().replace(/\.$/, '');
  if (!host) return true;

  let addresses: string[];
  if (IPAddr.isValid(host)) {
    addresses = [host];
  } else {
    try {
      addresses = (await lookup(host, { all: true })).map((a) => a.address);
    } catch {
      return true;
    }
  }
  return (
    addresses.length === 0 ||
    addresses.some((a) => IPAddr.parse(a).range() !== 'unicast')
  );
};

const assertSafeTargetUrl = async (urlString: string): Promise<void> => {
  let parsedUrl: URL;
  try {
    parsedUrl = new URL(urlString);
  } catch {
    throw new InsecureConnectionError(urlString, 'URL is invalid');
  }
  if (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:') {
    throw new InsecureConnectionError(
      urlString,
      `unsupported protocol "${parsedUrl.protocol}"`,
    );
  }
  if (!ALLOW_LOCAL_WEBHOOKS && (await isInternalHost(parsedUrl.hostname))) {
    throw new InsecureConnectionError(
      urlString,
      'resolves to a private/internal address',
    );
  }
};

const buildUpstreamProxyUrl = (): string | undefined => {
  if (!PROXY_SERVER) return undefined;
  const server = PROXY_SERVER.includes('://')
    ? PROXY_SERVER
    : `http://${PROXY_SERVER}`;
  const url = new URL(server);
  if (PROXY_USERNAME) url.username = PROXY_USERNAME;
  if (PROXY_PASSWORD) url.password = PROXY_PASSWORD;
  return url.toString();
};

const startSSRFProxy = async (
  useUpstreamProxy: boolean = true,
): Promise<number> => {
  const server = new Server({
    port: 0,
    host: '127.0.0.1',
    prepareRequestFunction: async ({ hostname }) => {
      if (!ALLOW_LOCAL_WEBHOOKS && (await isInternalHost(hostname))) {
        throw new RequestError(
          'Blocked: target resolves to a private/internal address',
          403,
        );
      }
      return {
        upstreamProxyUrl: useUpstreamProxy
          ? buildUpstreamProxyUrl()
          : undefined,
      };
    },
  });
  await server.listen();
  return server.port;
};

let ssrfProxyPort: number;
let directSsrfProxyPort: number;

type ContextSecurityState = {
  blockedNavigationRequestUrl: string | null;
};
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
  'amazon-adsystem.com',
];

interface UrlModel {
  url: string;
  wait_after_load?: number;
  timeout?: number;
  headers?: { [key: string]: string };
  check_selector?: string;
  skip_tls_verification?: boolean;
  bypass_proxy?: boolean;
  action?: string; // 'click', 'write', 'press', etc.
  selector?: string; // selector for the action
  value?: string; // value for write/type actions
  actions?: Array<Record<string, any>>;
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
      '--disable-gpu',
    ],
  });
};

const createContext = async (
  skipTlsVerification: boolean = false,
  userAgentOverride?: string,
  bypassProxy: boolean = false,
): Promise<{
  context: BrowserContext;
  securityState: ContextSecurityState;
}> => {
  const userAgent = userAgentOverride || new UserAgent().toString();
  const viewport = { width: 1280, height: 800 };
  const securityState: ContextSecurityState = {
    blockedNavigationRequestUrl: null,
  };

  const contextOptions: any = {
    userAgent,
    viewport,
    ignoreHTTPSErrors: skipTlsVerification,
    serviceWorkers: 'block',
  };

  contextOptions.proxy = {
    // Even when bypassing the configured upstream proxy, retain the local
    // SSRF-filtering proxy so private/internal targets remain blocked.
    server: `http://127.0.0.1:${
      bypassProxy ? directSsrfProxyPort : ssrfProxyPort
    }`,
  };

  const newContext = await browser.newContext(contextOptions);

  if (BLOCK_MEDIA) {
    await newContext.route(
      '**/*.{png,jpg,jpeg,gif,svg,mp3,mp4,avi,flac,ogg,wav,webm}',
      async (route: Route, request: PlaywrightRequest) => {
        await route.abort();
      },
    );
  }

  // Intercept all requests to avoid loading ads
  await newContext.route(
    '**/*',
    async (route: Route, request: PlaywrightRequest) => {
      const requestUrlString = request.url();
      try {
        await assertSafeTargetUrl(requestUrlString);
      } catch (error) {
        if (error instanceof InsecureConnectionError) {
          if (request.isNavigationRequest()) {
            securityState.blockedNavigationRequestUrl = requestUrlString;
          }
          console.warn(`Blocked request: ${requestUrlString}`);
          return route.abort('blockedbyclient');
        }
        throw error;
      }

      const hostname = new URL(requestUrlString).hostname.toLowerCase();

      if (AD_SERVING_DOMAINS.some((domain) => hostname.includes(domain))) {
        console.log(hostname);
        return route.abort();
      }
      return route.continue();
    },
  );

  return { context: newContext, securityState };
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

const scrapePage = async (
  page: Page,
  url: string,
  waitUntil: 'load' | 'networkidle' | 'domcontentloaded' | 'commit',
  waitAfterLoad: number,
  timeout: number,
  checkSelector: string | undefined,
  securityState: ContextSecurityState,
) => {
  console.log(
    `Navigating to ${url} with waitUntil: ${waitUntil} and timeout: ${timeout}ms`,
  );
  let response;
  try {
    response = await page.goto(url, { waitUntil, timeout });
  } catch (error) {
    if (securityState.blockedNavigationRequestUrl) {
      throw new InsecureConnectionError(
        securityState.blockedNavigationRequestUrl,
        'navigation to private/internal resource is not allowed',
      );
    }
    throw error;
  }

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

  let headers = null,
    content = await page.content();
  let ct: string | undefined = undefined;
  if (response) {
    headers = await response.allHeaders();
    ct = Object.entries(headers).find(
      ([key]) => key.toLowerCase() === 'content-type',
    )?.[1];
    if (
      ct &&
      (ct.toLowerCase().includes('application/json') ||
        ct.toLowerCase().includes('text/plain'))
    ) {
      content = (await response.body()).toString('utf8'); // TODO: determine real encoding
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
    const { context: testContext } = await createContext();
    const testPage = await testContext.newPage();
    await testPage.close();
    await testContext.close();

    res.status(200).json({
      status: 'healthy',
      maxConcurrentPages: MAX_CONCURRENT_PAGES,
      activePages: MAX_CONCURRENT_PAGES - pageSemaphore.getAvailablePermits(),
    });
  } catch (error) {
    console.error('Health check failed:', error);
    res.status(503).json({
      status: 'unhealthy',
      error: error instanceof Error ? error.message : 'Unknown error occurred',
    });
  }
});

app.post('/scrape', async (req: Request, res: Response) => {
  const defaultTimeout = Number.parseInt(
    process.env.DEFAULT_TIMEOUT || '90000',
    10,
  );
  const {
    url,
    wait_after_load = 0,
    timeout = defaultTimeout,
    headers,
    check_selector,
    skip_tls_verification = false,
    action,
    selector,
    value,
    bypass_proxy = false,
  }: UrlModel = req.body;

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

  try {
    await assertSafeTargetUrl(url);
  } catch (error) {
    if (error instanceof InsecureConnectionError) {
      return res.json({
        content: '',
        pageStatusCode: 403,
        pageError: error.message,
      });
    }
    throw error;
  }

  if (!PROXY_SERVER) {
    console.warn(
      '⚠️ WARNING: No proxy server provided. Your IP address may be blocked.',
    );
  }

  if (!browser) {
    await initializeBrowser();
  }

  await pageSemaphore.acquire();

  let requestContext: BrowserContext | null = null;
  let securityState: ContextSecurityState | null = null;
  let page: Page | null = null;

  try {
    // Extract user-agent from request headers (case-insensitive) so it can
    // be applied at the context level.  Playwright ignores user-agent in
    // setExtraHTTPHeaders when the context already defines one (#2802).
    const userAgentOverride = headers
      ? Object.entries(headers).find(
          ([k]) => k.toLowerCase() === 'user-agent',
        )?.[1]
      : undefined;

    const contextBundle = await createContext(
      skip_tls_verification,
      userAgentOverride,
      bypass_proxy,
    );
    requestContext = contextBundle.context;
    securityState = contextBundle.securityState;
    page = await requestContext.newPage();

    if (headers) {
      // A Cookie header passed through setExtraHTTPHeaders is sent on the first
      // request but DROPPED on any redirect hop (the browser regenerates the
      // redirected request from its cookie jar, which is empty). Authenticated
      // sites that 302 (e.g. to /signin when the session looks absent) then
      // land on the login page. Seed the cookie jar instead so Chromium re-sends
      // it on every request, including redirects — matching what a raw HTTP
      // client does.
      const cookieHeader = Object.entries(headers).find(
        ([k]) => k.toLowerCase() === 'cookie',
      )?.[1];
      if (cookieHeader) {
        // Scope cookies to the registrable domain (e.g. ".example.com"), not
        // host-only. Authenticated pages often 302 across sibling subdomains
        // (example.com -> app.example.com); a host-only cookie set for the
        // original host would not be sent to the redirect target, leaving the
        // request unauthenticated. The Cookie header carries no domain info, so
        // we apply the eTLD+1 — broad enough to follow the redirect, and these
        // are first-party cookies being returned to their own origin anyway.
        let cookieDomain: string | undefined;
        try {
          const host = new URL(url).hostname;
          const labels = host.split('.');
          cookieDomain = labels.length > 2 ? labels.slice(-2).join('.') : host;
        } catch {
          cookieDomain = undefined;
        }
        type SeedCookie = {
          name: string;
          value: string;
          url?: string;
          domain?: string;
          path?: string;
        };
        const cookies = cookieHeader
          .split(';')
          .map((pair) => pair.trim())
          .filter(Boolean)
          .map((pair): SeedCookie | null => {
            const eq = pair.indexOf('=');
            if (eq === -1) return null;
            const name = pair.slice(0, eq).trim();
            const value = pair.slice(eq + 1).trim();
            return cookieDomain
              ? { name, value, domain: `.${cookieDomain}`, path: '/' }
              : { name, value, url };
          })
          .filter((c): c is SeedCookie => c !== null);
        if (cookies.length > 0) {
          try {
            await requestContext.addCookies(cookies);
          } catch (error) {
            console.warn('Failed to seed cookies from Cookie header:', error);
          }
        }
      }

      // Remove user-agent (already applied at the context level) and cookie
      // (now seeded into the jar) before forwarding the rest verbatim.
      const filteredHeaders = Object.fromEntries(
        Object.entries(headers).filter(([k]) => {
          const lower = k.toLowerCase();
          return lower !== 'user-agent' && lower !== 'cookie';
        }),
      );
      if (Object.keys(filteredHeaders).length > 0) {
        await page.setExtraHTTPHeaders(filteredHeaders);
      }
    }

    const waitUntil =
      (process.env.DEFAULT_WAIT_UNTIL as
        | 'load'
        | 'networkidle'
        | 'domcontentloaded'
        | 'commit'
        | undefined) || 'domcontentloaded';
    const result = await scrapePage(
      page,
      url,
      waitUntil,
      wait_after_load,
      timeout,
      check_selector,
      securityState,
    );
    // Compatibility with single action
    const actionsToExecute = [...(req.body.actions || [])];
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

          case 'executejavascript':
            if (act.script) {
              console.log(`Executing JavaScript`);
              try {
                await page.evaluate(act.script);
              } catch (e: any) {
                console.warn(`JavaScript execution error: ${e.message}`);
              }
            }
            break;

          case 'scrape':
            // Marker action — content is captured at the end automatically.
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

    // SPA client-side routes often return HTTP 404 from the server, but after
    // JavaScript executes the correct content is rendered. When actions were
    // provided the caller explicitly wanted client-side rendering, so treat 404
    // as non-fatal and report 200 if we have content.
    const hasActions = actionsToExecute.length > 0;
    const effectiveStatus =
      result.status === 404 && hasActions && updatedContent.length > 500
        ? 200
        : result.status;

    const pageError =
      effectiveStatus !== 200 ? getError(effectiveStatus) : undefined;

    if (!pageError) {
      console.log(`✅ Scrape successful! (original HTTP ${result.status})`);
    } else {
      console.log(
        `🚨 Scrape failed with status code: ${result.status} ${pageError}`,
      );
    }

    const responseBody: any = {
      content: result.content,
      pageStatusCode: effectiveStatus,
      contentType: result.contentType,
      ...(pageError && { pageError }),
    };

    // If we took a screenshot, include it
    if (res.locals && res.locals.screenshot) {
      responseBody.screenshot = res.locals.screenshot;
    }

    res.json(responseBody);
  } catch (error) {
    if (error instanceof InsecureConnectionError) {
      return res.json({
        content: '',
        pageStatusCode: 403,
        pageError: error.message,
      });
    }
    console.error('Scrape error:', error);
    res
      .status(500)
      .json({ error: 'An error occurred while fetching the page.' });
  } finally {
    if (page) await page.close();
    if (requestContext) await requestContext.close();
    pageSemaphore.release();
  }
});

const start = async () => {
  ssrfProxyPort = await startSSRFProxy();
  directSsrfProxyPort = PROXY_SERVER
    ? await startSSRFProxy(false)
    : ssrfProxyPort;
  await initializeBrowser();
  app.listen(port, () => {
    console.log(`Server is running on port ${port}`);
  });
};
start().catch((error) => {
  console.error('Failed to start server:', error);
  process.exit(1);
});

if (require.main === module) {
  process.on('SIGINT', () => {
    shutdownBrowser().then(() => {
      console.log('Browser closed');
      process.exit(0);
    });
  });
}
