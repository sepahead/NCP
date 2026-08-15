interface ImportMeta {
  readonly dir: string;
}

declare const Bun: {
  readonly argv: readonly string[];
  file(path: string | URL): {
    arrayBuffer(): Promise<ArrayBuffer>;
    stat(): Promise<{
      readonly size: number;
      isFile(): boolean;
      isSymbolicLink(): boolean;
    }>;
  };
  CryptoHasher: new (algorithm: "sha256") => {
    update(data: Uint8Array): void;
    digest(encoding: "hex"): string;
  };
};

declare module "node:fs/promises" {
  interface Dirent {
    readonly name: string;
    isFile(): boolean;
    isSymbolicLink(): boolean;
  }

  interface FileStat {
    readonly dev: number;
    readonly ino: number;
    readonly size: number;
    readonly mtimeMs: number;
    readonly ctimeMs: number;
    isFile(): boolean;
    isDirectory(): boolean;
    isSymbolicLink(): boolean;
  }

  interface FileHandle {
    stat(): Promise<FileStat>;
    read(
      buffer: Uint8Array,
      offset: number,
      length: number,
      position: number,
    ): Promise<{ bytesRead: number }>;
    close(): Promise<void>;
  }

  export const constants: {
    readonly O_RDONLY: number;
    readonly O_NOFOLLOW: number;
  };

  export function open(
    path: string | URL,
    flags: number,
  ): Promise<FileHandle>;

  export function readdir(
    path: string | URL,
    options: { readonly withFileTypes: true },
  ): Promise<Dirent[]>;

  export function lstat(path: string | URL): Promise<FileStat>;
  export function realpath(path: string | URL): Promise<string>;
}

declare module "node:path" {
  export function resolve(...paths: string[]): string;
}

declare const process: {
  exitCode: number | undefined;
  readonly stdout: { write(value: string): void };
  readonly stderr: { write(value: string): void };
};
