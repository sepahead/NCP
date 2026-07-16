import { Buffer } from "node:buffer";
import { PrototypeError } from "./errors.js";

export const JSON_SAFE_INTEGER_MAX = 9_007_199_254_740_991;

export interface JsonLimits {
  readonly maxBytes: number;
  readonly maxDepth: number;
  readonly maxNodes: number;
  readonly maxMembers: number;
  readonly maxStringBytes: number;
}

export interface DecimalToken {
  readonly kind: "decimal";
  readonly token: string;
}

export type JsonPrimitive = null | boolean | string | number | DecimalToken;
export type JsonArray = JsonValue[];
export type JsonObject = { [key: string]: JsonValue };
export type JsonValue = JsonPrimitive | JsonArray | JsonObject;

const HEX = /^[0-9a-fA-F]{4}$/;

function decimalToken(token: string): DecimalToken {
  return Object.freeze({ kind: "decimal", token });
}

export function isJsonObject(value: JsonValue | unknown): value is JsonObject {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === null
  );
}

function isDecimalToken(value: JsonValue | unknown): value is DecimalToken {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) !== null &&
    (value as Partial<DecimalToken>).kind === "decimal" &&
    typeof (value as Partial<DecimalToken>).token === "string"
  );
}

class Parser {
  private readonly source: string;
  private readonly limits: JsonLimits;
  private readonly allowFloats: boolean;
  private index = 0;
  private nodes = 0;

  constructor(bytes: Uint8Array, limits: JsonLimits, allowFloats: boolean) {
    if (bytes.byteLength < 1 || bytes.byteLength > limits.maxBytes) {
      throw new PrototypeError(
        "bounds",
        `JSON byte length is outside 1..=${limits.maxBytes}`,
      );
    }
    if (
      bytes.byteLength >= 3 &&
      bytes[0] === 0xef &&
      bytes[1] === 0xbb &&
      bytes[2] === 0xbf
    ) {
      throw new PrototypeError("encoding", "UTF-8 BOM is forbidden");
    }
    try {
      this.source = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch (error) {
      throw new PrototypeError("encoding", `invalid UTF-8: ${String(error)}`);
    }
    this.limits = limits;
    this.allowFloats = allowFloats;
  }

  parse(): JsonValue {
    this.space();
    const value = this.value(1);
    this.space();
    if (this.index !== this.source.length) {
      this.fail("trailing characters after one JSON value");
    }
    walkDecoded(value, this.limits);
    return value;
  }

  private fail(detail: string): never {
    throw new PrototypeError("json", detail);
  }

  private space(): void {
    while (this.index < this.source.length) {
      const code = this.source.charCodeAt(this.index);
      if (code !== 0x20 && code !== 0x09 && code !== 0x0a && code !== 0x0d) {
        return;
      }
      this.index += 1;
    }
  }

  private node(depth: number): void {
    if (depth > this.limits.maxDepth) {
      throw new PrototypeError("bounds", "JSON nesting depth exceeds the profile limit");
    }
    this.nodes += 1;
    if (this.nodes > this.limits.maxNodes) {
      throw new PrototypeError("bounds", "JSON node count exceeds the profile limit");
    }
  }

  private value(depth: number): JsonValue {
    this.space();
    this.node(depth);
    const token = this.source[this.index];
    if (token === undefined) {
      this.fail("JSON value is truncated");
    }
    if (token === "{") return this.object(depth);
    if (token === "[") return this.array(depth);
    if (token === '"') return this.string();
    if (token === "t") return this.literal("true", true);
    if (token === "f") return this.literal("false", false);
    if (token === "n") return this.literal("null", null);
    if (token === "-" || (token >= "0" && token <= "9")) return this.number();
    return this.fail("unknown JSON value token");
  }

  private object(depth: number): JsonObject {
    this.take("{");
    this.space();
    const value = Object.create(null) as JsonObject;
    const names = new Set<string>();
    if (this.source[this.index] === "}") {
      this.index += 1;
      return value;
    }
    let members = 0;
    while (true) {
      members += 1;
      if (members > this.limits.maxMembers) {
        throw new PrototypeError("bounds", "JSON object member count exceeds the limit");
      }
      this.space();
      if (this.source[this.index] !== '"') {
        this.fail("JSON object name is not a string");
      }
      const name = this.string();
      if (names.has(name)) {
        this.fail(`duplicate JSON member ${JSON.stringify(name)}`);
      }
      names.add(name);
      this.space();
      this.take(":");
      value[name] = this.value(depth + 1);
      this.space();
      const separator = this.source[this.index];
      this.index += 1;
      if (separator === "}") return value;
      if (separator !== ",") this.fail("JSON object has an invalid separator");
    }
  }

  private array(depth: number): JsonArray {
    this.take("[");
    this.space();
    const value: JsonArray = [];
    if (this.source[this.index] === "]") {
      this.index += 1;
      return value;
    }
    while (true) {
      if (value.length >= this.limits.maxMembers) {
        throw new PrototypeError("bounds", "JSON array length exceeds the profile limit");
      }
      value.push(this.value(depth + 1));
      this.space();
      const separator = this.source[this.index];
      this.index += 1;
      if (separator === "]") return value;
      if (separator !== ",") this.fail("JSON array has an invalid separator");
    }
  }

  private string(): string {
    this.take('"');
    const rawStart = this.index;
    let output = "";
    while (this.index < this.source.length) {
      const code = this.source.charCodeAt(this.index);
      this.index += 1;
      if (code === 0x22) {
        const rawEnd = this.index - 1;
        if (
          Buffer.byteLength(this.source.slice(rawStart, rawEnd), "utf8") >
          this.limits.maxStringBytes
        ) {
          throw new PrototypeError("bounds", "JSON string token exceeds the profile limit");
        }
        if (Buffer.byteLength(output, "utf8") > this.limits.maxStringBytes) {
          throw new PrototypeError("bounds", "decoded JSON string exceeds the profile limit");
        }
        return output;
      }
      if (code < 0x20) this.fail("JSON string contains a raw control character");
      if (code === 0x5c) {
        output += this.escape();
        continue;
      }
      if (code >= 0xd800 && code <= 0xdbff) {
        const low = this.source.charCodeAt(this.index);
        if (low < 0xdc00 || low > 0xdfff) {
          this.fail("JSON string contains an unpaired high surrogate");
        }
        output += String.fromCharCode(code, low);
        this.index += 1;
        continue;
      }
      if (code >= 0xdc00 && code <= 0xdfff) {
        this.fail("JSON string contains an unpaired low surrogate");
      }
      output += String.fromCharCode(code);
    }
    return this.fail("JSON string is truncated");
  }

  private escape(): string {
    const token = this.source[this.index];
    this.index += 1;
    const simple: Record<string, string> = {
      '"': '"',
      "\\": "\\",
      "/": "/",
      b: "\b",
      f: "\f",
      n: "\n",
      r: "\r",
      t: "\t",
    };
    if (token !== undefined && Object.hasOwn(simple, token)) {
      return simple[token]!;
    }
    if (token !== "u") this.fail("JSON string contains an unknown escape");
    const high = this.hex4();
    if (high >= 0xd800 && high <= 0xdbff) {
      if (this.source.slice(this.index, this.index + 2) !== "\\u") {
        this.fail("JSON string contains an unpaired high surrogate");
      }
      this.index += 2;
      const low = this.hex4();
      if (low < 0xdc00 || low > 0xdfff) {
        this.fail("JSON string contains an invalid surrogate pair");
      }
      return String.fromCodePoint(0x10000 + ((high - 0xd800) << 10) + (low - 0xdc00));
    }
    if (high >= 0xdc00 && high <= 0xdfff) {
      this.fail("JSON string contains an unpaired low surrogate");
    }
    return String.fromCharCode(high);
  }

  private hex4(): number {
    const token = this.source.slice(this.index, this.index + 4);
    if (!HEX.test(token)) this.fail("JSON unicode escape is invalid or truncated");
    this.index += 4;
    return Number.parseInt(token, 16);
  }

  private literal<T extends JsonPrimitive>(token: string, value: T): T {
    if (this.source.slice(this.index, this.index + token.length) !== token) {
      this.fail("JSON literal is invalid");
    }
    this.index += token.length;
    return value;
  }

  private number(): number | DecimalToken {
    const start = this.index;
    let negative = false;
    if (this.source[this.index] === "-") {
      negative = true;
      this.index += 1;
      if (this.index >= this.source.length) this.fail("JSON number is truncated");
    }
    if (this.source[this.index] === "0") {
      this.index += 1;
      const next = this.source[this.index];
      if (next !== undefined && next >= "0" && next <= "9") {
        this.fail("JSON number has a leading zero");
      }
      if (negative && next !== "." && next !== "e" && next !== "E") {
        this.fail("negative zero integer is forbidden");
      }
    } else {
      const first = this.source[this.index];
      if (first === undefined || first < "1" || first > "9") {
        this.fail("JSON number has an invalid integer part");
      }
      this.index += 1;
      while (true) {
        const digit = this.source[this.index];
        if (digit === undefined || digit < "0" || digit > "9") break;
        this.index += 1;
      }
    }
    let fractional = false;
    if (this.source[this.index] === ".") {
      if (!this.allowFloats) this.fail("fractional numbers are forbidden");
      fractional = true;
      this.index += 1;
      const digits = this.index;
      while (true) {
        const digit = this.source[this.index];
        if (digit === undefined || digit < "0" || digit > "9") break;
        this.index += 1;
      }
      if (digits === this.index) this.fail("JSON fraction has no digits");
    }
    let exponent = false;
    if (this.source[this.index] === "e" || this.source[this.index] === "E") {
      if (!this.allowFloats) this.fail("exponent numbers are forbidden");
      exponent = true;
      this.index += 1;
      if (this.source[this.index] === "+" || this.source[this.index] === "-") {
        this.index += 1;
      }
      const digits = this.index;
      while (true) {
        const digit = this.source[this.index];
        if (digit === undefined || digit < "0" || digit > "9") break;
        this.index += 1;
      }
      if (digits === this.index) this.fail("JSON exponent has no digits");
    }
    const token = this.source.slice(start, this.index);
    if (fractional || exponent) return decimalToken(token);
    const integer = BigInt(token);
    if (
      integer < BigInt(-JSON_SAFE_INTEGER_MAX) ||
      integer > BigInt(JSON_SAFE_INTEGER_MAX)
    ) {
      throw new PrototypeError(
        "bounds",
        "JSON integer exceeds the interoperable safe-integer range",
      );
    }
    return Number(integer);
  }

  private take(expected: string): void {
    if (this.source[this.index] !== expected) this.fail("invalid JSON token");
    this.index += 1;
  }
}

function walkDecoded(value: JsonValue, limits: JsonLimits, depth = 1): number {
  if (depth > limits.maxDepth) {
    throw new PrototypeError("bounds", "decoded JSON depth exceeds the profile limit");
  }
  let nodes = 1;
  if (typeof value === "string") {
    if (Buffer.byteLength(value, "utf8") > limits.maxStringBytes) {
      throw new PrototypeError("bounds", "decoded JSON string exceeds the profile limit");
    }
  } else if (Array.isArray(value)) {
    if (value.length > limits.maxMembers) {
      throw new PrototypeError("bounds", "decoded JSON array is too wide");
    }
    for (const child of value) nodes += walkDecoded(child, limits, depth + 1);
  } else if (isJsonObject(value)) {
    const entries = Object.entries(value);
    if (entries.length > limits.maxMembers) {
      throw new PrototypeError("bounds", "decoded JSON object is too wide");
    }
    for (const [key, child] of entries) {
      nodes += walkDecoded(key, limits, depth + 1);
      nodes += walkDecoded(child, limits, depth + 1);
    }
  } else if (isDecimalToken(value)) {
    // Decimal tokens are already bounded substrings of the bounded source.
  }
  if (nodes > limits.maxNodes) {
    throw new PrototypeError("bounds", "decoded JSON node count exceeds the limit");
  }
  return nodes;
}

export function strictJsonParse(
  bytes: Uint8Array,
  limits: JsonLimits,
  allowFloats = false,
): JsonValue {
  return new Parser(bytes, limits, allowFloats).parse();
}

export function exactMembers(
  value: JsonValue | unknown,
  expected: readonly string[],
  field: string,
): JsonObject {
  if (!isJsonObject(value)) {
    throw new PrototypeError("profile", `${field} is not an object`);
  }
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (
    actual.length !== wanted.length ||
    actual.some((member, index) => member !== wanted[index])
  ) {
    throw new PrototypeError(
      "profile",
      `${field} must contain exactly ${JSON.stringify(wanted)}`,
    );
  }
  return value;
}
