import axios, { type AxiosResponse, type AxiosRequestHeaders, AxiosError } from "axios";
import * as zt from "zod";
import { zodToJsonSchema } from "zod-to-json-schema";
import { WebSocket } from "isows";
import { TypedEventTarget } from "typescript-event-target";

/**
 * Configuration interface for FirecrawlApp.
 * @param apiKey - Optional API key for authentication.
 * @param apiUrl - Optional base URL of the API; defaults to 'https://api.firecrawl.dev'.
 */
export interface FirecrawlAppConfig {
  apiKey?: string | null;
  apiUrl?: string | null;
}

/**
 * Metadata for a Firecrawl document.
 * Includes various optional properties for document metadata.
 */
export interface FirecrawlDocumentMetadata {
  title?: string;
  description?: string;
  language?: string;
  keywords?: string;
  robots?: string;
  ogTitle?: string;
  ogDescription?: string;
  ogUrl?: string;
  ogImage?: string;
  ogAudio?: string;
  ogDeterminer?: string;
  ogLocale?: string;
  ogLocaleAlternate?: string[];
  ogSiteName?: string;
  ogVideo?: string;
  dctermsCreated?: string;
  dcDateCreated?: string;
  dcDate?: string;
  dctermsType?: string;
  dcType?: string;
  dctermsAudience?: string;
  dctermsSubject?: string;
  dcSubject?: string;
  dcDescription?: string;
  dctermsKeywords?: string;
  modifiedTime?: string;
  publishedTime?: string;
  articleTag?: string;
  articleSection?: string;
  sourceURL?: string;
  statusCode?: number;
  error?: string;
  [key: string]: any; // Allows for additional metadata properties not explicitly defined.
}

/**
 * Document interface for Firecrawl.
 * Represents a document retrieved or processed by Firecrawl.
 */
export interface FirecrawlDocument<T = any, ActionsSchema extends (ActionsResult | never) = never> {
  url?: string;
  markdown?: string;
  html?: string;
  rawHtml?: string;
  links?: string[];
  extract?: T;
  screenshot?: string;
  metadata?: FirecrawlDocumentMetadata;
  actions: ActionsSchema;
  // v1 search only
  title?: string;
  description?: string;
}

/**
 * Parameters for scraping operations.
 * Defines the options and configurations available for scraping web content.
 */
export interface CrawlScrapeOptions {
  formats: ("markdown" | "html" | "rawHtml" | "content" | "links" | "screenshot" | "screenshot@fullPage" | "extract")[];
  headers?: Record<string, string>;
  includeTags?: string[];
  excludeTags?: string[];
  onlyMainContent?: boolean;
  waitFor?: number;
  timeout?: number;
  location?: {
    country?: string;
    languages?: string[];
  };
  mobile?: boolean;
  skipTlsVerification?: boolean;
  removeBase64Images?: boolean;
}

export type Action = {
  type: "wait",
  milliseconds?: number,
  selector?: string,
} | {
  type: "click",
  selector: string,
} | {
  type: "screenshot",
  fullPage?: boolean,
} | {
  type: "write",
  text: string,
} | {
  type: "press",
  key: string,
} | {
  type: "scroll",
  direction?: "up" | "down",
  selector?: string,
} | {
  type: "scrape",
} | {
  type: "executeJavascript",
  script: string,
};

export interface ScrapeParams<LLMSchema extends zt.ZodSchema = any, ActionsSchema extends (Action[] | undefined) = undefined> extends CrawlScrapeOptions {
  extract?: {
    prompt?: string;
    schema?: LLMSchema;
    systemPrompt?: string;
  };
  actions?: ActionsSchema;
}

export interface ActionsResult {
  screenshots: string[];
}

/**
 * Response interface for scraping operations.
 * Defines the structure of the response received after a scraping operation.
 */
export interface ScrapeResponse<LLMResult = any, ActionsSchema extends (ActionsResult | never) = never> extends FirecrawlDocument<LLMResult, ActionsSchema> {
  success: true;
  warning?: string;
  error?: string;
}

/**
 * Parameters for crawling operations.
 * Includes options for both scraping and mapping during a crawl.
 */
export interface CrawlParams {
  includePaths?: string[];
  excludePaths?: string[];
  maxDepth?: number;
  limit?: number;
  allowBackwardLinks?: boolean;
  allowExternalLinks?: boolean;
  ignoreSitemap?: boolean;
  scrapeOptions?: CrawlScrapeOptions;
  webhook?: string | {
    url: string;
    headers?: Record<string, string>;
    metadata?: Record<string, string>;
  };
  deduplicateSimilarURLs?: boolean;
  ignoreQueryParameters?: boolean;
}

/**
 * Response interface for crawling operations.
 * Defines the structure of the response received after initiating a crawl.
 */
export interface CrawlResponse {
  id?: string;
  url?: string;
  success: true;
  error?: string;
}

/**
 * Response interface for batch scrape operations.
 * Defines the structure of the response received after initiating a crawl.
 */
export interface BatchScrapeResponse {
  id?: string;
  url?: string;
  success: true;
  error?: string;
  invalidURLs?: string[];
}

/**
 * Response interface for job status checks.
 * Provides detailed status of a crawl job including progress and results.
 */
export interface CrawlStatusResponse {
  success: true;
  status: "scraping" | "completed" | "failed" | "cancelled";
  completed: number;
  total: number;
  creditsUsed: number;
  expiresAt: Date;
  next?: string;
  data: FirecrawlDocument<undefined>[];
};

/**
 * Response interface for batch scrape job status checks.
 * Provides detailed status of a batch scrape job including progress and results.
 */
export interface BatchScrapeStatusResponse {
  success: true;
  status: "scraping" | "completed" | "failed" | "cancelled";
  completed: number;
  total: number;
  creditsUsed: number;
  expiresAt: Date;
  next?: string;
  data: FirecrawlDocument<undefined>[];
};

/**
 * Parameters for mapping operations.
 * Defines options for mapping URLs during a crawl.
 */
export interface MapParams {
  search?: string;
  ignoreSitemap?: boolean;
  includeSubdomains?: boolean;
  sitemapOnly?: boolean;
  limit?: number;
}

/**
 * Response interface for mapping operations.
 * Defines the structure of the response received after a mapping operation.
 */
export interface MapResponse {
  success: true;
  links?: string[];
  error?: string;
}

/**
 * Parameters for extracting information from URLs.
 * Defines options for extracting information from URLs.
 */
export interface ExtractParams<LLMSchema extends zt.ZodSchema = any> {
  prompt?: string;
  schema?: LLMSchema | object;
  systemPrompt?: string;
  allowExternalLinks?: boolean;
  includeSubdomains?: boolean;
}

/**
 * Response interface for extracting information from URLs.
 * Defines the structure of the response received after extracting information from URLs.
 */
export interface ExtractResponse<LLMSchema extends zt.ZodSchema = any> {
  success: boolean;
  data: LLMSchema;
  error?: string;
  warning?: string;
}

/**
 * Error response interface.
 * Defines the structure of the response received when an error occurs.
 */
export interface ErrorResponse {
  success: false;
  error: string;
}

/**
 * Custom error class for Firecrawl.
 * Extends the built-in Error class to include a status code.
 */
export class FirecrawlError extends Error {
  statusCode: number;
  constructor(message: string, statusCode: number) {
    super(message);
    this.statusCode = statusCode;
  }
}

/**
 * Parameters for search operations.
 * Defines options for searching and scraping search results.
 */
export interface SearchParams {
  limit?: number;
  tbs?: string;
  filter?: string;
  lang?: string;
  country?: string;
  location?: string;
  origin?: string;
  timeout?: number;
  scrapeOptions?: ScrapeParams;
}

/**
 * Response interface for search operations.
 * Defines the structure of the response received after a search operation.
 */
export interface SearchResponse {
  success: boolean;
  data: FirecrawlDocument<undefined>[];
  warning?: string;
  error?: string;
}

/**
 * Main class for interacting with the Firecrawl API.
 * Provides methods for scraping, searching, crawling, and mapping web content.
 */
export default class FirecrawlApp {
  public apiKey: string;
  public apiUrl: string;

  private isCloudService(url: string): boolean {
    return url.includes('api.firecrawl.dev');
  }

  /**
   * Initializes a new instance of the FirecrawlApp class.
   * @param config - Configuration options for the FirecrawlApp instance.
   */
  constructor({ apiKey = null, apiUrl = null }: FirecrawlAppConfig) {
    const baseUrl = apiUrl || "https://api.firecrawl.dev";
    
    if (this.isCloudService(baseUrl) && typeof apiKey !== "string") {
      throw new FirecrawlError("No API key provided", 401);
    }

    this.apiKey = apiKey || '';
    this.apiUrl = baseUrl;
  }

  /**
   * Scrapes a URL using the Firecrawl API.
   * @param url - The URL to scrape.
   * @param params - Additional parameters for the scrape request.
   * @returns The response from the scrape operation.
   */
  async scrapeUrl<T extends zt.ZodSchema, ActionsSchema extends (Action[] | undefined) = undefined>(
    url: string,
    params?: ScrapeParams<T, ActionsSchema>
  ): Promise<ScrapeResponse<zt.infer<T>, ActionsSchema extends Action[] ? ActionsResult : never> | ErrorResponse> {
    const headers: AxiosRequestHeaders = {
      "Content-Type": "application/json",
      Authorization: `Bearer ${this.apiKey}`,
    } as AxiosRequestHeaders;
    let jsonData: any = { url, ...params };
    if (jsonData?.extract?.schema) {
      let schema = jsonData.extract.schema;

      // Try parsing the schema as a Zod schema
      try {
        schema = zodToJsonSchema(schema);
      } catch (error) {
        
      }
      jsonData = {
        ...jsonData,
        extract: {
          ...jsonData.extract,
          schema: schema,
        },
      };
    }
    try {
      const response: AxiosResponse = await axios.post(
        this.apiUrl + `/v1/scrape`,
        jsonData,
        { headers }
      );
      if (response.status === 200) {
        const responseData = response.data;
        if (responseData.success) {
          return {
            success: true,
            warning: responseData.warning,
            error: responseData.error,
            ...responseData.data
          };
        } else {
          throw new FirecrawlError(`Failed to scrape URL. Error: ${responseData.error}`, response.status);
        }
      } else {
        this.handleError(response, "scrape URL");
      }
    } catch (error: any) {
      this.handleError(error.response, "scrape URL");
    }
    return { success: false, error: "Internal server error." };
  }

  /**
   * Searches using the Firecrawl API and optionally scrapes the results.
   * @param query - The search query string.
   * @param params - Optional parameters for the search request.
   * @returns The response from the search operation.
   */
  async search(query: string, params?: SearchParams | Record<string, any>): Promise<SearchResponse> {
    const headers: AxiosRequestHeaders = {
      "Content-Type": "application/json",
      Authorization: `Bearer ${this.apiKey}`,
    } as AxiosRequestHeaders;

    let jsonData: any = {
      query,
      limit: params?.limit ?? 5,
      tbs: params?.tbs,
      filter: params?.filter,
      lang: params?.lang ?? "en",
      country: params?.country ?? "us",
      location: params?.location,
      origin: params?.origin ?? "api",
      timeout: params?.timeout ?? 60000,
      scrapeOptions: params?.scrapeOptions ?? { formats: [] },
    };

    if (jsonData?.scrapeOptions?.extract?.schema) {
      let schema = jsonData.scrapeOptions.extract.schema;

      // Try parsing the schema as a Zod schema
      try {
        schema = zodToJsonSchema(schema);
      } catch (error) {
        
      }
      jsonData = {
        ...jsonData,
        scrapeOptions: {
          ...jsonData.scrapeOptions,
          extract: {
            ...jsonData.scrapeOptions.extract,
            schema: schema,
          },
        },
      };
    }

    try {
      const response: AxiosResponse = await this.postRequest(
        this.apiUrl + `/v1/search`,
        jsonData,
        headers
      );

      if (response.status === 200) {
        const responseData = response.data;
        if (responseData.success) {
          return {
            success: true,
            data: responseData.data as FirecrawlDocument<any>[],
            warning: responseData.warning,
          };
        } else {
          throw new FirecrawlError(`Failed to search. Error: ${responseData.error}`, response.status);
        }
      } else {
        this.handleError(response, "search");
      }
    } catch (error: any) {
      if (error.response?.data?.error) {
        throw new FirecrawlError(`Request failed with status code ${error.response.status}. Error: ${error.response.data.error} ${error.response.data.details ? ` - ${JSON.stringify(error.response.data.details)}` : ''}`, error.response.status);
      } else {
        throw new FirecrawlError(error.message, 500);
      }
    }
    return { success: false, error: "Internal server error.", data: [] };
  }

  /**
   * Initiates a crawl job for a URL using the Firecrawl API.
   * @param url - The URL to crawl.
   * @param params - Additional parameters for the crawl request.
   * @param pollInterval - Time in seconds for job status checks.
   * @param idempotencyKey - Optional idempotency key for the request.
   * @returns The response from the crawl operation.
   */
  async crawlUrl(
    url: string,
    params?: CrawlParams,
    pollInterval: number = 2,
    idempotencyKey?: string
  ): Promise<CrawlStatusResponse | ErrorResponse> {
    const headers = this.prepareHeaders(idempotencyKey);
    let jsonData: any = { url, ...params };
    try {
      const response: AxiosResponse = await this.postRequest(
        this.apiUrl + `/v1/crawl`,
        jsonData,
        headers
      );
      if (response.status === 200) {
        const id: string = response.data.id;
        return this.monitorJobStatus(id, headers, pollInterval);
      } else {
        this.handleError(response, "start crawl job");
      }
    } catch (error: any) {
      if (error.response?.data?.error) {
        throw new FirecrawlError(`Request failed with status code ${error.response.status}. Error: ${error.response.data.error} ${error.response.data.details ? ` - ${JSON.stringify(error.response.data.details)}` : ''}`, error.response.status);
      } else {
        throw new FirecrawlError(error.message, 500);
      }
    }
    return { success: false, error: "Internal server error." };
  }

  async asyncCrawlUrl(
    url: string,
    params?: CrawlParams,
    idempotencyKey?: string
  ): Promise<CrawlResponse | ErrorResponse> {
    const headers = this.prepareHeaders(idempotencyKey);
    let jsonData: any = { url, ...params };
    try {
      const response: AxiosResponse = await this.postRequest(
        this.apiUrl + `/v1/crawl`,
        jsonData,
        headers
      );
      if (response.status === 200) {
        return response.data;
      } else {
        this.handleError(response, "start crawl job");
      }
    } catch (error: any) {
      if (error.response?.data?.error) {
        throw new FirecrawlError(`Request failed with status code ${error.response.status}. Error: ${error.response.data.error} ${error.response.data.details ? ` - ${JSON.stringify(error.response.data.details)}` : ''}`, error.response.status);
      } else {
        throw new FirecrawlError(error.message, 500);
      }
    }
    return { success: false, error: "Internal server error." };
  }

  /**
   * Checks the status of a crawl job using the Firecrawl API.
   * @param id - The ID of the crawl operation.
   * @param getAllData - Paginate through all the pages of documents, returning the full list of all documents. (default: `false`)
   * @returns The response containing the job status.
   */
  async checkCrawlStatus(id?: string, getAllData = false): Promise<CrawlStatusResponse | ErrorResponse> {
    if (!id) {
      throw new FirecrawlError("No crawl ID provided", 400);
    }

    const headers: AxiosRequestHeaders = this.prepareHeaders();
    try {
      const response: AxiosResponse = await this.getRequest(
        `${this.apiUrl}/v1/crawl/${id}`,
        headers
      );
      if (response.status === 200) {
        let allData = response.data.data;
        if (getAllData && response.data.status === "completed") {
          let statusData = response.data
          if ("data" in statusData) {
            let data = statusData.data;
            while (typeof statusData === 'object' && 'next' in statusData) {
              if (data.length === 0) {
                break
              }
              statusData = (await this.getRequest(statusData.next, headers)).data;
              data = data.concat(statusData.data);
            }
            allData = data;
          }
        }

        let resp: CrawlStatusResponse | ErrorResponse = {
          success: response.data.success,
          status: response.data.status,
          total: response.data.total,
          completed: response.data.completed,
          creditsUsed: response.data.creditsUsed,
          expiresAt: new Date(response.data.expiresAt),
          data: allData
        }

        if (!response.data.success && response.data.error) {
          resp = {
            ...resp,
            success: false,
            error: response.data.error
          } as ErrorResponse;
        }

        if (response.data.next) {
          (resp as CrawlStatusResponse).next = response.data.next;
        }
        
        return resp;
      } else {
        this.handleError(response, "check crawl status");
      }
    } catch (error: any) {
      throw new FirecrawlError(error.message, 500);
    }
    return { success: false, error: "Internal server error." };
  }

  /**
   * Cancels a crawl job using the Firecrawl API.
   * @param id - The ID of the crawl operation.
   * @returns The response from the cancel crawl operation.
   */
  async cancelCrawl(id: string): Promise<ErrorResponse> {
    const headers = this.prepareHeaders();
    try {
      const response: AxiosResponse = await this.deleteRequest(
        `${this.apiUrl}/v1/crawl/${id}`,
        headers
      );
      if (response.status === 200) {
        return response.data;
      } else {
        this.handleError(response, "cancel crawl job");
      }
    } catch (error: any) {
      throw new FirecrawlError(error.message, 500);
    }
    return { success: false, error: "Internal server error." };
  }

  /**
   * Initiates a crawl job and returns a CrawlWatcher to monitor the job via WebSocket.
   * @param url - The URL to crawl.
   * @param params - Additional parameters for the crawl request.
   * @param idempotencyKey - Optional idempotency key for the request.
   * @returns A CrawlWatcher instance to monitor the crawl job.
   */
  async crawlUrlAndWatch(
    url: string,
    params?: CrawlParams,
    idempotencyKey?: string,
  ) {
    const crawl = await this.asyncCrawlUrl(url, params, idempotencyKey);

    if (crawl.success && crawl.id) {
      const id = crawl.id;
      return new CrawlWatcher(id, this);
    }

    throw new FirecrawlError("Crawl job failed to start", 400);
  }

  /**
   * Maps a URL using the Firecrawl API.
   * @param url - The URL to map.
   * @param params - Additional parameters for the map request.
   * @returns The response from the map operation.
   */
  async mapUrl(url: string, params?: MapParams): Promise<MapResponse | ErrorResponse> {
    const headers = this.prepareHeaders();
    let jsonData: { url: string } & MapParams = { url, ...params };

    try {
      const response: AxiosResponse = await this.postRequest(
        this.apiUrl + `/v1/map`,
        jsonData,
        headers
      );
      if (response.status === 200) {
        return response.data as MapResponse;
      } else {
        this.handleError(response, "map");
      }
    } catch (error: any) {
      throw new FirecrawlError(error.message, 500);
    }
    return { success: false, error: "Internal server error." };
  }

  /**
   * Initiates a batch scrape job for multiple URLs using the Firecrawl API.
   * @param url - The URLs to scrape.
   * @param params - Additional parameters for the scrape request.
   * @param pollInterval - Time in seconds for job status checks.
   * @param idempotencyKey - Optional idempotency key for the request.
   * @param webhook - Optional webhook for the batch scrape.
   * @returns The response from the crawl operation.
   */
  async batchScrapeUrls(
    urls: string[],
    params?: ScrapeParams,
    pollInterval: number = 2,
    idempotencyKey?: string,
    webhook?: CrawlParams["webhook"],
    ignoreInvalidURLs?: boolean,
  ): Promise<BatchScrapeStatusResponse | ErrorResponse> {
    const headers = this.prepareHeaders(idempotencyKey);
    let jsonData: any = { urls, webhook, ignoreInvalidURLs, ...params };
    if (jsonData?.extract?.schema) {
      let schema = jsonData.extract.schema;

      // Try parsing the schema as a Zod schema
      try {
        schema = zodToJsonSchema(schema);
      } catch (error) {
        
      }
      jsonData = {
        ...jsonData,
        extract: {
          ...jsonData.extract,
          schema: schema,
        },
      };
    }
    try {
      const response: AxiosResponse = await this.postRequest(
        this.apiUrl + `/v1/batch/scrape`,
        jsonData,
        headers
      );
      if (response.status === 200) {
        const id: string = response.data.id;
        return this.monitorJobStatus(id, headers, pollInterval);
      } else {
        this.handleError(response, "start batch scrape job");
      }
    } catch (error: any) {
      if (error.response?.data?.error) {
        throw new FirecrawlError(`Request failed with status code ${error.response.status}. Error: ${error.response.data.error} ${error.response.data.details ? ` - ${JSON.stringify(error.response.data.details)}` : ''}`, error.response.status);
      } else {
        throw new FirecrawlError(error.message, 500);
      }
    }
    return { success: false, error: "Internal server error." };
  }

  async asyncBatchScrapeUrls(
    urls: string[],
    params?: ScrapeParams,
    idempotencyKey?: string,
    webhook?: CrawlParams["webhook"],
    ignoreInvalidURLs?: boolean,
  ): Promise<BatchScrapeResponse | ErrorResponse> {
    const headers = this.prepareHeaders(idempotencyKey);
    let jsonData: any = { urls, webhook, ignoreInvalidURLs, ...(params ?? {}) };
    try {
      const response: AxiosResponse = await this.postRequest(
        this.apiUrl + `/v1/batch/scrape`,
        jsonData,
        headers
      );
      if (response.status === 200) {
        return response.data;
      } else {
        this.handleError(response, "start batch scrape job");
      }
    } catch (error: any) {
      if (error.response?.data?.error) {
        throw new FirecrawlError(`Request failed with status code ${error.response.status}. Error: ${error.response.data.error} ${error.response.data.details ? ` - ${JSON.stringify(error.response.data.details)}` : ''}`, error.response.status);
      } else {
        throw new FirecrawlError(error.message, 500);
      }
    }
    return { success: false, error: "Internal server error." };
  }

  /**
   * Initiates a batch scrape job and returns a CrawlWatcher to monitor the job via WebSocket.
   * @param urls - The URL to scrape.
   * @param params - Additional parameters for the scrape request.
   * @param idempotencyKey - Optional idempotency key for the request.
   * @returns A CrawlWatcher instance to monitor the crawl job.
   */
  async batchScrapeUrlsAndWatch(
    urls: string[],
    params?: ScrapeParams,
    idempotencyKey?: string,
    webhook?: CrawlParams["webhook"],
    ignoreInvalidURLs?: boolean,
  ) {
    const crawl = await this.asyncBatchScrapeUrls(urls, params, idempotencyKey, webhook, ignoreInvalidURLs);

    if (crawl.success && crawl.id) {
      const id = crawl.id;
      return new CrawlWatcher(id, this);
    }

    throw new FirecrawlError("Batch scrape job failed to start", 400);
  }

  /**
   * Checks the status of a batch scrape job using the Firecrawl API.
   * @param id - The ID of the batch scrape operation.
   * @param getAllData - Paginate through all the pages of documents, returning the full list of all documents. (default: `false`)
   * @returns The response containing the job status.
   */
  async checkBatchScrapeStatus(id?: string, getAllData = false): Promise<BatchScrapeStatusResponse | ErrorResponse> {
    if (!id) {
      throw new FirecrawlError("No batch scrape ID provided", 400);
    }

    const headers: AxiosRequestHeaders = this.prepareHeaders();
    try {
      const response: AxiosResponse = await this.getRequest(
        `${this.apiUrl}/v1/batch/scrape/${id}`,
        headers
      );
      if (response.status === 200) {
        let allData = response.data.data;
        if (getAllData && response.data.status === "completed") {
          let statusData = response.data
          if ("data" in statusData) {
            let data = statusData.data;
            while (typeof statusData === 'object' && 'next' in statusData) {
              if (data.length === 0) {
                break
              }
              statusData = (await this.getRequest(statusData.next, headers)).data;
              data = data.concat(statusData.data);
            }
            allData = data;
          }
        }

        let resp: BatchScrapeStatusResponse | ErrorResponse = {
          success: response.data.success,
          status: response.data.status,
          total: response.data.total,
          completed: response.data.completed,
          creditsUsed: response.data.creditsUsed,
          expiresAt: new Date(response.data.expiresAt),
          data: allData
        }

        if (!response.data.success && response.data.error) {
          resp = {
            ...resp,
            success: false,
            error: response.data.error
          } as ErrorResponse;
        }

        if (response.data.next) {
          (resp as BatchScrapeStatusResponse).next = response.data.next;
        }
        
        return resp;
      } else {
        this.handleError(response, "check batch scrape status");
      }
    } catch (error: any) {
      throw new FirecrawlError(error.message, 500);
    }
    return { success: false, error: "Internal server error." };
  }

  /**
   * Extracts information from URLs using the Firecrawl API.
   * Currently in Beta. Expect breaking changes on future minor versions.
   * @param url - The URL to extract information from.
   * @param params - Additional parameters for the extract request.
   * @returns The response from the extract operation.
   */
  async extract<T extends zt.ZodSchema = any>(urls: string[], params?: ExtractParams<T>): Promise<ExtractResponse<zt.infer<T>> | ErrorResponse> {
    const headers = this.prepareHeaders();

    let jsonData: { urls: string[] } & ExtractParams<T> = { urls,  ...params };
    let jsonSchema: any;
    try {
      if (!params?.schema) {
        jsonSchema = undefined;
      } else if (params.schema instanceof zt.ZodType) {
        jsonSchema = zodToJsonSchema(params.schema);
      } else {
        jsonSchema = params.schema;
      }
    } catch (error: any) {
      throw new FirecrawlError("Invalid schema. Schema must be either a valid Zod schema or JSON schema object.", 400);
    }

    try {
      const response: AxiosResponse = await this.postRequest(
        this.apiUrl + `/v1/extract`,
        { ...jsonData, schema: jsonSchema },
        headers
      );
      if (response.status === 200) {
        const responseData = response.data as ExtractResponse<T>;
        if (responseData.success) {
          return {
            success: true,
            data: responseData.data,
            warning: responseData.warning,
            error: responseData.error
          };
        } else {
          throw new FirecrawlError(`Failed to scrape URL. Error: ${responseData.error}`, response.status);
        }
      } else {
        this.handleError(response, "extract");
      }
    } catch (error: any) {
      throw new FirecrawlError(error.message, 500);
    }
    return { success: false, error: "Internal server error." };
  }

  /**
   * Prepares the headers for an API request.
   * @param idempotencyKey - Optional key to ensure idempotency.
   * @returns The prepared headers.
   */
  prepareHeaders(idempotencyKey?: string): AxiosRequestHeaders {
    return {
      "Content-Type": "application/json",
      Authorization: `Bearer ${this.apiKey}`,
      ...(idempotencyKey ? { "x-idempotency-key": idempotencyKey } : {}),
    } as AxiosRequestHeaders & { "x-idempotency-key"?: string };
  }

  /**
   * Sends a POST request to the specified URL.
   * @param url - The URL to send the request to.
   * @param data - The data to send in the request.
   * @param headers - The headers for the request.
   * @returns The response from the POST request.
   */
  postRequest(
    url: string,
    data: any,
    headers: AxiosRequestHeaders
  ): Promise<AxiosResponse> {
    return axios.post(url, data, { headers });
  }

  /**
   * Sends a GET request to the specified URL.
   * @param url - The URL to send the request to.
   * @param headers - The headers for the request.
   * @returns The response from the GET request.
   */
  async getRequest(
    url: string,
    headers: AxiosRequestHeaders
  ): Promise<AxiosResponse> {
    try {
      return await axios.get(url, { headers });
    } catch (error) {
      if (error instanceof AxiosError && error.response) {
        return error.response as AxiosResponse;
      } else {
        throw error;
      }
    }
  }

  /**
   * Sends a DELETE request to the specified URL.
   * @param url - The URL to send the request to.
   * @param headers - The headers for the request.
   * @returns The response from the DELETE request.
   */
  async deleteRequest(
    url: string,
    headers: AxiosRequestHeaders
  ): Promise<AxiosResponse> {
    try {
        return await axios.delete(url, { headers });
    } catch (error) {
      if (error instanceof AxiosError && error.response) {
        return error.response as AxiosResponse;
      } else {
        throw error;
      }
    }
  }

  /**
   * Monitors the status of a crawl job until completion or failure.
   * @param id - The ID of the crawl operation.
   * @param headers - The headers for the request.
   * @param checkInterval - Interval in seconds for job status checks.
   * @param checkUrl - Optional URL to check the status (used for v1 API)
   * @returns The final job status or data.
   */
  async monitorJobStatus(
    id: string,
    headers: AxiosRequestHeaders,
    checkInterval: number
  ): Promise<CrawlStatusResponse | ErrorResponse> {
    try {
      while (true) {
        let statusResponse: AxiosResponse = await this.getRequest(
          `${this.apiUrl}/v1/crawl/${id}`,
          headers
        );
        if (statusResponse.status === 200) {
          let statusData = statusResponse.data;
            if (statusData.status === "completed") {
              if ("data" in statusData) {
                let data = statusData.data;
                while (typeof statusData === 'object' && 'next' in statusData) {
                  if (data.length === 0) {
                    break
                  }
                  statusResponse = await this.getRequest(statusData.next, headers);
                  statusData = statusResponse.data;
                  data = data.concat(statusData.data);
                }
                statusData.data = data;
                return statusData;
              } else {
                throw new FirecrawlError("Crawl job completed but no data was returned", 500);
              }
            } else if (
            ["active", "paused", "pending", "queued", "waiting", "scraping"].includes(statusData.status)
          ) {
            checkInterval = Math.max(checkInterval, 2);
            await new Promise((resolve) =>
              setTimeout(resolve, checkInterval * 1000)
            );
          } else {
            throw new FirecrawlError(
              `Crawl job failed or was stopped. Status: ${statusData.status}`,
              500
            );
          }
        } else {
          this.handleError(statusResponse, "check crawl status");
        }
      }
    } catch (error: any) {
      throw new FirecrawlError(error, 500);
    }
  }

  /**
   * Handles errors from API responses.
   * @param {AxiosResponse} response - The response from the API.
   * @param {string} action - The action being performed when the error occurred.
   */
  handleError(response: AxiosResponse, action: string): void {
    if ([402, 408, 409, 500].includes(response.status)) {
      const errorMessage: string =
        response.data.error || "Unknown error occurred";
      throw new FirecrawlError(
        `Failed to ${action}. Status code: ${response.status}. Error: ${errorMessage}`,
        response.status
      );
    } else {
      throw new FirecrawlError(
        `Unexpected error occurred while trying to ${action}. Status code: ${response.status}`,
        response.status
      );
    }
  }
}

interface CrawlWatcherEvents {
  document: CustomEvent<FirecrawlDocument<undefined>>,
  done: CustomEvent<{
    status: CrawlStatusResponse["status"];
    data: FirecrawlDocument<undefined>[];
  }>,
  error: CustomEvent<{
    status: CrawlStatusResponse["status"],
    data: FirecrawlDocument<undefined>[],
    error: string,
  }>,
}

export class CrawlWatcher extends TypedEventTarget<CrawlWatcherEvents> {
  private ws: WebSocket;
  public data: FirecrawlDocument<undefined>[];
  public status: CrawlStatusResponse["status"];
  public id: string;

  constructor(id: string, app: FirecrawlApp) {
    super();
    this.id = id;
    this.ws = new WebSocket(`${app.apiUrl}/v1/crawl/${id}`, app.apiKey);
    this.status = "scraping";
    this.data = [];

    type ErrorMessage = {
      type: "error",
      error: string,
    }
    
    type CatchupMessage = {
      type: "catchup",
      data: CrawlStatusResponse,
    }
    
    type DocumentMessage = {
      type: "document",
      data: FirecrawlDocument<undefined>,
    }
    
    type DoneMessage = { type: "done" }
    
    type Message = ErrorMessage | CatchupMessage | DoneMessage | DocumentMessage;

    const messageHandler = (msg: Message) => {
      if (msg.type === "done") {
        this.status = "completed";
        this.dispatchTypedEvent("done", new CustomEvent("done", {
          detail: {
            status: this.status,
            data: this.data,
            id: this.id,
          },
        }));
      } else if (msg.type === "error") {
        this.status = "failed";
        this.dispatchTypedEvent("error", new CustomEvent("error", {
          detail: {
            status: this.status,
            data: this.data,
            error: msg.error,
            id: this.id,
          },
        }));
      } else if (msg.type === "catchup") {
        this.status = msg.data.status;
        this.data.push(...(msg.data.data ?? []));
        for (const doc of this.data) {
          this.dispatchTypedEvent("document", new CustomEvent("document", {
            detail: {
              ...doc,
              id: this.id,
            },
          }));
        }
      } else if (msg.type === "document") {
        this.dispatchTypedEvent("document", new CustomEvent("document", {
          detail: {
            ...msg.data,
            id: this.id,
          },
        }));
      }
    }

    this.ws.onmessage = ((ev: MessageEvent) => {
      if (typeof ev.data !== "string") {
        this.ws.close();
        return;
      }
      try {
        const msg = JSON.parse(ev.data) as Message;
        messageHandler(msg);
      } catch (error) {
        console.error("Error on message", error);
      }
    }).bind(this);

    this.ws.onclose = ((ev: CloseEvent) => {
      try {
        const msg = JSON.parse(ev.reason) as Message;
        messageHandler(msg);
      } catch (error) {
        console.error("Error on close", error);
      }
    }).bind(this);

    this.ws.onerror = ((_: Event) => {
      this.status = "failed"
      this.dispatchTypedEvent("error", new CustomEvent("error", {
        detail: {
          status: this.status,
          data: this.data,
          error: "WebSocket error",
          id: this.id,
        },
      }));
    }).bind(this);
  }

  close() {
    this.ws.close();
  }
}
