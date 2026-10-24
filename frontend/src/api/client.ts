import type {
  HealthResponse,
  MetaResponse,
  EarningsLeaderboardResponse,
  StandingsResponse,
  HallOfFameResponse,
  TradesTrendsResponse,
  TradeDetail,
  TransactionsSummaryResponse,
} from '@/types/api';

export type TradeAdminDraftPickInput = {
  season_year?: number;
  round: number;
  pick_number?: number | null;
};

export type TradeAdminSideInput = {
  team_id: number;
  player_ids: number[];
  draft_picks: TradeAdminDraftPickInput[];
  faab_received: number;
};

export type TradeAdminUpdatePayload = {
  week: number | null;
  sides: TradeAdminSideInput[];
};

export type TradeAdminCreatePayload = {
  season_year: number;
  week: number;
  sides: TradeAdminSideInput[];
};

export type TradeAdminTeamOption = {
  team_id: number;
  season_year: number;
  team_name: string;
  manager_id: number;
  manager_name: string;
  logo_url: string | null;
};

export type TradeAdminPlayerOption = {
  player_id: number;
  full_name: string;
  default_position: string;
  pro_team: string;
  headshot_url: string | null;
};

export type TradeAdminOptionsResponse = {
  seasons: number[];
  teams: TradeAdminTeamOption[];
  players: TradeAdminPlayerOption[];
  deleted_trades: TradeDetail[];
};

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

export async function verifyTradeAdminPassword(
  password: string
): Promise<{ authenticated: boolean }> {
  return request<{ authenticated: boolean }>('/api/v1/trades/admin/verify', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Password': password,
    },
    body: JSON.stringify({ password }),
  });
}

export async function fetchTradeAdminOptions(
  password: string
): Promise<TradeAdminOptionsResponse> {
  return request<TradeAdminOptionsResponse>('/api/v1/trades/admin/options', {
    headers: {
      'X-Admin-Password': password,
    },
  });
}

export async function updateTradeAdmin(
  password: string,
  tradeId: number,
  payload: TradeAdminUpdatePayload
): Promise<{ message: string; trade_id: number }> {
  return request<{ message: string; trade_id: number }>(`/api/v1/trades/${tradeId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Password': password,
    },
    body: JSON.stringify(payload),
  });
}

export async function createTradeAdmin(
  password: string,
  payload: TradeAdminCreatePayload
): Promise<{ message: string; trade_id: number }> {
  return request<{ message: string; trade_id: number }>('/api/v1/trades', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Password': password,
    },
    body: JSON.stringify(payload),
  });
}

export async function deleteTradeAdmin(
  password: string,
  tradeId: number
): Promise<{ message: string; trade_id: number }> {
  return request<{ message: string; trade_id: number }>(`/api/v1/trades/${tradeId}`, {
    method: 'DELETE',
    headers: {
      'X-Admin-Password': password,
    },
  });
}

export async function restoreTradeAdmin(
  password: string,
  tradeId: number
): Promise<{ message: string; trade_id: number }> {
  return request<{ message: string; trade_id: number }>(`/api/v1/trades/${tradeId}/restore`, {
    method: 'POST',
    headers: {
      'X-Admin-Password': password,
    },
  });
}

export const apiClient = {
  fetchHealth,
  fetchMeta,
  fetchEarningsLeaderboard,
  fetchStandings,
  fetchHallOfFame,
  fetchTradeTrends,
  fetchTransactionsSummary,
  verifyTradeAdminPassword,
  fetchTradeAdminOptions,
  updateTradeAdmin,
  createTradeAdmin,
  deleteTradeAdmin,
  restoreTradeAdmin,
};

export default apiClient;
