/** NCP request-digest-v1 semantic projection and SHA-256.
 *
 * This is an independent TypeScript implementation of the normative typed,
 * length-prefixed projection. It deliberately does not call the Rust FFI.
 */
export declare const REQUEST_DIGEST_DOMAIN_V1 = "ncp.request-digest.v1\0";
export declare const MAX_REQUEST_PROJECTION_BYTES = 2097152;
export declare class RequestDigestError extends Error {
    constructor(detail: string);
}
/** Exact request-digest-v1 projection bytes. */
export declare function canonicalRequestProjection(request: unknown): Uint8Array;
/** Lowercase SHA-256 of the request-digest-v1 projection. */
export declare function requestDigest(request: unknown): string;
/** Verify the embedded operation.request_digest. */
export declare function verifyRequestDigest(request: unknown): void;
//# sourceMappingURL=request-digest.d.ts.map