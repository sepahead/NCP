/** Reject duplicate object keys at every depth in an already-valid JSON string. */
export function rejectDuplicateJsonObjectKeys(text, context) {
  let index = 0
  const maximumDepth = 64
  const fail = (message) => {
    throw new Error(`${context} ${message}`)
  }
  const skipWhitespace = () => {
    while (index < text.length && /\s/.test(text[index])) index += 1
  }
  const parseString = () => {
    const start = index
    index += 1
    let escaped = false
    while (index < text.length) {
      const character = text[index]
      index += 1
      if (escaped) escaped = false
      else if (character === '\\') escaped = true
      else if (character === '"') return JSON.parse(text.slice(start, index))
    }
    fail('has an unterminated string')
  }
  const scanValue = (depth) => {
    if (depth > maximumDepth) fail('exceeds the JSON nesting limit')
    skipWhitespace()
    const character = text[index]
    if (character === '{') {
      index += 1
      const keys = new Set()
      skipWhitespace()
      if (text[index] === '}') {
        index += 1
        return
      }
      while (index < text.length) {
        skipWhitespace()
        if (text[index] !== '"') fail('has a non-string object key')
        const key = parseString()
        if (keys.has(key)) fail(`contains duplicate object key ${JSON.stringify(key)}`)
        keys.add(key)
        skipWhitespace()
        if (text[index] !== ':') fail('has a malformed object member')
        index += 1
        scanValue(depth + 1)
        skipWhitespace()
        if (text[index] === '}') {
          index += 1
          return
        }
        if (text[index] !== ',') fail('has a malformed object separator')
        index += 1
      }
      fail('has an unterminated object')
    }
    if (character === '[') {
      index += 1
      skipWhitespace()
      if (text[index] === ']') {
        index += 1
        return
      }
      while (index < text.length) {
        scanValue(depth + 1)
        skipWhitespace()
        if (text[index] === ']') {
          index += 1
          return
        }
        if (text[index] !== ',') fail('has a malformed array separator')
        index += 1
      }
      fail('has an unterminated array')
    }
    if (character === '"') {
      parseString()
      return
    }
    const start = index
    while (index < text.length && !/[\s,\]}]/.test(text[index])) index += 1
    if (index === start) fail('has a malformed scalar')
  }

  scanValue(0)
  skipWhitespace()
  if (index !== text.length) fail('has trailing JSON content')
}

/** Parse one strict JSON object without allowing duplicate keys. */
export function parseUniqueJsonObject(raw, context) {
  let value
  try {
    value = JSON.parse(raw)
  } catch (error) {
    throw new Error(`${context} is not valid JSON: ${error.message}`)
  }
  rejectDuplicateJsonObjectKeys(raw, context)
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${context} must contain one object`)
  }
  return value
}
