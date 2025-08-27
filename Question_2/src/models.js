import mongoose from "mongoose";

const { Schema, model } = mongoose;

export const OrderItemSchema = new Schema(
  {
    orderId: { type: Schema.Types.ObjectId, ref: "Order", index: true, required: true },
    sku: { type: String, required: true },
    name: { type: String, required: true },
    unitPrice: { type: Number, required: true, min: 0 },
    quantity: { type: Number, required: true, min: 1 },
    lineTotal: { type: Number, required: true, min: 0 }
  },
  { timestamps: true }
);

export const OrderSchema = new Schema(
  {
    customerId: { type: String, required: true, index: true },
    currency: { type: String, required: true, default: "INR" },
    status: { type: String, required: true, enum: ["PENDING", "CONFIRMED", "CANCELLED"], default: "PENDING" },
    itemsSummary: [
      {
        sku: String,
        quantity: Number,
        lineTotal: Number
      }
    ],
    grandTotal: { type: Number, required: true, min: 0 }
  },
  { timestamps: true }
);

export const OutboxEventSchema = new Schema(
  {
    type: { type: String, required: true },          // e.g., ORDER_CREATED
    aggregateId: { type: String, required: true },   // order _id
    payload: { type: Object, required: true },       // full event payload
    status: { type: String, enum: ["PENDING", "SENT", "FAILED"], default: "PENDING", index: true },
    lastError: { type: String }
  },
  { timestamps: true }
);

export const Order = model("Order", OrderSchema);
export const OrderItem = model("OrderItem", OrderItemSchema);
export const OutboxEvent = model("OutboxEvent", OutboxEventSchema);
