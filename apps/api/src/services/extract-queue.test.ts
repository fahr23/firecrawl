import { EventEmitter } from "node:events";

const { connect, mockConfig } = vi.hoisted(() => ({
  connect: vi.fn(),
  mockConfig: {
    NUQ_RABBITMQ_URL: "amqp://rabbitmq:5672" as string | undefined,
  },
}));

vi.mock("amqplib", () => ({ default: { connect } }));
vi.mock("../config", () => ({ config: mockConfig }));
vi.mock("../lib/logger", () => {
  const logger = {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    child: () => logger,
  };
  return { logger };
});

function fakeChannel() {
  return Object.assign(new EventEmitter(), {
    assertExchange: vi.fn().mockResolvedValue(undefined),
    assertQueue: vi.fn().mockResolvedValue(undefined),
    bindQueue: vi.fn().mockResolvedValue(undefined),
    prefetch: vi.fn().mockResolvedValue(undefined),
    consume: vi.fn().mockResolvedValue(undefined),
    close: vi.fn().mockResolvedValue(undefined),
    ack: vi.fn(),
    nack: vi.fn(),
  });
}

function fakeConnection(channel = fakeChannel()) {
  const connection = Object.assign(new EventEmitter(), {
    channel,
    createChannel: vi.fn().mockResolvedValue(channel),
    close: vi.fn(async () => {
      connection.emit("close");
    }),
  });
  return connection;
}

const noBackoff = { baseDelayMs: 1, maxDelayMs: 1 };

async function loadQueue() {
  vi.resetModules();
  return await import("./extract-queue.js");
}

describe("extract queue RabbitMQ resilience", () => {
  beforeEach(() => {
    connect.mockReset();
    mockConfig.NUQ_RABBITMQ_URL = "amqp://rabbitmq:5672";
  });

  it("keeps retrying until RabbitMQ accepts the connection", async () => {
    const connection = fakeConnection();
    connect
      .mockRejectedValueOnce(new Error("connect ECONNREFUSED"))
      .mockRejectedValueOnce(new Error("connect ECONNREFUSED"))
      .mockResolvedValue(connection);
    const queue = await loadQueue();

    const running = queue.keepConsumingExtractQueues(
      () => queue.consumeExtractDLQ(async () => undefined),
      noBackoff,
    );

    await vi.waitFor(() =>
      expect(connection.channel.consume).toHaveBeenCalled(),
    );
    expect(connect).toHaveBeenCalledTimes(3);

    await queue.shutdownExtractQueue();
    await running;
  });

  it("registers consumers again after the connection is lost", async () => {
    const first = fakeConnection();
    const second = fakeConnection();
    connect.mockResolvedValueOnce(first).mockResolvedValueOnce(second);
    const queue = await loadQueue();

    const running = queue.keepConsumingExtractQueues(
      () => queue.consumeExtractDLQ(async () => undefined),
      noBackoff,
    );
    await vi.waitFor(() => expect(first.channel.consume).toHaveBeenCalled());

    first.emit("close");

    await vi.waitFor(() => expect(second.channel.consume).toHaveBeenCalled());
    await queue.shutdownExtractQueue();
    await running;
  });

  it("shares one connection between consumers that start together", async () => {
    const connection = fakeConnection();
    connect.mockResolvedValue(connection);
    const queue = await loadQueue();

    await Promise.all([
      queue.consumeExtractJobs(async () => undefined),
      queue.consumeExtractDLQ(async () => undefined),
    ]);

    expect(connect).toHaveBeenCalledTimes(1);
    expect(connection.channel.consume).toHaveBeenCalledTimes(2);
  });

  it("drops the connection after a partial start so consumers can't double up", async () => {
    const broken = fakeConnection();
    broken.channel.consume.mockRejectedValueOnce(new Error("channel closed"));
    const healthy = fakeConnection();
    connect.mockResolvedValueOnce(broken).mockResolvedValueOnce(healthy);
    const queue = await loadQueue();

    const running = queue.keepConsumingExtractQueues(
      () => queue.consumeExtractDLQ(async () => undefined),
      noBackoff,
    );

    await vi.waitFor(() => expect(healthy.channel.consume).toHaveBeenCalled());
    expect(broken.close).toHaveBeenCalled();

    await queue.shutdownExtractQueue();
    await running;
  });

  it("does not throw when a job settles after its channel has closed", async () => {
    const connection = fakeConnection();
    connection.channel.ack.mockImplementation(() => {
      throw new Error("Channel closed");
    });
    connect.mockResolvedValue(connection);
    const queue = await loadQueue();

    await queue.consumeExtractJobs(async (_data, ack) => ack());
    const onMessage = connection.channel.consume.mock.calls[0][1];

    await expect(
      onMessage({
        content: Buffer.from(JSON.stringify({ extractId: "extract-1" })),
      }),
    ).resolves.toBeUndefined();
    expect(connection.channel.ack).toHaveBeenCalled();
  });

  it("fails immediately when RabbitMQ is not configured", async () => {
    mockConfig.NUQ_RABBITMQ_URL = undefined;
    const queue = await loadQueue();
    const startConsumers = vi.fn();

    await expect(
      queue.keepConsumingExtractQueues(startConsumers, noBackoff),
    ).rejects.toThrow("NUQ_RABBITMQ_URL is not configured");
    expect(startConsumers).not.toHaveBeenCalled();
  });
});
