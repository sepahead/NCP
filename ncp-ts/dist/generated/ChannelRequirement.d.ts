/**
 * Whether a negotiated channel is mandatory. Wire 1.0 deliberately makes
 * absence/`"unknown"` non-authorizing; wire 0.8's missing `optional` boolean
 * optimistically defaulted to `true` and is accepted only by the labelled gateway.
 */
export type ChannelRequirement = "unknown" | "required" | "optional";
//# sourceMappingURL=ChannelRequirement.d.ts.map