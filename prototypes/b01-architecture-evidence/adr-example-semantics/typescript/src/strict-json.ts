export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface JsonLimits {
  readonly maxBytes: number;
  readonly maxDepth: number;
  readonly maxNodes: number;
  readonly maxMembers: number;
  readonly maxArrayItems: number;
  readonly maxKeyBytes: number;
  readonly maxStringBytes: number;
  readonly maxTotalStringBytes: number;
  readonly maxIntegerCharacters: number;
}

export class StrictJsonError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StrictJsonError";
  }
}

const encoder = new TextEncoder();

export function strictJsonParse(
  bytes: Uint8Array,
  limits: JsonLimits,
): JsonValue {
  validateLimits(limits);
  if (bytes.byteLength > limits.maxBytes) {
    throw new StrictJsonError(
      `JSON byte length ${bytes.byteLength} exceeds ${limits.maxBytes}`,
    );
  }
  if (bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    throw new StrictJsonError("UTF-8 BOM is forbidden");
  }

  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new StrictJsonError("JSON is not valid UTF-8");
  }
  return new Parser(text, limits).parse();
}

function validateLimits(limits: JsonLimits): void {
  for (const [name, value] of Object.entries(limits)) {
    if (!Number.isSafeInteger(value) || value <= 0) {
      throw new StrictJsonError(`${name} must be a positive safe integer`);
    }
  }
}

class Parser {
  private index = 0;
  private nodes = 0;
  private totalStringBytes = 0;

  constructor(
    private readonly text: string,
    private readonly limits: JsonLimits,
  ) {}

  parse(): JsonValue {
    this.skipWhitespace();
    const value = this.parseValue(1);
    this.skipWhitespace();
    if (this.index !== this.text.length) {
      this.fail("trailing bytes after the JSON value");
    }
    return value;
  }

  private parseValue(depth: number): JsonValue {
    if (depth > this.limits.maxDepth) {
      this.fail(`JSON depth exceeds ${this.limits.maxDepth}`);
    }
    this.nodes += 1;
    if (this.nodes > this.limits.maxNodes) {
      this.fail(`JSON node count exceeds ${this.limits.maxNodes}`);
    }

    const token = this.text[this.index];
    switch (token) {
      case "{":
        return this.parseObject(depth);
      case "[":
        return this.parseArray(depth);
      case '"':
        return this.parseString(false);
      case "t":
        this.expectLiteral("true");
        return true;
      case "f":
        this.expectLiteral("false");
        return false;
      case "n":
        this.expectLiteral("null");
        return null;
      default:
        if (token === "-" || isDigit(token)) {
          return this.parseInteger();
        }
        this.fail("expected a JSON value");
    }
  }

  private parseObject(depth: number): { [key: string]: JsonValue } {
    this.index += 1;
    this.skipWhitespace();
    const result: { [key: string]: JsonValue } = Object.create(null) as {
      [key: string]: JsonValue;
    };
    const seen = new Set<string>();
    let memberCount = 0;
    if (this.consume("}")) {
      return result;
    }

    while (true) {
      if (memberCount >= this.limits.maxMembers) {
        this.fail(`JSON object member count exceeds ${this.limits.maxMembers}`);
      }
      if (this.text[this.index] !== '"') {
        this.fail("object member name must be a JSON string");
      }
      const key = this.parseString(true);
      if (seen.has(key)) {
        this.fail(`duplicate object member ${JSON.stringify(key)}`);
      }
      seen.add(key);
      memberCount += 1;
      this.skipWhitespace();
      if (!this.consume(":")) {
        this.fail("expected ':' after object member name");
      }
      this.skipWhitespace();
      result[key] = this.parseValue(depth + 1);
      this.skipWhitespace();
      if (this.consume("}")) {
        return result;
      }
      if (!this.consume(",")) {
        this.fail("expected ',' or '}' after object member value");
      }
      this.skipWhitespace();
    }
  }

  private parseArray(depth: number): JsonValue[] {
    this.index += 1;
    this.skipWhitespace();
    const result: JsonValue[] = [];
    if (this.consume("]")) {
      return result;
    }
    while (true) {
      if (result.length >= this.limits.maxArrayItems) {
        this.fail(`array item count exceeds ${this.limits.maxArrayItems}`);
      }
      result.push(this.parseValue(depth + 1));
      this.skipWhitespace();
      if (this.consume("]")) {
        return result;
      }
      if (!this.consume(",")) {
        this.fail("expected ',' or ']' after array element");
      }
      this.skipWhitespace();
    }
  }

  private parseString(isKey: boolean): string {
    this.index += 1;
    let result = "";
    let byteLength = 0;
    while (this.index < this.text.length) {
      const code = this.text.charCodeAt(this.index);
      if (code === 0x22) {
        this.index += 1;
        this.totalStringBytes += byteLength;
        return result;
      }
      if (code < 0x20) {
        this.fail("unescaped control character in JSON string");
      }
      if (code === 0x5c) {
        this.index += 1;
        const fragment = this.parseEscape();
        byteLength = this.checkedStringAppend(
          byteLength,
          utf8ScalarStringBytes(fragment),
          isKey,
        );
        result += fragment;
        continue;
      }
      if (isHighSurrogate(code)) {
        const low = this.text.charCodeAt(this.index + 1);
        if (!isLowSurrogate(low)) {
          this.fail("unpaired high surrogate in JSON string");
        }
        byteLength = this.checkedStringAppend(byteLength, 4, isKey);
        result += this.text.slice(this.index, this.index + 2);
        this.index += 2;
        continue;
      }
      if (isLowSurrogate(code)) {
        this.fail("unpaired low surrogate in JSON string");
      }
      byteLength = this.checkedStringAppend(
        byteLength,
        utf8CodeUnitBytes(code),
        isKey,
      );
      result += this.text[this.index] as string;
      this.index += 1;
    }
    this.fail("unterminated JSON string");
  }

  private checkedStringAppend(
    currentBytes: number,
    fragmentBytes: number,
    isKey: boolean,
  ): number {
    const nextBytes = currentBytes + fragmentBytes;
    const individualLimit = isKey ? this.limits.maxKeyBytes : this.limits.maxStringBytes;
    if (!Number.isSafeInteger(nextBytes) || nextBytes > individualLimit) {
      this.fail(`decoded string exceeds ${individualLimit} bytes`);
    }
    const nextTotal = this.totalStringBytes + nextBytes;
    if (!Number.isSafeInteger(nextTotal) || nextTotal > this.limits.maxTotalStringBytes) {
      this.fail(`total decoded string bytes exceed ${this.limits.maxTotalStringBytes}`);
    }
    return nextBytes;
  }

  private parseEscape(): string {
    const escaped = this.text[this.index];
    this.index += 1;
    switch (escaped) {
      case '"':
      case "\\":
      case "/":
        return escaped;
      case "b":
        return "\b";
      case "f":
        return "\f";
      case "n":
        return "\n";
      case "r":
        return "\r";
      case "t":
        return "\t";
      case "u": {
        const first = this.readHexCodeUnit();
        if (isHighSurrogate(first)) {
          if (this.text.slice(this.index, this.index + 2) !== "\\u") {
            this.fail("escaped high surrogate lacks a low-surrogate escape");
          }
          this.index += 2;
          const second = this.readHexCodeUnit();
          if (!isLowSurrogate(second)) {
            this.fail("escaped high surrogate has an invalid pair");
          }
          return String.fromCharCode(first, second);
        }
        if (isLowSurrogate(first)) {
          this.fail("unpaired escaped low surrogate in JSON string");
        }
        return String.fromCharCode(first);
      }
      default:
        this.fail("invalid JSON string escape");
    }
  }

  private readHexCodeUnit(): number {
    const value = this.text.slice(this.index, this.index + 4);
    if (!/^[0-9a-fA-F]{4}$/.test(value)) {
      this.fail("invalid Unicode escape in JSON string");
    }
    this.index += 4;
    return Number.parseInt(value, 16);
  }

  private parseInteger(): number {
    const start = this.index;
    this.consume("-");
    if (this.consume("0")) {
      if (isDigit(this.text[this.index])) {
        this.fail("integer has a leading zero");
      }
    } else {
      const first = this.text[this.index];
      if (first === undefined || first < "1" || first > "9") {
        this.fail("invalid integer");
      }
      this.index += 1;
      while (isDigit(this.text[this.index])) {
        this.index += 1;
      }
    }
    if ([".", "e", "E"].includes(this.text[this.index] ?? "")) {
      this.fail("floating-point JSON numbers are forbidden");
    }
    const token = this.text.slice(start, this.index);
    if (token === "-0") {
      this.fail("negative zero is forbidden");
    }
    if (token.length > this.limits.maxIntegerCharacters) {
      this.fail(
        `integer has more than ${this.limits.maxIntegerCharacters} characters`,
      );
    }
    const value = Number(token);
    if (!Number.isSafeInteger(value)) {
      this.fail("integer is outside the exact JSON-safe range");
    }
    return value;
  }

  private expectLiteral(expected: string): void {
    if (this.text.slice(this.index, this.index + expected.length) !== expected) {
      this.fail(`expected ${expected}`);
    }
    this.index += expected.length;
  }

  private skipWhitespace(): void {
    while ([" ", "\t", "\r", "\n"].includes(this.text[this.index] ?? "")) {
      this.index += 1;
    }
  }

  private consume(expected: string): boolean {
    if (this.text[this.index] !== expected) {
      return false;
    }
    this.index += 1;
    return true;
  }

  private fail(message: string): never {
    throw new StrictJsonError(`${message} at UTF-16 offset ${this.index}`);
  }
}

function isDigit(value: string | undefined): boolean {
  return value !== undefined && value >= "0" && value <= "9";
}

function isHighSurrogate(value: number): boolean {
  return value >= 0xd800 && value <= 0xdbff;
}

function isLowSurrogate(value: number): boolean {
  return value >= 0xdc00 && value <= 0xdfff;
}

function utf8CodeUnitBytes(value: number): number {
  if (value <= 0x7f) return 1;
  if (value <= 0x7ff) return 2;
  return 3;
}

function utf8ScalarStringBytes(value: string): number {
  if (value.length === 2) return 4;
  const code = value.charCodeAt(0);
  if (!Number.isFinite(code)) throw new StrictJsonError("empty decoded string fragment");
  return utf8CodeUnitBytes(code);
}
