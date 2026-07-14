/** NCP 1.0 universal bounded-JSON preflight.
 *
 * This is intentionally independent of the Rust parser. It validates aggregate
 * structure and duplicate decoded keys before `JSON.parse` can collapse them.
 * Constants mirror `contract/limits.v1.json` and `ncp-core::bounded_json`.
 */
export declare const JSON_LIMITS: Readonly<{
    maxFrameBytes: 1048576;
    maxNestingDepth: 32;
    maxObjects: 4096;
    maxArrays: 4096;
    maxTotalMembers: 16384;
    maxTotalArrayItems: 262144;
    maxObjectMembers: 4096;
    maxArrayItems: 65536;
    maxKeyBytes: 128;
    maxStringBytes: 65536;
    maxTotalStringBytes: 1048576;
    maxFiniteNumberMagnitude: 1e+300;
}>;
export type JsonLimitCode = 'NCP-LIMIT-001' | 'NCP-LIMIT-002' | 'NCP-LIMIT-003' | 'NCP-LIMIT-004' | 'NCP-LIMIT-005' | 'NCP-LIMIT-006' | 'NCP-LIMIT-007' | 'NCP-LIMIT-008' | 'NCP-LIMIT-009';
export declare class BoundedJsonError extends Error {
    readonly code: JsonLimitCode;
    readonly offset: number;
    constructor(code: JsonLimitCode, offset: number, detail: string);
}
export declare function preflightJson(input: string): void;
export declare function parseBoundedJson(input: string): unknown;
//# sourceMappingURL=bounded-json.d.ts.map