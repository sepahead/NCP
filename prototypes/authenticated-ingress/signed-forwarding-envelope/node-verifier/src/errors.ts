export type ErrorCode =
  | "bounds"
  | "json"
  | "encoding"
  | "manifest"
  | "profile"
  | "crypto"
  | "payload";

export class PrototypeError extends Error {
  readonly code: ErrorCode;
  readonly detail: string;

  constructor(code: ErrorCode, detail: string) {
    super(`${code}: ${detail}`);
    this.name = "PrototypeError";
    this.code = code;
    this.detail = detail;
  }
}
