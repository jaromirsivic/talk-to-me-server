export function prettyJson(value) {
  return JSON.stringify(value, null, 2);
}

export function parseJson(source) {
  try {
    return {value: JSON.parse(source), error: null};
  } catch (error) {
    const position = Number(/position\s+(\d+)/i.exec(error.message)?.[1] ?? source.length);
    const before = source.slice(0, position);
    return {
      value: null,
      error: {
        line: before.split("\n").length,
        column: position - before.lastIndexOf("\n"),
        message: error.message,
      },
    };
  }
}
