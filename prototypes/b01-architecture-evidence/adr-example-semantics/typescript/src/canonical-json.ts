import type { JsonValue } from "./strict-json.ts";

const encoder = new TextEncoder();

export class CanonicalJsonError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CanonicalJsonError";
  }
}

export function canonicalJsonText(value: JsonValue, maximumBytes?: number): string {
  const writer = new CanonicalWriter(maximumBytes);
  writer.write(value);
  return writer.finish();
}

export function canonicalJsonBytes(value: JsonValue, maximumBytes?: number): Uint8Array {
  return encoder.encode(canonicalJsonText(value, maximumBytes));
}

class CanonicalWriter {
  private readonly fragments: string[] = [];
  private byteLength = 0;

  constructor(private readonly maximumBytes: number | undefined) {
    if (
      maximumBytes !== undefined &&
      (!Number.isSafeInteger(maximumBytes) || maximumBytes <= 0)
    ) {
      throw new CanonicalJsonError("canonical JSON byte bound must be a positive safe integer");
    }
  }

  write(value: JsonValue): void {
    if (value === null) {
      this.append("null");
      return;
    }
    if (typeof value === "boolean") {
      this.append(value ? "true" : "false");
      return;
    }
    if (typeof value === "number") {
      if (!Number.isSafeInteger(value) || Object.is(value, -0)) {
        throw new CanonicalJsonError(
          "canonical JSON permits only safe integers other than negative zero",
        );
      }
      this.append(String(value));
      return;
    }
    if (typeof value === "string") {
      this.writeString(value);
      return;
    }
    if (Array.isArray(value)) {
      this.append("[");
      value.forEach((entry, index) => {
        if (index !== 0) this.append(",");
        this.write(entry);
      });
      this.append("]");
      return;
    }

    const keys = Object.keys(value);
    for (const key of keys) assertUnicodeScalarString(key);
    keys.sort(compareUnicodeScalars);
    this.append("{");
    keys.forEach((key, index) => {
      if (index !== 0) this.append(",");
      this.writeString(key);
      this.append(":");
      this.write(value[key] as JsonValue);
    });
    this.append("}");
  }

  finish(): string {
    return this.fragments.join("");
  }

  private writeString(value: string): void {
    assertUnicodeScalarString(value);
    const encoded = JSON.stringify(value);
    if (encoded === undefined) throw new CanonicalJsonError("string serialization failed");
    this.append(encoded);
  }

  private append(fragment: string): void {
    if (this.maximumBytes !== undefined) {
      const nextLength = this.byteLength + encoder.encode(fragment).byteLength;
      if (!Number.isSafeInteger(nextLength) || nextLength > this.maximumBytes) {
        throw new CanonicalJsonError(
          `canonical JSON exceeds ${this.maximumBytes} UTF-8 bytes`,
        );
      }
      this.byteLength = nextLength;
    }
    this.fragments.push(fragment);
  }
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
