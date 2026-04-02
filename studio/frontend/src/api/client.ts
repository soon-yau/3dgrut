const base = "";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`${r.status} ${t}`);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}
