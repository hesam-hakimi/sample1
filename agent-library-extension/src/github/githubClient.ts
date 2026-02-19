import * as vscode from 'vscode';
import { getCache, setCache } from './cache';
import { toRawUrl } from './urls';

export type FetchIndexInput = {
  context: vscode.ExtensionContext;
  key: string;
  repo: string;
  ref: string;
  indexPath: string;
  maxBytes: number;
  timeoutMs?: number;
};

async function fetchTextWithLimit(url: string, headers: HeadersInit, maxBytes: number, timeoutMs = 20_000): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { headers, signal: controller.signal });
    const len = Number(res.headers.get('content-length') || '0');
    if (len > maxBytes) throw new Error(`Content too large (${len} bytes > ${maxBytes}).`);
    return res;
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchIndex(input: FetchIndexInput): Promise<string> {
  const url = toRawUrl(input.repo, input.ref, input.indexPath);
  const cache = await getCache(input.context, input.key);
  const headers: HeadersInit = {};
  if (cache.etag) headers['If-None-Match'] = cache.etag;

  const res = await fetchTextWithLimit(url, headers, input.maxBytes, input.timeoutMs);
  if (res.status === 304 && cache.body) return cache.body;
  if (!res.ok) throw new Error(`Failed to fetch index (${res.status}) from ${url}`);

  const body = await res.text();
  if (Buffer.byteLength(body, 'utf8') > input.maxBytes) {
    throw new Error(`Index exceeds max bytes (${input.maxBytes}).`);
  }

  await setCache(input.context, input.key, {
    etag: res.headers.get('etag') ?? undefined,
    body,
    fetchedAt: new Date().toISOString()
  });
  return body;
}

export async function fetchItemContent(repo: string, ref: string, itemPath: string, maxBytes: number): Promise<Uint8Array> {
  const url = toRawUrl(repo, ref, itemPath);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch item ${itemPath} (${res.status}).`);
  const buffer = new Uint8Array(await res.arrayBuffer());
  if (buffer.byteLength > maxBytes) throw new Error(`Item ${itemPath} too large.`);
  return buffer;
}
