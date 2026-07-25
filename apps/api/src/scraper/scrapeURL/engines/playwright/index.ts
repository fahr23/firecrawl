import { z } from "zod";
import { config } from "../../../../config";
import { EngineScrapeResult } from "..";
import { Meta } from "../..";
import { robustFetch } from "../../lib/fetch";
import { getInnerJson } from "@mendable/firecrawl-rs";

export async function scrapeURLWithPlaywright(
  meta: Meta,
): Promise<EngineScrapeResult> {
  meta.logger.info("Scraping with Playwright", {
    url: config.PLAYWRIGHT_MICROSERVICE_URL,
    target: meta.rewrittenUrl ?? meta.url
  });

  try {
    const response = await robustFetch({
      url: config.PLAYWRIGHT_MICROSERVICE_URL!,
      headers: {
        "Content-Type": "application/json",
      },
      body: {
        url: meta.rewrittenUrl ?? meta.url,
        wait_after_load: meta.options.waitFor,
        timeout: meta.abort.scrapeTimeout(),
        headers: meta.options.headers,
        skip_tls_verification: meta.options.skipTlsVerification,
        actions: meta.options.actions,
        bypass_proxy: meta.options.bypassProxy,
      },
      method: "POST",
      logger: meta.logger.child("scrapeURLWithPlaywright/robustFetch"),
      schema: z.object({
        content: z.string(),
        pageStatusCode: z.number(),
        pageError: z.string().optional(),
        contentType: z.string().optional(),
        screenshot: z.string().optional(),
      }),
      mock: meta.mock,
      abort: meta.abort.asSignal(),
    });

    if (response.contentType?.includes("application/json")) {
      response.content = await getInnerJson(response.content);
    }

    return {
      url: meta.rewrittenUrl ?? meta.url, // TODO: impove redirect following
      html: response.content,
      statusCode: response.pageStatusCode,
      error: response.pageError,
      contentType: response.contentType,
      screenshot: response.screenshot,

      proxyUsed: "basic",
    };
  } catch (error) {
    meta.logger.error("Playwright scrape error", { error, url: config.PLAYWRIGHT_MICROSERVICE_URL });
    throw error;
  }
}

export function playwrightMaxReasonableTime(meta: Meta): number {
  const actionsWait = (meta.options.actions ?? []).reduce(
    (acc: number, a: any) => acc + (a.type === "wait" ? (a.milliseconds ?? 0) : 0),
    0
  );
  // For proxy-based scraping, page load can take 60-90 seconds; actions add extra time.
  const proxyBuffer = meta.options.proxy ? 90000 : 30000;
  return (meta.options.waitFor ?? 0) + actionsWait + proxyBuffer;
}
