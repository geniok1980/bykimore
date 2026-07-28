"use client";
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';

export interface UserInfo {
  id: number;
  username: string;
  tenant_id: string;
  role: string;
}

function decodeTokenPayload(token: string): Record<string, any> | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    return JSON.parse(atob(parts[1]));
  } catch { return null; }
}

export function useAuth() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserInfo | null>(null);
  const router = useRouter();

  const loadUserInfo = useCallback(async (authToken: string) => {
    try {
      const API_BASE =
        (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_API_URL) ||
        (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_API_BASE_URL) ||
        '';
      const url = API_BASE ? `${API_BASE}/users/me` : `/api/users/me`;

      const response = await fetch(url, {
        headers: { 'Authorization': `Bearer ${authToken}` },
        credentials: 'include',
      });

      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
      } else {
        console.warn('loadUserInfo: HTTP', response.status);
      }
    } catch (error) {
      console.error('loadUserInfo: fetch error:', error);
    }
  }, []);

  const initFromToken = useCallback((accessToken: string) => {
    const payload = decodeTokenPayload(accessToken);
    if (!payload) return false;

    const isExpired = (payload.exp * 1000) < Date.now();
    if (isExpired) return false;

    setToken(accessToken);
    setIsAuthenticated(true);

    // Извлекаем role из токена (если есть)
    if (payload.role) {
      setUser({
        id: parseInt(payload.sub || '0'),
        username: '',
        tenant_id: '',
        role: payload.role,
      });
    } else {
      // Старый токен — user пока null, загрузим через API
      setUser(null);
      loadUserInfo(accessToken);
    }
    return true;
  }, [loadUserInfo]);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const accessToken = localStorage.getItem('access_token');
      if (accessToken) {
        const ok = initFromToken(accessToken);
        if (!ok) {
          localStorage.removeItem('access_token');
          localStorage.removeItem('token_type');
          setToken(null);
          setIsAuthenticated(false);
        }
      } else {
        setToken(null);
        setIsAuthenticated(false);
      }
    }
  }, [initFromToken]);

  const logout = () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token');
      localStorage.removeItem('token_type');
    }
    setToken(null);
    setIsAuthenticated(false);
    setUser(null);
    router.push('/signin');
  };

  const loginFn = (accessToken: string, tokenType: string) => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('access_token', accessToken);
      localStorage.setItem('token_type', tokenType);
    }
    initFromToken(accessToken);
  };

  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin';
  const isSuperAdmin = user?.role === 'superadmin';

  return {
    isAuthenticated,
    token,
    user,
    isAdmin,
    isSuperAdmin,
    login: loginFn,
    logout,
  };
}
