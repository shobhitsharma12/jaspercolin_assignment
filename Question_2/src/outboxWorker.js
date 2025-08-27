import pino from "pino";
import { connect } from "./db.js";
import { OutboxEvent } from "./models.js";

const logger = pino({ level: process.env.LOG_LEVEL || "info" });
const MONGO_URI = process.env.MONGO_URI;

async function publish(evt) {
  // TODO: replace this with Kafka/RabbitMQ/SNS producer call
  // Example: await kafkaProducer.send({ topic: evt.type, messages: [{ key: evt.aggregateId, value: JSON.stringify(evt.payload) }] });
  // Simulate success:
  return true;
}

async function run() {
  await connect(MONGO_URI);
  logger.info("Outbox worker started");

  // Simple polling loop; in prod, consider change streams or a job queue
  // Also consider backoff & concurrency control
  // NOTE: We process a handful per tick to avoid starvation
  const BATCH = 50;
  const INTERVAL_MS = 1000;

  setInterval(async () => {
    try {
      const events = await OutboxEvent.find({ status: "PENDING" }).sort({ createdAt: 1 }).limit(BATCH);
      for (const evt of events) {
        try {
          await publish(evt);
          await OutboxEvent.updateOne({ _id: evt._id, status: "PENDING" }, { $set: { status: "SENT", lastError: null } });
          logger.info({ id: String(evt._id), type: evt.type }, "outbox sent");
        } catch (err) {
          await OutboxEvent.updateOne({ _id: evt._id }, { $set: { status: "FAILED", lastError: String(err?.message || err) } });
          logger.error({ id: String(evt._id), err }, "outbox publish failed");
        }
      }
    } catch (err) {
      logger.error({ err }, "outbox tick failed");
    }
  }, INTERVAL_MS);
}

run().catch(err => {
  logger.error({ err }, "worker crashed");
  process.exit(1);
});
