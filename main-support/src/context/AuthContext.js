import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [serverMode, setServerMode] = useState(false);
  const [user, setUser] = useState(null); // {id, username, role, permissions}
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const cfgRes = await fetch('/api/server-config');
      const cfg = await cfgRes.json();
      setServerMode(!!cfg.serverMode);

      const meRes = await fetch('/api/me');
      if (meRes.ok) {
        const me = await meRes.json();
        setUser(me);
      } else {
        setUser(null);
      }
    } catch (e) {
      console.error('認証状態の取得に失敗:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = async (username, password) => {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || 'ログインに失敗しました');
    }
    setUser(data.user);
    return data.user;
  };

  const logout = async () => {
    await fetch('/api/logout', { method: 'POST' });
    setUser(null);
  };

  // role: 'admin' は常に true。'editor' はカテゴリ/アイテム単位の権限を見る。'viewer' は常にfalse。
  const canEdit = (category, item) => {
    if (!serverMode) return true; // 通常起動時は全員編集可
    if (!user) return false;
    if (user.role === 'admin') return true;
    if (user.role === 'viewer') return false;
    const perm = (user.permissions || {})[category];
    if (!perm) return false;
    if (perm.all) return true;
    if (item && (perm.items || []).includes(item)) return true;
    return false;
  };

  const value = {
    serverMode,
    user,
    loading,
    isAdmin: !!user && user.role === 'admin',
    login,
    logout,
    refresh,
    canEdit,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth は AuthProvider の内側で使用してください');
  }
  return ctx;
}
