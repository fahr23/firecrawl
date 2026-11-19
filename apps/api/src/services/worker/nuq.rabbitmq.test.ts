const { connect, query } = vi.hoisted(() => ({
  connect: vi.fn(),
  query: vi.fn(),
}));

vi.mock("amqplib", () => ({ default: { connect } }));
vi.mock("pg", () => {
  class Pool {
    query = query;
    on = vi.fn();
  }
  return { Pool, default: { Pool } };
});
vi.mock("../../config", async importOriginal => {
  const actual = await importOriginal<typeof import("../../config")>();
  return {
    config: { ...actual.config, NUQ_RABBITMQ_URL: "amqp://rabbitmq:5672" },
  };
});

import { scrapeQueue } from "./nuq.js";

describe("NuQ worker while RabbitMQ is unavailable", () => {
  it("falls back to Postgres instead of throwing", async () => {
    connect.mockRejectedValue(new Error("connect ECONNREFUSED"));
    query.mockResolvedValue({ rows: [] });

    await expect(scrapeQueue.getJobToProcess()).resolves.toBeNull();
    expect(query).toHaveBeenCalled();
  });
});
