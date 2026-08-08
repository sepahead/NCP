import type { JsonValue } from "./strict-json.ts";

export type PatchOperation =
  | { readonly op: "add"; readonly path: string; readonly value: JsonValue }
  | { readonly op: "remove"; readonly path: string }
  | { readonly op: "replace"; readonly path: string; readonly value: JsonValue };

export class JsonPointerError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "JsonPointerError";
  }
}

export function applyPatch(
  input: JsonValue,
  operations: readonly PatchOperation[],
): JsonValue {
  if (operations.length > 64) {
    throw new JsonPointerError("mutation exceeds the 64-operation bound");
  }
  const value = cloneJson(input);
  for (const operation of operations) {
    applyOperation(value, operation);
  }
  return value;
}

function applyOperation(root: JsonValue, operation: PatchOperation): void {
  const tokens = pointerTokens(operation.path);
  if (tokens.length === 0) {
    throw new JsonPointerError("root replacement is not permitted");
  }
  let parent: JsonValue = root;
  for (const token of tokens.slice(0, -1)) {
    parent = childAt(parent, token);
  }
  const leaf = tokens[tokens.length - 1] as string;

  if (Array.isArray(parent)) {
    applyArrayOperation(parent, leaf, operation);
    return;
  }
  if (parent === null || typeof parent !== "object") {
    throw new JsonPointerError(`mutation parent at ${operation.path} is not a container`);
  }
  const object = parent as { [key: string]: JsonValue };
  const exists = Object.hasOwn(object, leaf);
  switch (operation.op) {
    case "add":
      if (exists) {
        throw new JsonPointerError(`add target ${operation.path} already exists`);
      }
      object[leaf] = cloneJson(operation.value);
      return;
    case "remove":
      if (!exists) {
        throw new JsonPointerError(`remove target ${operation.path} does not exist`);
      }
      delete object[leaf];
      return;
    case "replace":
      if (!exists) {
        throw new JsonPointerError(`replace target ${operation.path} does not exist`);
      }
      object[leaf] = cloneJson(operation.value);
      return;
  }
}

function applyArrayOperation(
  array: JsonValue[],
  token: string,
  operation: PatchOperation,
): void {
  if (operation.op === "add" && token === "-") {
    array.push(cloneJson(operation.value));
    return;
  }
  if (!/^(0|[1-9][0-9]*)$/.test(token)) {
    throw new JsonPointerError(`array index ${JSON.stringify(token)} is invalid`);
  }
  const index = Number(token);
  if (!Number.isSafeInteger(index)) {
    throw new JsonPointerError("array index is outside the safe integer range");
  }
  if (operation.op === "add") {
    if (index > array.length) {
      throw new JsonPointerError("array add index is past the end");
    }
    array.splice(index, 0, cloneJson(operation.value));
    return;
  }
  if (index >= array.length) {
    throw new JsonPointerError("array mutation index does not exist");
  }
  if (operation.op === "remove") {
    array.splice(index, 1);
  } else {
    array[index] = cloneJson(operation.value);
  }
}

function childAt(parent: JsonValue, token: string): JsonValue {
  if (Array.isArray(parent)) {
    if (!/^(0|[1-9][0-9]*)$/.test(token)) {
      throw new JsonPointerError(`array index ${JSON.stringify(token)} is invalid`);
    }
    const index = Number(token);
    const child = parent[index];
    if (child === undefined) {
      throw new JsonPointerError(`array index ${token} does not exist`);
    }
    return child;
  }
  if (parent === null || typeof parent !== "object") {
    throw new JsonPointerError("JSON Pointer traverses a scalar");
  }
  const object = parent as { [key: string]: JsonValue };
  if (!Object.hasOwn(object, token)) {
    throw new JsonPointerError(`object member ${JSON.stringify(token)} does not exist`);
  }
  return object[token] as JsonValue;
}

function pointerTokens(pointer: string): string[] {
  if (pointer === "") return [];
  if (!pointer.startsWith("/")) {
    throw new JsonPointerError("JSON Pointer must be empty or start with '/'");
  }
  return pointer.slice(1).split("/").map((token) => {
    if (/~(?:[^01]|$)/.test(token)) {
      throw new JsonPointerError("JSON Pointer contains an invalid '~' escape");
    }
    return token.replaceAll("~1", "/").replaceAll("~0", "~");
  });
}

function cloneJson(value: JsonValue): JsonValue {
  if (value === null || typeof value !== "object") return value;
  if (Array.isArray(value)) return value.map((entry) => cloneJson(entry));
  const clone: { [key: string]: JsonValue } = Object.create(null) as {
    [key: string]: JsonValue;
  };
  for (const key of Object.keys(value)) {
    clone[key] = cloneJson(value[key] as JsonValue);
  }
  return clone;
}
