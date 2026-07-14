/** NCP 1.0 universal bounded-JSON preflight.
 *
 * This is intentionally independent of the Rust parser. It validates aggregate
 * structure and duplicate decoded keys before `JSON.parse` can collapse them.
 * Constants mirror `contract/limits.v1.json` and `ncp-core::bounded_json`.
 */
export const JSON_LIMITS = Object.freeze({
    maxFrameBytes: 1_048_576,
    maxNestingDepth: 32,
    maxObjects: 4_096,
    maxArrays: 4_096,
    maxTotalMembers: 16_384,
    maxTotalArrayItems: 262_144,
    maxObjectMembers: 4_096,
    maxArrayItems: 65_536,
    maxKeyBytes: 128,
    maxStringBytes: 65_536,
    maxTotalStringBytes: 1_048_576,
    safeIntegerMin: -9_007_199_254_740_991,
    safeIntegerMax: 9_007_199_254_740_991,
    maxFiniteNumberMagnitude: 1e300,
});
const SAFE_INTEGER_MAX_DECIMAL = '9007199254740991';
function jsonIntegerMagnitudeStart(token) {
    // Only canonical integer spellings take the early limit path. Malformed
    // numeric spellings must retain their NCP-LIMIT-009 classification below.
    const start = token[0] === '-' ? 1 : 0;
    const first = token.charCodeAt(start);
    if (first === 0x30)
        return token.length - start === 1 ? start : undefined;
    if (first < 0x31 || first > 0x39)
        return undefined;
    for (let index = start + 1; index < token.length; index++) {
        const digit = token.charCodeAt(index);
        if (digit < 0x30 || digit > 0x39)
            return undefined;
    }
    return start;
}
function integerTokenExceedsSafeRange(token) {
    const magnitudeStart = jsonIntegerMagnitudeStart(token);
    if (magnitudeStart === undefined)
        return false;
    const magnitudeLength = token.length - magnitudeStart;
    if (magnitudeLength !== SAFE_INTEGER_MAX_DECIMAL.length) {
        return magnitudeLength > SAFE_INTEGER_MAX_DECIMAL.length;
    }
    for (let index = 0; index < magnitudeLength; index++) {
        const digit = token.charCodeAt(magnitudeStart + index);
        const boundaryDigit = SAFE_INTEGER_MAX_DECIMAL.charCodeAt(index);
        if (digit !== boundaryDigit)
            return digit > boundaryDigit;
    }
    return false;
}
export class BoundedJsonError extends Error {
    code;
    offset;
    constructor(code, offset, detail) {
        super(`${code} at UTF-8 byte ${offset}: ${detail}`);
        this.code = code;
        this.offset = offset;
        this.name = 'BoundedJsonError';
    }
}
/** Count UTF-8 bytes without materializing a second full-frame `Uint8Array`.
 *
 * Browser WebSocket text messages are already buffered as UTF-16 strings. Using
 * `TextEncoder.encode(input)` for the outer byte gate duplicates an arbitrarily
 * large reply before it can be rejected. This bounded counter stops as soon as
 * `stopAfter` is exceeded. Unpaired surrogates count like TextEncoder's U+FFFD;
 * the scanner subsequently rejects them with NCP-LIMIT-008.
 */
function utf8ByteLength(input, end = input.length, stopAfter = Number.MAX_SAFE_INTEGER) {
    let bytes = 0;
    for (let index = 0; index < end; index++) {
        const unit = input.charCodeAt(index);
        if (unit <= 0x7f) {
            bytes += 1;
        }
        else if (unit <= 0x7ff) {
            bytes += 2;
        }
        else if (unit >= 0xd800 && unit <= 0xdbff) {
            const next = input.charCodeAt(index + 1);
            if (index + 1 < end && next >= 0xdc00 && next <= 0xdfff) {
                bytes += 4;
                index++;
            }
            else {
                bytes += 3;
            }
        }
        else {
            // BMP code points, low surrogates (replacement), and noncharacters all
            // occupy three bytes under TextEncoder's UTF-8 conversion.
            bytes += 3;
        }
        if (bytes > stopAfter)
            return bytes;
    }
    return bytes;
}
class Scanner {
    input;
    position = 0;
    objects = 0;
    arrays = 0;
    members = 0;
    arrayItems = 0;
    stringBytes = 0;
    constructor(input) {
        this.input = input;
    }
    byteOffset() {
        return utf8ByteLength(this.input, this.position);
    }
    fail(code, detail) {
        throw new BoundedJsonError(code, this.byteOffset(), detail);
    }
    skipWhitespace() {
        while (/\s/u.test(this.input[this.position] ?? '') && /[ \n\r\t]/u.test(this.input[this.position])) {
            this.position++;
        }
    }
    expect(expected) {
        if (this.input[this.position] !== expected)
            this.fail('NCP-LIMIT-009', 'unexpected token');
        this.position++;
    }
    scan() {
        this.parseValue(0);
        this.skipWhitespace();
        if (this.position !== this.input.length)
            this.fail('NCP-LIMIT-009', 'trailing JSON bytes');
    }
    parseValue(depth) {
        this.skipWhitespace();
        if (depth > JSON_LIMITS.maxNestingDepth) {
            this.fail('NCP-LIMIT-002', 'JSON nesting depth exceeded');
        }
        const token = this.input[this.position];
        if (token === '{')
            return this.parseObject(depth + 1);
        if (token === '[')
            return this.parseArray(depth + 1);
        if (token === '"') {
            this.parseString(false);
            return;
        }
        if (token === 't')
            return this.parseLiteral('true');
        if (token === 'f')
            return this.parseLiteral('false');
        if (token === 'n')
            return this.parseLiteral('null');
        if (token === '-' || (token !== undefined && /[0-9]/u.test(token))) {
            return this.parseNumber();
        }
        this.fail('NCP-LIMIT-009', 'expected a JSON value');
    }
    parseLiteral(literal) {
        if (this.input.slice(this.position, this.position + literal.length) !== literal) {
            this.fail('NCP-LIMIT-009', 'invalid JSON literal');
        }
        this.position += literal.length;
    }
    parseNumber() {
        const start = this.position;
        while (/[0-9+\-.eE]/u.test(this.input[this.position] ?? ''))
            this.position++;
        const token = this.input.slice(start, this.position);
        // Compare decimal digits before JSON.parse can round an unsafe integer.
        if (integerTokenExceedsSafeRange(token)) {
            this.fail('NCP-LIMIT-006', 'integer exceeds the exact JSON range');
        }
        let value;
        try {
            value = JSON.parse(token);
        }
        catch {
            this.fail('NCP-LIMIT-009', 'invalid JSON number');
        }
        if (typeof value !== 'number' ||
            !Number.isFinite(value) ||
            Math.abs(value) > JSON_LIMITS.maxFiniteNumberMagnitude) {
            this.fail('NCP-LIMIT-006', 'number exceeds the finite magnitude budget');
        }
    }
    parseString(key) {
        const start = this.position;
        this.expect('"');
        let escaped = false;
        for (;;) {
            const character = this.input[this.position];
            if (character === undefined)
                this.fail('NCP-LIMIT-009', 'unterminated JSON string');
            this.position++;
            if (escaped) {
                escaped = false;
                continue;
            }
            if (character === '\\') {
                escaped = true;
                continue;
            }
            if (character === '"')
                break;
            if (character.charCodeAt(0) <= 0x1f) {
                this.fail('NCP-LIMIT-008', 'unescaped control character in JSON string');
            }
        }
        let decoded;
        try {
            decoded = JSON.parse(this.input.slice(start, this.position));
        }
        catch {
            this.fail('NCP-LIMIT-008', 'invalid JSON string or Unicode');
        }
        if (typeof decoded !== 'string')
            this.fail('NCP-LIMIT-008', 'invalid JSON string');
        for (let index = 0; index < decoded.length; index++) {
            const unit = decoded.charCodeAt(index);
            if (unit >= 0xd800 && unit <= 0xdbff) {
                const next = decoded.charCodeAt(index + 1);
                if (!(next >= 0xdc00 && next <= 0xdfff)) {
                    this.fail('NCP-LIMIT-008', 'unpaired high surrogate in JSON string');
                }
                index++;
            }
            else if (unit >= 0xdc00 && unit <= 0xdfff) {
                this.fail('NCP-LIMIT-008', 'unpaired low surrogate in JSON string');
            }
        }
        const limit = key ? JSON_LIMITS.maxKeyBytes : JSON_LIMITS.maxStringBytes;
        const bytes = utf8ByteLength(decoded, decoded.length, limit);
        if (bytes > limit)
            this.fail('NCP-LIMIT-005', 'JSON string exceeds byte limit');
        this.stringBytes += bytes;
        if (this.stringBytes > JSON_LIMITS.maxTotalStringBytes) {
            this.fail('NCP-LIMIT-005', 'aggregate JSON string budget exceeded');
        }
        return decoded;
    }
    parseObject(depth) {
        if (depth > JSON_LIMITS.maxNestingDepth)
            this.fail('NCP-LIMIT-002', 'JSON nesting depth exceeded');
        this.objects++;
        if (this.objects > JSON_LIMITS.maxObjects)
            this.fail('NCP-LIMIT-003', 'object count exceeded');
        this.expect('{');
        this.skipWhitespace();
        if (this.input[this.position] === '}') {
            this.position++;
            return;
        }
        const keys = new Set();
        for (;;) {
            this.skipWhitespace();
            const key = this.parseString(true);
            if (keys.has(key))
                this.fail('NCP-LIMIT-007', 'duplicate JSON object key');
            keys.add(key);
            this.members++;
            if (keys.size > JSON_LIMITS.maxObjectMembers ||
                this.members > JSON_LIMITS.maxTotalMembers) {
                this.fail('NCP-LIMIT-003', 'object member budget exceeded');
            }
            this.skipWhitespace();
            this.expect(':');
            this.parseValue(depth);
            this.skipWhitespace();
            if (this.input[this.position] === ',') {
                this.position++;
                continue;
            }
            if (this.input[this.position] === '}') {
                this.position++;
                return;
            }
            this.fail('NCP-LIMIT-009', "expected ',' or '}'");
        }
    }
    parseArray(depth) {
        if (depth > JSON_LIMITS.maxNestingDepth)
            this.fail('NCP-LIMIT-002', 'JSON nesting depth exceeded');
        this.arrays++;
        if (this.arrays > JSON_LIMITS.maxArrays)
            this.fail('NCP-LIMIT-004', 'array count exceeded');
        this.expect('[');
        this.skipWhitespace();
        if (this.input[this.position] === ']') {
            this.position++;
            return;
        }
        let localItems = 0;
        for (;;) {
            localItems++;
            this.arrayItems++;
            if (localItems > JSON_LIMITS.maxArrayItems ||
                this.arrayItems > JSON_LIMITS.maxTotalArrayItems) {
                this.fail('NCP-LIMIT-004', 'array item budget exceeded');
            }
            this.parseValue(depth);
            this.skipWhitespace();
            if (this.input[this.position] === ',') {
                this.position++;
                continue;
            }
            if (this.input[this.position] === ']') {
                this.position++;
                return;
            }
            this.fail('NCP-LIMIT-009', "expected ',' or ']' ");
        }
    }
}
export function preflightJson(input) {
    const bytes = utf8ByteLength(input, input.length, JSON_LIMITS.maxFrameBytes);
    if (bytes > JSON_LIMITS.maxFrameBytes) {
        throw new BoundedJsonError('NCP-LIMIT-001', JSON_LIMITS.maxFrameBytes, 'JSON frame byte limit exceeded');
    }
    new Scanner(input).scan();
}
export function parseBoundedJson(input) {
    preflightJson(input);
    return JSON.parse(input);
}
//# sourceMappingURL=bounded-json.js.map