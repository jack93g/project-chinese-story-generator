import { getAccessKey, reportAccessKeyRejected } from "./access-key";

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

export type GenerationStatusValue = "queued" | "running" | "succeeded" | "failed";

export type GenerationStatus = {
  id: number;
  status: GenerationStatusValue;
  error_code: string | null;
  error_message: string | null;
  story_id: number | null;
};

export type VocabularyGlossaryItem = {
  id: number;
  skritter_vocab_id: string;
  language: string;
  writing: string;
  reading: string | null;
  definition_en: string | null;
};

export type StorySummary = {
  id: number;
  title: string;
  created_at: string;
  target_hsk: number | null;
};

export type StoriesResponse = {
  items: StorySummary[];
  total: number;
  limit: number;
  offset: number;
};

export type StoryDetail = StorySummary & {
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

// Every API call goes through here so the access key header is added in one
// place and a rejected key (401) is handled in one place.
async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const accessKey = getAccessKey();
  let requestInit = init;
  if (accessKey) {
    const headers = new Headers(init?.headers);
    headers.set("X-API-Key", accessKey);
    requestInit = { ...init, headers };
  }

  const response = await fetch(apiUrl(path), requestInit);
  if (response.status === 401) {
    reportAccessKeyRejected();
  }
  return response;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    throw new ApiError(await parseErrorMessage(response), response.status);
  }
  return response.json() as Promise<T>;
}

function buildQueryPath(
  path: string,
  params: { limit?: number; offset?: number },
): string {
  const query = new URLSearchParams();
  if (params.limit !== undefined) {
    query.set("limit", String(params.limit));
  }
  if (params.offset !== undefined) {
    query.set("offset", String(params.offset));
  }
  const queryString = query.toString();
  return `${path}${queryString ? `?${queryString}` : ""}`;
}

async function fetchAllPages<TItem>(
  fetchPage: (params: {
    limit: number;
    offset: number;
  }) => Promise<{ items: TItem[]; total: number }>,
  pageSize: number,
): Promise<TItem[]> {
  const items: TItem[] = [];
  let offset = 0;

  while (true) {
    const page = await fetchPage({ limit: pageSize, offset });
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

const VOCABULARY_LISTS_PAGE_SIZE = 100;

export function fetchVocabularyLists(
  params: { limit?: number; offset?: number } = {},
): Promise<VocabularyListsResponse> {
  return requestJson<VocabularyListsResponse>(
    buildQueryPath("/vocabulary-lists", params),
  );
}

export function fetchAllVocabularyLists(
  pageSize: number = VOCABULARY_LISTS_PAGE_SIZE,
): Promise<VocabularyListSummary[]> {
  return fetchAllPages(fetchVocabularyLists, pageSize);
}

const STORIES_PAGE_SIZE = 100;

export function fetchStories(
  params: { limit?: number; offset?: number } = {},
): Promise<StoriesResponse> {
  return requestJson<StoriesResponse>(buildQueryPath("/stories", params));
}

export function fetchAllStories(
  pageSize: number = STORIES_PAGE_SIZE,
): Promise<StorySummary[]> {
  return fetchAllPages(fetchStories, pageSize);
}

export function fetchStory(id: number | string): Promise<StoryDetail> {
  return requestJson<StoryDetail>(`/stories/${encodeURIComponent(id)}`);
}

export async function deleteStory(id: number | string): Promise<void> {
  const response = await apiFetch(`/stories/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new ApiError(await parseErrorMessage(response), response.status);
  }
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

export function fetchGenerationStatus(id: number): Promise<GenerationStatus> {
  return requestJson<GenerationStatus>(`/story-generations/${id}`);
}

export function retryStoryGeneration(id: number): Promise<GenerationStatus> {
  return requestJson<GenerationStatus>(`/story-generations/${id}/retry`, {
    method: "POST",
  });
}
