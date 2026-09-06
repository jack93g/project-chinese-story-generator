const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL;

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export type VocabularyListSummary = {
  id: number;
  name: string;
  item_count: number;
};

export type VocabularyListsResponse = {
  items: VocabularyListSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type CreateStoryGenerationPayload = {
  vocabulary_list_id: number;
  target_hsk_level: number;
  target_word_count: number;
  target_vocabulary_count: number;
  topic?: string | null;
};

export type StoryGenerationCreated = {
  id: number;
  status: string;
};

export type VocabularyGlossaryItem = {
  id: number;
  skritter_vocab_id: string;
  language: string;
  writing: string;
  reading: string | null;
  definition_en: string | null;
};

export type StoryDetail = {
  id: number;
  title: string;
  created_at: string;
  target_hsk: number;
  content: string;
  selected_vocabulary: VocabularyGlossaryItem[];
};

async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") {
        return detail;
      }
      if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0] as { msg?: unknown };
        if (typeof first?.msg === "string") {
          return first.msg;
        }
      }
    }
  } catch {
    // Fall through to the generic message below.
  }
  return `Request failed with status ${response.status}`;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), init);
  if (!response.ok) {
    throw new ApiError(await parseErrorMessage(response), response.status);
  }
  return response.json() as Promise<T>;
}

const VOCABULARY_LISTS_PAGE_SIZE = 100;

export function fetchVocabularyLists(
  params: { limit?: number; offset?: number } = {},
): Promise<VocabularyListsResponse> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) {
    query.set("limit", String(params.limit));
  }
  if (params.offset !== undefined) {
    query.set("offset", String(params.offset));
  }
  const queryString = query.toString();
  return requestJson<VocabularyListsResponse>(
    `/vocabulary-lists${queryString ? `?${queryString}` : ""}`,
  );
}

export async function fetchAllVocabularyLists(
  pageSize: number = VOCABULARY_LISTS_PAGE_SIZE,
): Promise<VocabularyListSummary[]> {
  const items: VocabularyListSummary[] = [];
  let offset = 0;

  while (true) {
    const page = await fetchVocabularyLists({ limit: pageSize, offset });
    items.push(...page.items);
    offset += page.items.length;
    // A short page (fewer items than requested) means we've reached the
    // end, regardless of what `total` claims — this guarantees the loop
    // terminates even if `total` is wrong or stale.
    if (page.items.length < pageSize || items.length >= page.total) {
      break;
    }
  }

  return items;
}

export function fetchStory(id: number | string): Promise<StoryDetail> {
  return requestJson<StoryDetail>(`/stories/${id}`);
}

export function createStoryGeneration(
  payload: CreateStoryGenerationPayload,
): Promise<StoryGenerationCreated> {
  return requestJson<StoryGenerationCreated>("/story-generations", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
}
