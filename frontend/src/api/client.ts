import type {
  HealthResponse,
  MetaResponse,
  EarningsLeaderboardResponse,
  StandingsResponse,
  HallOfFameResponse,
  TradesTrendsResponse,
  TransactionsSummaryResponse,
} from '@/types/api';

export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${BASE_URL}${endpoint}`;
  const response = await fetch(url, {
    headers: {
      Accept: 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let errorData: unknown = null;
    try {
      errorData = await response.json();
    } catch {
      // ignore json parse error
    }
    const message =
      (errorData && typeof errorData === 'object' && 'message' in errorData && typeof (errorData as Record<string, unknown>).message === 'string')
        ? (errorData as Record<string, unknown>).message as string
        : `HTTP error ${response.status}: ${response.statusText}`;
    throw new ApiError(message, response.status, errorData);
  }

  return (await response.json()) as T;
}

export async function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/api/v1/health');
}

export async function fetchMeta(): Promise<MetaResponse> {
  return request<MetaResponse>('/api/v1/meta');
}

export async function fetchEarningsLeaderboard(
  season?: number | null
): Promise<EarningsLeaderboardResponse> {
  const query = season != null ? `?season=${season}` : '';
  return request<EarningsLeaderboardResponse>(`/api/v1/earnings/leaderboard${query}`);
}

export async function fetchStandings(
  season?: number | string | null
): Promise<StandingsResponse> {
  const query = season !== undefined ? (season !== null ? `?season=${season}` : '?season=all') : '';
  return request<StandingsResponse>(`/api/v1/standings/current${query}`);
}

export async function fetchHallOfFame(
  season?: number | string | null
): Promise<HallOfFameResponse> {
  const query = season != null ? `?season=${season}` : '';
  return request<HallOfFameResponse>(`/api/v1/hall-of-fame${query}`);
}

export async function fetchTradeTrends(
  season?: number | null
): Promise<TradesTrendsResponse> {
  const query = season != null ? `?season=${season}` : '';
  return request<TradesTrendsResponse>(`/api/v1/trades/trends${query}`);
}

export async function fetchTransactionsSummary(
  season?: number | null
): Promise<TransactionsSummaryResponse> {
  const query = season != null ? `?season=${season}` : '';
  return request<TransactionsSummaryResponse>(`/api/v1/transactions/summary${query}`);
}

export const apiClient = {
  fetchHealth,
  fetchMeta,
  fetchEarningsLeaderboard,
  fetchStandings,
  fetchHallOfFame,
  fetchTradeTrends,
  fetchTransactionsSummary,
};

export default apiClient;
