import { constants, lstat, open, realpath } from "node:fs/promises";

export class SourceFileError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SourceFileError";
  }
}

export async function readBoundedRegularFile(
  url: string | URL,
  maximumBytes: number,
  label: string,
): Promise<Uint8Array> {
  if (!Number.isSafeInteger(maximumBytes) || maximumBytes <= 0) {
    throw new SourceFileError("file bound must be a positive safe integer");
  }
  let handle;
  try {
    handle = await open(url, constants.O_RDONLY | constants.O_NOFOLLOW);
  } catch (error) {
    throw new SourceFileError(`${label} cannot be opened without following links: ${errorText(error)}`);
  }
  try {
    const before = await handle.stat();
    if (!before.isFile()) {
      throw new SourceFileError(`${label} is not a regular file`);
    }
    if (before.size > maximumBytes) {
      throw new SourceFileError(`${label} exceeds ${maximumBytes} bytes`);
    }

    const allocation = new Uint8Array(before.size + 1);
    let used = 0;
    while (used < allocation.byteLength) {
      const { bytesRead } = await handle.read(
        allocation,
        used,
        allocation.byteLength - used,
        used,
      );
      if (bytesRead === 0) break;
      used += bytesRead;
    }
    if (used > maximumBytes) {
      throw new SourceFileError(`${label} grew beyond ${maximumBytes} bytes while read`);
    }
    const after = await handle.stat();
    if (
      before.dev !== after.dev ||
      before.ino !== after.ino ||
      before.size !== after.size ||
      before.mtimeMs !== after.mtimeMs ||
      before.ctimeMs !== after.ctimeMs ||
      used !== after.size
    ) {
      throw new SourceFileError(`${label} changed while it was read`);
    }
    return allocation.subarray(0, used);
  } finally {
    await handle.close();
  }
}

export async function readBoundedRepositoryFile(
  repositoryRoot: string,
  relativePath: string,
  maximumBytes: number,
  label: string,
): Promise<Uint8Array> {
  const path = await resolveRepositoryPath(
    repositoryRoot,
    relativePath,
    "file",
    label,
  );
  return readBoundedRegularFile(path, maximumBytes, label);
}

export async function resolveRepositoryDirectory(
  repositoryRoot: string,
  relativePath: string,
  label: string,
): Promise<string> {
  return resolveRepositoryPath(repositoryRoot, relativePath, "directory", label);
}

export function sha256(bytes: Uint8Array): string {
  const hasher = new Bun.CryptoHasher("sha256");
  hasher.update(bytes);
  return hasher.digest("hex");
}

export function extractExactJsonFences(markdownBytes: Uint8Array): Uint8Array[] {
  try {
    new TextDecoder("utf-8", { fatal: true }).decode(markdownBytes);
  } catch {
    throw new SourceFileError("ADR Markdown is not valid UTF-8");
  }

  type FenceState =
    | { readonly kind: "json"; readonly contentStart: number }
    | { readonly kind: "other" };
  const fences: Uint8Array[] = [];
  let state: FenceState | undefined;
  let lineStart = 0;
  while (lineStart < markdownBytes.byteLength) {
    let lineEnd = lineStart;
    while (lineEnd < markdownBytes.byteLength && markdownBytes[lineEnd] !== 0x0a) {
      lineEnd += 1;
    }
    let logicalEnd = lineEnd;
    if (logicalEnd > lineStart && markdownBytes[logicalEnd - 1] === 0x0d) {
      logicalEnd -= 1;
    }
    const nextLine = lineEnd < markdownBytes.byteLength ? lineEnd + 1 : lineEnd;

    if (state === undefined && equalsAscii(markdownBytes, lineStart, logicalEnd, "```json")) {
      if (lineEnd === markdownBytes.byteLength) {
        throw new SourceFileError("JSON fence opener has no following content line");
      }
      state = { kind: "json", contentStart: nextLine };
    } else if (
      state === undefined &&
      startsWithAscii(markdownBytes, lineStart, logicalEnd, "```")
    ) {
      state = { kind: "other" };
    } else if (
      state?.kind === "json" &&
      equalsAscii(markdownBytes, lineStart, logicalEnd, "```")
    ) {
      let contentEnd = lineStart;
      if (contentEnd > state.contentStart && markdownBytes[contentEnd - 1] === 0x0a) {
        contentEnd -= 1;
        if (contentEnd > state.contentStart && markdownBytes[contentEnd - 1] === 0x0d) {
          contentEnd -= 1;
        }
      }
      fences.push(markdownBytes.slice(state.contentStart, contentEnd));
      state = undefined;
    } else if (
      state?.kind === "other" &&
      equalsAscii(markdownBytes, lineStart, logicalEnd, "```")
    ) {
      state = undefined;
    }
    lineStart = nextLine;
  }
  if (state !== undefined) {
    throw new SourceFileError("ADR contains an unclosed Markdown fence");
  }
  return fences;
}

function equalsAscii(
  bytes: Uint8Array,
  start: number,
  end: number,
  expected: string,
): boolean {
  return end - start === expected.length && startsWithAscii(bytes, start, end, expected);
}

function startsWithAscii(
  bytes: Uint8Array,
  start: number,
  end: number,
  expected: string,
): boolean {
  if (end - start < expected.length) return false;
  for (let index = 0; index < expected.length; index += 1) {
    if (bytes[start + index] !== expected.charCodeAt(index)) return false;
  }
  return true;
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "unknown file error";
}

async function resolveRepositoryPath(
  repositoryRoot: string,
  relativePath: string,
  finalKind: "file" | "directory",
  label: string,
): Promise<string> {
  if (!repositoryRoot.startsWith("/") || repositoryRoot.includes("\0")) {
    throw new SourceFileError("repository root must be an absolute path without NUL");
  }
  const segments = relativePath.split("/");
  if (
    relativePath.startsWith("/") ||
    relativePath.includes("\0") ||
    segments.some((segment) => segment === "" || segment === "." || segment === "..")
  ) {
    throw new SourceFileError(`${label} path is not a normalized repository-relative path`);
  }

  let resolved = repositoryRoot.replace(/\/+$/, "");
  if (resolved === "") resolved = "/";
  const rootMetadata = await inspectPath(resolved, label);
  if (rootMetadata.isSymbolicLink() || !rootMetadata.isDirectory()) {
    throw new SourceFileError("repository root must be a non-symlink directory");
  }
  let canonicalRoot: string;
  try {
    canonicalRoot = await realpath(resolved);
  } catch (error) {
    throw new SourceFileError(`repository root cannot be resolved: ${errorText(error)}`);
  }
  if (canonicalRoot !== resolved) {
    throw new SourceFileError("repository root cannot contain a symbolic-link ancestor");
  }

  for (const [index, segment] of segments.entries()) {
    resolved = resolved === "/" ? `/${segment}` : `${resolved}/${segment}`;
    const metadata = await inspectPath(resolved, label);
    if (metadata.isSymbolicLink()) {
      throw new SourceFileError(`${label} path contains a symbolic link`);
    }
    const final = index + 1 === segments.length;
    const wrongKind = final
      ? finalKind === "file"
        ? !metadata.isFile()
        : !metadata.isDirectory()
      : !metadata.isDirectory();
    if (wrongKind) {
      throw new SourceFileError(
        final
          ? `${label} is not a regular ${finalKind}`
          : `${label} parent is not a directory`,
      );
    }
  }
  return resolved;
}

async function inspectPath(path: string, label: string) {
  try {
    return await lstat(path);
  } catch (error) {
    throw new SourceFileError(`${label} path cannot be inspected: ${errorText(error)}`);
  }
}
