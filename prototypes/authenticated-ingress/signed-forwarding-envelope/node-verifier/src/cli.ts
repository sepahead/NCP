import { Buffer } from "node:buffer";
import { PrototypeError } from "./errors.js";
import { MAX_REQUEST_BYTES, verifyRequest } from "./verifier.js";

const RESPONSE_SCHEMA = "ncp.prototype.signed-forwarding-node-response.v1";

async function readBoundedStdin(): Promise<Buffer> {
  const chunks: Buffer[] = [];
  let length = 0;
  for await (const chunk of process.stdin) {
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    length += bytes.byteLength;
    if (length > MAX_REQUEST_BYTES) {
      throw new PrototypeError("bounds", "node verifier request exceeds the byte limit");
    }
    chunks.push(bytes);
  }
  return Buffer.concat(chunks, length);
}

async function main(): Promise<void> {
  try {
    const projection = verifyRequest(await readBoundedStdin());
    process.stdout.write(
      `${JSON.stringify({
        accepted: true,
        projection,
        schema: RESPONSE_SCHEMA,
      })}\n`,
    );
  } catch (error) {
    if (!(error instanceof PrototypeError)) throw error;
    process.stdout.write(
      `${JSON.stringify({
        accepted: false,
        error_code: error.code,
        schema: RESPONSE_SCHEMA,
      })}\n`,
    );
  }
}

await main();
