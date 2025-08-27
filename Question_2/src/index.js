import express from "express";
import pino from "pino";
import pinoHttp from "pino-http";
import { connect, startSession } from "./db.js";
import { Order, OrderItem, OutboxEvent } from "./models.js";
import { validateBody, createOrderSchema } from "./validation.js";

const PORT = process.env.PORT || 3000;
const MONGO_URI = process.env.MONGO_URI;
const logger = pino({ level: process.env.LOG_LEVEL || "info" });

const app = express();
app.use(express.json());
app.use(pinoHttp({ logger }));

app.get("/health", (_req, res) => res.json({ status: "ok" }));

/**
 * Create Order (atomic):
 * - Begin MongoDB transaction (session).
 * - Compute totals.
 * - Insert Order + OrderItems + OutboxEvent(ORDER_CREATED) in the SAME transaction.
 * - Commit or abort => all-or-nothing.
 */
app.post("/orders", validateBody(createOrderSchema), async (req, res) => {
  const session = await startSession();
  session.startTransaction();

  try {
    const { customerId, currency, items } = req.validated;

    // compute totals
    const itemsWithTotals = items.map(i => ({
      ...i,
      lineTotal: Math.round((i.unitPrice * i.quantity) * 100) / 100
    }));
    const grandTotal = Math.round(itemsWithTotals.reduce((s, i) => s + i.lineTotal, 0) * 100) / 100;

    // 1) create order
    const order = await Order.create(
      [{
        customerId,
        currency,
        status: "CONFIRMED",
        itemsSummary: itemsWithTotals.map(i => ({ sku: i.sku, quantity: i.quantity, lineTotal: i.lineTotal })),
        grandTotal
      }],
      { session }
    );

    const orderId = order[0]._id;

    // 2) create order items docs
    const itemsDocs = itemsWithTotals.map(i => ({
      orderId,
      sku: i.sku,
      name: i.name,
      unitPrice: i.unitPrice,
      quantity: i.quantity,
      lineTotal: i.lineTotal
    }));
    await OrderItem.insertMany(itemsDocs, { session });

    // 3) transactional outbox event
    await OutboxEvent.create(
      [{
        type: "ORDER_CREATED",
        aggregateId: String(orderId),
        payload: {
          orderId: String(orderId),
          customerId,
          currency,
          grandTotal,
          items: itemsWithTotals
        }
      }],
      { session }
    );

    await session.commitTransaction();
    session.endSession();

    req.log.info({ orderId }, "order created");
    return res.status(201).json({ orderId, grandTotal, currency, status: "CONFIRMED" });

  } catch (err) {
    await session.abortTransaction().catch(() => {});
    session.endSession();
    req.log.error({ err }, "order creation failed");
    return res.status(500).json({ error: "OrderCreationFailed" });
  }
});

app.get("/orders/:id", async (req, res) => {
  const order = await Order.findById(req.params.id).lean();
  if (!order) return res.status(404).json({ error: "NotFound" });
  const items = await OrderItem.find({ orderId: order._id }).lean();
  return res.json({ ...order, items });
});

connect(MONGO_URI)
  .then(() => {
    logger.info("Mongo connected");
    app.listen(PORT, () => logger.info(`orders-ms listening on :${PORT}`));
  })
  .catch(err => {
    logger.error({ err }, "Mongo connection failed");
    process.exit(1);
  });
