export type TokenResponse = {
  access_token: string;
  token_type: string;
};

export type ChatMessage = {
  id: string;
  user_message: string;
  assistant_message: string;
  timestamp: string;
  chat_id: string;
  user_id: string;
};

export type ChatHistoryResponse = {
  messages: ChatMessage[];
  total: number;
};

// Prefer NEXT_PUBLIC_API_URL (as defined in next.config.js), but also support NEXT_PUBLIC_API_BASE_URL for backward compatibility.
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://127.0.0.1:8000/api/v1";

function getAuthHeaders() {
  if (typeof window === "undefined") return {} as Record<string, string>;
  const token = localStorage.getItem("access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function request<T>(path: string, init: RequestInit): Promise<T> {
  const normPath = path.startsWith("/") ? path : `/${path}`;
  const fullUrl = `${API_BASE_URL}${normPath}`;
  const method = init.method || 'GET';
  console.log(`🌐 Making ${method} request to: ${fullUrl}`);
  
  const res = await fetch(fullUrl, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
      ...(init.headers || {}),
    },
  });
  
  console.log(`📡 Response status: ${res.status} ${res.statusText}`);
  
  if (!res.ok) {
    // Try to extract a safe, concise error detail
    const contentType = res.headers.get("content-type") || "";
    let detail: string | undefined;
    if (contentType.includes("application/json")) {
      try {
        const json = await res.json();
        detail = (json && (json.detail || json.message)) || undefined;
        if (!detail) {
          // Fallback to a truncated JSON string if no standard field exists
          const jsonStr = JSON.stringify(json);
          detail = jsonStr.length > 300 ? jsonStr.slice(0, 300) + "…" : jsonStr;
        }
      } catch {
        // If JSON parsing fails, fall back to text
        detail = await res.text().catch(() => undefined);
      }
    } else {
      detail = await res.text().catch(() => undefined);
    }

    // Log a readable, stringified error to avoid {} in some consoles
    const baseMsg = `❌ Request failed ${method} ${fullUrl}: status=${res.status} ${res.statusText}`;
    console.error(detail ? `${baseMsg}, detail=${detail}` : baseMsg);
    if (res.status === 401) {
      try {
        if (typeof window !== "undefined") {
          localStorage.removeItem("access_token");
          localStorage.removeItem("token_type");
          // Redirect to signin for fresh login
          window.location.href = "/signin";
        }
      } catch {}
    }
    throw new Error(detail || `Request failed: ${res.status} ${res.statusText}`);
  }
  // Some endpoints (e.g., DELETE) return 204 No Content; attempting res.json() will throw.
  if (res.status === 204 || res.status === 205) {
    console.log(`✅ Request successful: No Content (${res.status})`);
    return undefined as unknown as T;
  }

  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    const text = await res.text().catch(() => "");
    console.log(`✅ Request successful (non-JSON):`, text);
    // Return undefined for non-JSON by default to avoid parsing errors
    return undefined as unknown as T;
  }

  const result = await res.json() as T;
  console.log(`✅ Request successful:`, result);
  return result;
}

export async function registerUser(args: { username: string; password: string; tenant_id?: string }): Promise<{ message: string }> {
  const { username, password, tenant_id = "default" } = args;
  return request<{ message: string }>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password, tenant_id }),
  });
}

export async function loginUser(args: { username: string; password: string }): Promise<TokenResponse> {
  return request<TokenResponse>(`/auth/login`, {
    method: "POST",
    body: JSON.stringify({ username: args.username, password: args.password }),
  });
}

export async function getLivekitToken(): Promise<{ token: string; room_name: string }> {
  return request("/livekit/generate_token", { method: "POST" });
}

export async function dispatchAgent(roomName: string): Promise<{ status: string; message: string }> {
  console.log('🤖📡 === DISPATCH AGENT API CALL ===');
  console.log('🤖 Room name:', roomName);
  console.log('🤖 API endpoint: /livekit/dispatch_agent');
  
  try {
    const result = await request<{ status: string; message: string }>("/livekit/dispatch_agent", { 
      method: "POST",
      body: JSON.stringify({ room_name: roomName })
    });
    console.log('🤖✅ Dispatch agent API call successful:', result);
    return result;
  } catch (error) {
    console.error('🤖❌ Dispatch agent API call failed:', error);
    throw error;
  }
}

export async function sendChatCompletion(args: { user_message: string; chat_id: string }, onChunk?: (t: string) => void): Promise<string> {
  const res = await fetch(`${API_BASE_URL}/chat/completions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify(args),
  });
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Chat failed: ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let full = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    full += chunk;
    onChunk?.(chunk);
  }
  return full;
}

export async function getChatHistory(args?: { limit?: number; offset?: number }): Promise<ChatHistoryResponse> {
  const { limit = 50, offset = 0 } = args || {};
  return request<ChatHistoryResponse>(`/history/chats?limit=${limit}&offset=${offset}`, {
    method: "GET",
  });
}

export async function getChatById(chatId: string, args?: { limit?: number; offset?: number }): Promise<ChatHistoryResponse> {
  const { limit = 50, offset = 0 } = args || {};
  return request<ChatHistoryResponse>(`/history/chats/${chatId}?limit=${limit}&offset=${offset}`, {
    method: "GET",
  });
}

// User management API
export type UserCreateRequest = {
  username: string;
  password: string;
  tenant_id: string;
  role?: string;
};

// Dishes API
export type Dish = { id: number; name: string };

export async function getDishes(): Promise<Dish[]> {
  // Используем путь с завершающим слешом, чтобы избежать лишних редиректов FastAPI
  return request<Dish[]>(`/dishes/`, { method: "GET" });
}

export async function deleteDish(dishId: number): Promise<void> {
  // Удаление блюда (только для админов на бэкенде)
  return request<void>(`/dishes/${dishId}`, { method: "DELETE" });
}

// Создание блюда (админ). Можно передать начальную цену/курс.
export async function createDish(args: { name: string; initial_price?: number | null; initial_rate?: number | null }): Promise<Dish> {
  const { name, initial_price = null, initial_rate = null } = args;
  return request<Dish>(`/dishes/`, {
    method: "POST",
    body: JSON.stringify({ name, initial_price, initial_rate }),
  });
}

export type UserUpdateRequest = {
  username?: string;
  password?: string;
  tenant_id?: string;
  role?: string;
};

export type User = {
  id: number;
  username: string;
  tenant_id: string;
  role: string;
};

export async function getAllUsers(): Promise<User[]> {
  return request<User[]>("/users/", { method: "GET" });
}

export async function createUser(userData: UserCreateRequest): Promise<User> {
  return request<User>("/users/", {
    method: "POST",
    body: JSON.stringify(userData),
  });
}

export async function updateUser(userId: number, userData: UserUpdateRequest): Promise<User> {
  return request<User>(`/users/${userId}`, {
    method: "PUT",
    body: JSON.stringify(userData),
  });
}

export async function deleteUser(userId: number): Promise<void> {
  return request<void>(`/users/${userId}`, { method: "DELETE" });
}

// Beer Exchange API
export type BeerExchangeItemAPI = {
  id: number;
  name: string;
  price: number | null;
  rate: number | null;
  stoplisted?: boolean;
};

export async function getBeerExchangeItems(): Promise<BeerExchangeItemAPI[]> {
  return request<BeerExchangeItemAPI[]>(`/beer-exchange/`, { method: "GET" });
}

// Prices API
export type PriceRead = {
  id: number;
  dish_id: number;
  value: number;
  created_at: string; // ISO timestamp
};

export async function listPrices(): Promise<PriceRead[]> {
  return request<PriceRead[]>(`/prices/`, { method: "GET" });
}

// Beer Exchange Settings API
export type DishSettingsRead = {
  id: number;
  dish_id: number;
  min_price?: number | null;
  max_price?: number | null;
  step?: number | null;
  base_price?: number | null;
  sales_quantity?: number | null;
  weight_grams?: number | null;
  ttl_minutes?: number | null;
  active: boolean;
};

export type DishSettingsCreate = {
  dish_id: number;
  min_price?: number | null;
  max_price?: number | null;
  step?: number | null;
  base_price?: number | null;
  sales_quantity?: number | null;
  weight_grams?: number | null;
  ttl_minutes?: number | null;
  active?: boolean;
};

export async function listBeerExchangeSettings(): Promise<DishSettingsRead[]> {
  return request<DishSettingsRead[]>(`/beer-exchange/settings/`, { method: "GET" });
}

export async function upsertBeerExchangeSettings(body: DishSettingsCreate): Promise<DishSettingsRead> {
  // Admin-only endpoint on backend; relies on Authorization header
  return request<DishSettingsRead>(`/beer-exchange/settings/`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export type ApplyBasePricesResultItem = {
  dish_id: number;
  name: string;
  product_id: string | null;
  base_price: number | null;
  pushed: boolean;
  error?: string | null;
};

export type ApplyBasePricesResponse = {
  applied: number;
  total: number;
  results: ApplyBasePricesResultItem[];
};

export async function applyBasePrices(): Promise<ApplyBasePricesResponse> {
  // Admin-only endpoint on backend; relies on Authorization header
  return request<ApplyBasePricesResponse>(`/beer-exchange/settings/apply-base-prices`, {
    method: "POST",
  });
}

// iiko products (admin-only)
export type IikoProduct = {
  id: string | null;
  name: string;
  price: number | null;
  code: string | null;
};

export async function getIikoProducts(): Promise<IikoProduct[]> {
  return request<IikoProduct[]>(`/iiko/products`, { method: "GET" });
}

export async function syncIikoMenu(): Promise<{ created_dishes: number; appended_prices: number; total_products: number }>{
  return request<{ created_dishes: number; appended_prices: number; total_products: number }>(`/iiko/sync`, { method: "POST" });
}

// iiko Integration Settings (admin-only)
export type IikoSettingsRead = {
  id: number;
  server_host?: string | null;
  server_login?: string | null;
  server_password?: string | null;
  active: boolean;
};

export type IikoSettingsCreate = {
  server_host?: string | null;
  server_login?: string | null;
  server_password?: string | null;
  active?: boolean;
};

export async function getIikoSettings(): Promise<IikoSettingsRead | null> {
  return request<IikoSettingsRead | null>(`/iiko/settings/`, { method: "GET" });
}

export async function upsertIikoSettings(body: IikoSettingsCreate): Promise<IikoSettingsRead> {
  return request<IikoSettingsRead>(`/iiko/settings/`, { method: "POST", body: JSON.stringify(body) });
}

export async function testIikoConnection(): Promise<{ status: string; mode?: string }> {
  return request<{ status: string; mode?: string }>(`/iiko/test-connection`, { method: "GET" });
}

export async function getAlgorithmStatus(): Promise<{ running: boolean; message?: string }>{
  return request<{ running: boolean; message?: string }>(`/beer-exchange/settings/algorithm/status`, { method: "GET" });
}

export async function enableAlgorithm(): Promise<{ running: boolean; message?: string }>{
  return request<{ running: boolean; message?: string }>(`/beer-exchange/settings/algorithm/enable`, { method: "POST" });
}

export async function disableAlgorithm(): Promise<{ running: boolean; message?: string }>{
  return request<{ running: boolean; message?: string }>(`/beer-exchange/settings/algorithm/disable`, { method: "POST" });
}

// Stream Settings API
export type StreamSettingsRead = {
  id: number;
  hls_url: string | null;
  active: boolean;
};

export type StreamSettingsCreate = {
  hls_url?: string | null;
  active?: boolean;
};

export async function getStreamSettings(): Promise<StreamSettingsRead | null> {
  return request<StreamSettingsRead | null>(`/stream-settings/`, { method: "GET" });
}

export async function upsertStreamSettings(body: StreamSettingsCreate): Promise<StreamSettingsRead> {
  return request<StreamSettingsRead>(`/stream-settings/`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// Bull & Sea
export type SyncSalesResponse = {
  updated: number;
  total: number;
  message: string;
  details?: {
    weights_found: number;
    sales_found: number;
  };
};

export async function syncSales(dateFrom?: string, dateTo?: string): Promise<SyncSalesResponse> {
  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  const qs = params.toString();
  return request<SyncSalesResponse>(`/bull-and-sea/sync-sales${qs ? `?${qs}` : ""}`, {
    method: "POST",
  });
}

export type AutoSyncStatus = {
  enabled: boolean;
  date_from: string | null;
  interval_seconds: number;
  task_running: boolean;
};

export async function startAutoSync(dateFrom: string): Promise<AutoSyncStatus> {
  return request<AutoSyncStatus>(`/bull-and-sea/auto-sync/start?date_from=${encodeURIComponent(dateFrom)}`, {
    method: "POST",
  });
}

export async function stopAutoSync(): Promise<AutoSyncStatus> {
  return request<AutoSyncStatus>(`/bull-and-sea/auto-sync/stop`, {
    method: "POST",
  });
}

export async function getAutoSyncStatus(): Promise<AutoSyncStatus> {
  return request<AutoSyncStatus>(`/bull-and-sea/auto-sync/status`, {
    method: "GET",
  });
}
