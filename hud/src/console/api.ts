export interface Card {
  question: string;
  lead: string;
  points: string[];
  source: string | null;
  live: boolean;
}

export interface Entry {
  id: string;
  qtype: string;
  audience: string;
  question: string;
  variants: string[];
  card: Card;
  parent: string | null;
  edited: boolean;
  hits: number;
}

export interface Gap {
  question: string;
  problems: string[];
}

export interface Doc {
  alias: string;
  name: string;
  role: 'main' | 'evidence';
  pages: number;
  titles: string[];
}

export interface Status {
  fake: boolean;
  backend: 'spark' | 'glimmer' | 'stand-in';
  model: string;
  stt: boolean;
  mode: 'qa' | 'present';
  listening: boolean;
  hud_clients: number;
  prep: {
    running: boolean;
    message: string;
    error: string | null;
    vision_pages?: number;
    stats?: {questions: number; cards: number; first_try: number; retried: number; gaps: number; drafts: number};
  };
}

export interface PathStats {
  count: number;
  first_p50: number | null;
  first_p95: number | null;
  rendered_p50: number | null;
  rendered_p95: number | null;
}

export interface QuestionRecord {
  id: string;
  question: string;
  path: 'bank' | 'live' | 'none';
  qtype?: string;
  score?: number | null;
  first?: number;
  card?: number;
  rendered?: number;
  error?: string;
}

export interface Stats {
  questions: number;
  hit_rate: number | null;
  paths: {bank: PathStats; live: PathStats};
  recent: QuestionRecord[];
  cache: {task: string; prompt: number; cached: number; ms: number}[];
}

export interface PageNotes {
  page: number;
  points: string[];
  bridge: string;
  short: string;
  support: string;
  support_source: string;
}

/** Hub base URL: same origin by default, or ?hub=http://host:8000 */
export const HUB = new URLSearchParams(location.search).get('hub') ?? '';

export async function api<T>(path: string, init?: RequestInit & {json?: unknown}): Promise<T> {
  const {json, ...rest} = init ?? {};
  const response = await fetch(HUB + path, {
    ...rest,
    headers: json === undefined ? rest.headers : {'Content-Type': 'application/json'},
    body: json === undefined ? rest.body : JSON.stringify(json),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export function wsUrl(path: string): string {
  const base = HUB || location.origin;
  return base.replace(/^http/, 'ws') + path;
}
