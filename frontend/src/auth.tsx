import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import {
  getStatus,
  login as apiLogin,
  logout as apiLogout,
  setupAdmin,
  setUnauthorizedHandler,
} from "./api";

interface AuthCtx {
  ready: boolean;
  user: string | null;
  isAdmin: boolean;
  authDisabled: boolean;
  needsSetup: boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signUp: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const Ctx = createContext<AuthCtx | null>(null);

export function useAuth(): AuthCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth must be used within <AuthProvider>");
  return c;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [authDisabled, setAuthDisabled] = useState(false);
  const [needsSetup, setNeedsSetup] = useState(false);

  const refresh = useCallback(async () => {
    const s = await getStatus();
    setAuthDisabled(s.authDisabled);
    setNeedsSetup(s.needsSetup);
    setUser(s.user ? s.user.username : null);
    setIsAdmin(s.user ? s.user.isAdmin : false);
    setReady(true);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null)); // session expired mid-use -> back to login
    void refresh();
    return () => setUnauthorizedHandler(null);
  }, [refresh]);

  const signIn = async (username: string, password: string) => {
    const me = await apiLogin(username, password);
    setUser(me.username);
    setIsAdmin(me.isAdmin);
    setAuthDisabled(me.authDisabled);
  };
  const signUp = async (username: string, password: string) => {
    await setupAdmin(username, password);
    await refresh();
  };
  const signOut = async () => {
    await apiLogout();
    setUser(null);
    setIsAdmin(false);
  };

  return (
    <Ctx.Provider
      value={{ ready, user, isAdmin, authDisabled, needsSetup, signIn, signUp, signOut }}
    >
      {children}
    </Ctx.Provider>
  );
}
