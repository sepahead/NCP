import { constants, open } from "node:fs/promises";

export class SourceFileError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SourceFileError";
  }
}

export async function readBoundedRegularFile(
  url: string | URL,
  maximumBytes: number,
  label: string,
): Promise<Uint8Array> {
  if (!Number.isSafeInteger(maximumBytes) || maximumBytes <= 0) {
    throw new SourceFileError("file bound must be a positive safe integer");
  }
  let handle;
  try {
    handle = await open(url, constants.O_RDONLY | constants.O_NOFOLLOW);
  } catch (error) {
    throw new SourceFileError(`${label} cannot be opened without following links: ${errorText(error)}`);
  }
  try {
    const before = await handle.stat();
    if (!before.isFile()) {
      throw new SourceFileError(`${label} is not a regular file`);
    }
    if (before.size > maximumBytes) {
      throw new SourceFileError(`${label} exceeds ${maximumBytes} bytes`);
    }

    const allocation = new Uint8Array(maximumBytes + 1);
    let used = 0;
    while (used < allocation.byteLength) {
      const { bytesRead } = await handle.read(
        allocation,
        used,
        allocation.byteLength - used,
        used,
      );
      if (bytesRead === 0) break;
      used += bytesRead;
    }
    if (used > maximumBytes) {
      throw new SourceFileError(`${label} grew beyond ${maximumBytes} bytes while read`);
    }
    const after = await handle.stat();
    if (
      before.dev !== after.dev ||
      before.ino !== after.ino ||
      before.size !== after.size ||
      before.mtimeMs !== after.mtimeMs ||
      before.ctimeMs !== after.ctimeMs ||
      used !== after.size
    ) {
      throw new SourceFileError(`${label} changed while it was read`);
    }
    return allocation.slice(0, used);
  } finally {
    await handle.close();
  }
}

export function sha256(bytes: Uint8Array): string {
  const hasher = new Bun.CryptoHasher("sha256");
  hasher.update(bytes);
  return hasher.digest("hex");
}

export function extractExactJsonFences(markdownBytes: Uint8Array): Uint8Array[] {
  let markdown: string;
  try {
    markdown = new TextDecoder("utf-8", { fatal: true }).decode(markdownBytes);
  } catch {
    throw new SourceFileError("ADR Markdown is not valid UTF-8");
  }
  const expression = /^```json\n([\s\S]*?)\n```$/gm;
  const encoder = new TextEncoder();
  const fences: Uint8Array[] = [];
  for (const match of markdown.matchAll(expression)) {
    const content = match[1];
    if (content === undefined) {
      throw new SourceFileError("JSON fence extraction lost its content capture");
    }
    fences.push(encoder.encode(content));
  }
  return fences;
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "unknown file error";
}
