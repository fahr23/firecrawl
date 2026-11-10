import amqp from "amqplib";
import { config } from "../config";
import { logger as _logger } from "../lib/logger";

const EXTRACT_QUEUE = "extract.jobs";
const EXTRACT_DLX = "extract.dlx";
const EXTRACT_DLQ = "extract.dlq";

export type ExtractJobData = {
  extractId: string;
  request: any;
  teamId: string;
  apiKeyId?: number | null;
  agent?: any;
  createdAt: number;
};

let connection: amqp.ChannelModel | null = null;
let channel: amqp.Channel | null = null;
let connecting: Promise<amqp.Channel> | null = null;
let shuttingDown = false;

async function openChannel(): Promise<amqp.Channel> {
  const url = config.NUQ_RABBITMQ_URL;
  if (!url) {
    throw new Error("NUQ_RABBITMQ_URL is not configured");
  }

  const conn = await amqp.connect(url);

  conn.on("close", () => {
    _logger.warn("Extract queue connection closed");
    if (connection === conn) {
      connection = null;
      channel = null;
    }
  });

  conn.on("error", err => {
    _logger.error("Extract queue connection error", { error: err });
  });

  try {
    const ch = await conn.createChannel();

    ch.on("error", err => {
      _logger.error("Extract queue channel error", { error: err });
    });

    // Set up the dead letter exchange
    await ch.assertExchange(EXTRACT_DLX, "direct", { durable: true });

    // Set up the dead letter queue
    await ch.assertQueue(EXTRACT_DLQ, {
      durable: true,
      arguments: {
        "x-queue-type": "quorum",
      },
    });
    await ch.bindQueue(EXTRACT_DLQ, EXTRACT_DLX, EXTRACT_QUEUE);

    // Set up the main queue with DLX - no retries (messages go straight to DLQ on reject/crash)
    await ch.assertQueue(EXTRACT_QUEUE, {
      durable: true,
      arguments: {
        "x-queue-type": "quorum",
        "x-dead-letter-exchange": EXTRACT_DLX,
        "x-dead-letter-routing-key": EXTRACT_QUEUE,
        "x-delivery-limit": 1,
      },
    });

    connection = conn;
    channel = ch;
    return ch;
  } catch (error) {
    await conn.close().catch(() => undefined);
    throw error;
  }
}

async function getChannel(): Promise<amqp.Channel> {
  if (channel) return channel;

  // Concurrent callers share one attempt, so they all end up on one connection.
  connecting ??= openChannel().finally(() => {
    connecting = null;
  });
  return connecting;
}

// Once the channel is gone the broker redelivers the message itself. Throwing
// here would become an unhandled rejection and take down the whole API pod.
function settleMessage(action: () => void, logger: typeof _logger) {
  try {
    action();
  } catch (error) {
    logger.warn("Could not settle extract message", { error });
  }
}

/**
 * Runs `startConsumers` and keeps it running: connection failures are retried
 * with backoff, and consumers are registered again after a lost connection.
 * Only returns once the queue is shut down.
 */
export async function keepConsumingExtractQueues(
  startConsumers: () => Promise<void>,
  { baseDelayMs = 1_000, maxDelayMs = 30_000 } = {},
): Promise<void> {
  if (!config.NUQ_RABBITMQ_URL) {
    throw new Error("NUQ_RABBITMQ_URL is not configured");
  }

  let failures = 0;

  while (!shuttingDown) {
    try {
      await startConsumers();
      failures = 0;

      const activeConnection = connection;
      if (activeConnection) {
        await new Promise<void>(resolve => {
          activeConnection.once("close", () => resolve());
        });
      }
    } catch (error) {
      failures++;
      _logger.warn("Could not start extract consumers, retrying", {
        error,
        failures,
      });
      // Start clean, so a partial start can't leave duplicate consumers behind.
      await connection?.close().catch(() => undefined);
    }

    if (shuttingDown) return;

    const delayMs = Math.min(
      baseDelayMs * 2 ** Math.max(failures - 1, 0),
      maxDelayMs,
    );
    await new Promise(resolve => setTimeout(resolve, delayMs));
  }
}

export async function addExtractJob(
  extractId: string,
  data: ExtractJobData,
): Promise<void> {
  const ch = await getChannel();
  ch.sendToQueue(EXTRACT_QUEUE, Buffer.from(JSON.stringify(data)), {
    persistent: true,
    messageId: extractId,
  });
  _logger.info("Extract job added to queue", { extractId });
}

export async function consumeExtractJobs(
  handler: (
    data: ExtractJobData,
    ack: () => void,
    nack: () => void,
  ) => Promise<void>,
): Promise<void> {
  const ch = await getChannel();
  await ch.prefetch(1);

  await ch.consume(
    EXTRACT_QUEUE,
    async msg => {
      if (!msg) return;

      const data = JSON.parse(msg.content.toString()) as ExtractJobData;
      const logger = _logger.child({
        module: "extract-queue",
        extractId: data.extractId,
      });

      logger.info("Processing extract job");

      try {
        await handler(
          data,
          () => settleMessage(() => ch.ack(msg), logger),
          // Don't requeue - send to DLX
          () => settleMessage(() => ch.nack(msg, false, false), logger),
        );
      } catch (error) {
        logger.error("Extract job handler threw an error", { error });
        // Don't requeue - send to DLX
        settleMessage(() => ch.nack(msg, false, false), logger);
      }
    },
    { noAck: false },
  );

  _logger.info("Started consuming extract jobs");
}

export async function consumeExtractDLQ(
  handler: (data: ExtractJobData) => Promise<void>,
): Promise<void> {
  const ch = await getChannel();
  await ch.prefetch(1);

  await ch.consume(
    EXTRACT_DLQ,
    async msg => {
      if (!msg) return;

      const data = JSON.parse(msg.content.toString()) as ExtractJobData;
      const logger = _logger.child({
        module: "extract-dlq",
        extractId: data.extractId,
      });

      logger.info("Processing dead-lettered extract job");

      try {
        await handler(data);
        settleMessage(() => ch.ack(msg), logger);
      } catch (error) {
        logger.error("DLQ handler threw an error, requeueing", { error });
        // Requeue DLQ messages on error so we don't lose them
        settleMessage(() => ch.nack(msg, false, true), logger);
      }
    },
    { noAck: false },
  );

  _logger.info("Started consuming extract DLQ");
}

export async function shutdownExtractQueue(): Promise<void> {
  shuttingDown = true;
  if (channel) {
    await channel.close();
    channel = null;
  }
  if (connection) {
    await connection.close();
    connection = null;
  }
}
