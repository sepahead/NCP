/**
 * Controller mode (the safety-critical action authority lives here). Unknown
 * additive strings are preserved, but every safety decision treats them exactly
 * like a non-Active mode and emits HOLD.
 */
export type Mode = "init" | "active" | "hold" | "estop" | (string & {});
//# sourceMappingURL=Mode.d.ts.map