export async function postApi(operation, payload) {
  const response = await fetch(`/api/v1/${operation}`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  let body;
  try {
    body = await response.json();
  } catch (error) {
    throw new Error(`Server returned an unreadable response (${response.status})`, {cause: error});
  }
  return {status: response.status, body};
}

export async function postMultipart(operation, payload) {
  const response = await fetch(`/api/v1/${operation}`, {
    method: "POST",
    body: payload,
  });
  const body = await response.json();
  return {status: response.status, body};
}
