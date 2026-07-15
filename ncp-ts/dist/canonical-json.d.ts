/** Deterministic NCP message round-trip bytes.
 *
 * The Rust reference materializes serde defaults, drops unknown object members,
 * emits struct fields in declaration order, orders map keys by UTF-8 bytes, and
 * uses serde_json/ryu spelling for binary64 values. This module mirrors that
 * projection independently for the stable message set so the mandatory corpus
 * can compare emitted bytes rather than merely reparsed values.
 */
/** Validate a programmatic TypeScript message and emit Rust-reference-identical bytes. */
export declare function canonicalizeNcpMessage(value: unknown, expectedKind?: string): string;
/** Apply bounded raw-JSON ingress before producing deterministic message bytes. */
export declare function canonicalizeNcpJson(input: string, expectedKind?: string): string;
//# sourceMappingURL=canonical-json.d.ts.map