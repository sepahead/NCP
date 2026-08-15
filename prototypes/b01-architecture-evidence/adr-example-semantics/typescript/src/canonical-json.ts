import type { JsonValue } from "./strict-json.ts";

export class CanonicalJsonError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CanonicalJsonError";
  }
}

export function canonicalJsonText(value: JsonValue, maximumBytes?: number): string {
  const sink = new CanonicalTextSink(validateMaximum(maximumBytes));
  writeCanonical(value, sink);
  return sink.finish();
}

export function canonicalJsonBytes(value: JsonValue, maximumBytes?: number): Uint8Array {
  const maximum = validateMaximum(maximumBytes);
  const counter = new CanonicalByteCounter(maximum);
  writeCanonical(value, counter);

  const output = new Uint8Array(counter.byteLength);
  const sink = new CanonicalByteSink(output);
  writeCanonical(value, sink);
  sink.finish();
  return output;
}

interface CanonicalSink {
  append(fragment: string): void;
}

class CanonicalTextSink implements CanonicalSink {
  private output = "";
  private byteLength = 0;

  constructor(private readonly maximumBytes: number | undefined) {}

  append(fragment: string): void {
    this.byteLength = checkedByteLength(
      this.byteLength,
      utf8ByteLength(fragment),
      this.maximumBytes,
    );
    this.output += fragment;
  }

  finish(): string {
    return this.output;
  }
}

class CanonicalByteCounter implements CanonicalSink {
  byteLength = 0;

  constructor(private readonly maximumBytes: number | undefined) {}

  append(fragment: string): void {
    this.byteLength = checkedByteLength(
      this.byteLength,
      utf8ByteLength(fragment),
      this.maximumBytes,
    );
  }
}

class CanonicalByteSink implements CanonicalSink {
  private offset = 0;

  constructor(private readonly output: Uint8Array) {}

  append(fragment: string): void {
    this.offset = writeUtf8(fragment, this.output, this.offset);
  }

  finish(): void {
    if (this.offset !== this.output.byteLength) {
      throw new CanonicalJsonError("canonical JSON output length changed between passes");
    }
  }
}

function writeCanonical(value: JsonValue, sink: CanonicalSink): void {
  if (value === null) {
    sink.append("null");
    return;
  }
  if (typeof value === "boolean") {
    sink.append(value ? "true" : "false");
    return;
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value) || Object.is(value, -0)) {
      throw new CanonicalJsonError(
        "canonical JSON permits only safe integers other than negative zero",
      );
    }
    sink.append(String(value));
    return;
  }
  if (typeof value === "string") {
    writeString(value, sink);
    return;
  }
  if (Array.isArray(value)) {
    sink.append("[");
    value.forEach((entry, index) => {
      if (index !== 0) sink.append(",");
      writeCanonical(entry, sink);
    });
    sink.append("]");
    return;
  }

  const keys = Object.keys(value);
  for (const key of keys) assertUnicodeScalarString(key);
  keys.sort(compareUnicodeScalars);
  sink.append("{");
  keys.forEach((key, index) => {
    if (index !== 0) sink.append(",");
    writeString(key, sink);
    sink.append(":");
    writeCanonical(value[key] as JsonValue, sink);
  });
  sink.append("}");
}

function writeString(value: string, sink: CanonicalSink): void {
  assertUnicodeScalarString(value);
  const encoded = JSON.stringify(value);
  if (encoded === undefined) throw new CanonicalJsonError("string serialization failed");
  sink.append(encoded);
}

function validateMaximum(maximumBytes: number | undefined): number | undefined {
  if (
    maximumBytes !== undefined &&
    (!Number.isSafeInteger(maximumBytes) || maximumBytes <= 0)
  ) {
    throw new CanonicalJsonError("canonical JSON byte bound must be a positive safe integer");
  }
  return maximumBytes;
}

function checkedByteLength(
  current: number,
  additional: number,
  maximum: number | undefined,
): number {
  const next = current + additional;
  if (!Number.isSafeInteger(next) || (maximum !== undefined && next > maximum)) {
    throw new CanonicalJsonError(
      maximum === undefined
        ? "canonical JSON byte length is not a safe integer"
        : `canonical JSON exceeds ${maximum} UTF-8 bytes`,
    );
  }
  return next;
}

function utf8ByteLength(value: string): number {
  let bytes = 0;
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    if (codeUnit <= 0x7f) {
      bytes += 1;
    } else if (codeUnit <= 0x7ff) {
      bytes += 2;
    } else if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const low = value.charCodeAt(index + 1);
      if (!(low >= 0xdc00 && low <= 0xdfff)) {
        throw new CanonicalJsonError("canonical JSON string has an unpaired high surrogate");
      }
      bytes += 4;
      index += 1;
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      throw new CanonicalJsonError("canonical JSON string has an unpaired low surrogate");
    } else {
      bytes += 3;
    }
  }
  return bytes;
}

function writeUtf8(value: string, output: Uint8Array, start: number): number {
  const expectedEnd = start + utf8ByteLength(value);
  if (!Number.isSafeInteger(expectedEnd) || expectedEnd > output.byteLength) {
    throw new CanonicalJsonError("canonical JSON output allocation is too small");
  }
  let offset = start;
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    if (codeUnit <= 0x7f) {
      output[offset++] = codeUnit;
    } else if (codeUnit <= 0x7ff) {
      output[offset++] = 0xc0 | (codeUnit >> 6);
      output[offset++] = 0x80 | (codeUnit & 0x3f);
    } else if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const low = value.charCodeAt(index + 1);
      if (!(low >= 0xdc00 && low <= 0xdfff)) {
        throw new CanonicalJsonError("canonical JSON string has an unpaired high surrogate");
      }
      const scalar = 0x10000 + ((codeUnit - 0xd800) << 10) + (low - 0xdc00);
      output[offset++] = 0xf0 | (scalar >> 18);
      output[offset++] = 0x80 | ((scalar >> 12) & 0x3f);
      output[offset++] = 0x80 | ((scalar >> 6) & 0x3f);
      output[offset++] = 0x80 | (scalar & 0x3f);
      index += 1;
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      throw new CanonicalJsonError("canonical JSON string has an unpaired low surrogate");
    } else {
      output[offset++] = 0xe0 | (codeUnit >> 12);
      output[offset++] = 0x80 | ((codeUnit >> 6) & 0x3f);
      output[offset++] = 0x80 | (codeUnit & 0x3f);
    }
  }
  if (offset !== expectedEnd) {
    throw new CanonicalJsonError("canonical JSON UTF-8 length changed while writing");
  }
  return offset;
}

function compareUnicodeScalars(left: string, right: string): number {
  let leftIndex = 0;
  let rightIndex = 0;
  while (leftIndex < left.length && rightIndex < right.length) {
    const leftScalar = left.codePointAt(leftIndex);
    const rightScalar = right.codePointAt(rightIndex);
    if (leftScalar === undefined || rightScalar === undefined) {
      throw new CanonicalJsonError("canonical JSON key comparison failed");
    }
    if (leftScalar !== rightScalar) return leftScalar < rightScalar ? -1 : 1;
    leftIndex += leftScalar > 0xffff ? 2 : 1;
    rightIndex += rightScalar > 0xffff ? 2 : 1;
  }
  if (leftIndex === left.length && rightIndex === right.length) return 0;
  return leftIndex === left.length ? -1 : 1;
}

function assertUnicodeScalarString(value: string): void {
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const low = value.charCodeAt(index + 1);
      if (!(low >= 0xdc00 && low <= 0xdfff)) {
        throw new CanonicalJsonError("canonical JSON string has an unpaired high surrogate");
      }
      index += 1;
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      throw new CanonicalJsonError("canonical JSON string has an unpaired low surrogate");
    }
  }
}
