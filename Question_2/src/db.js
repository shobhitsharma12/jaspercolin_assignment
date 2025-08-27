import mongoose from "mongoose";

export async function connect(uri) {
  mongoose.set("strictQuery", true);
  await mongoose.connect(uri, {
    // tune pool for your throughput needs
    maxPoolSize: 20,
    minPoolSize: 5
  });
  return mongoose.connection;
}

export function startSession() {
  return mongoose.startSession();
}
