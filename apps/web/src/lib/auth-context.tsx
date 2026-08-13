"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";

// =============================================================================
// Types
// =============================================================================

export interface User {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  email_verified: boolean;
  github_id: number | null;  // From OAuth login (UserIdentity)
  github_username: string | null;  // From OAuth login (UserIdentity)
  github_app_installed: boolean;  // True if GitHubConnection exists (for repo access)
  type: "personal" | "team";
  created_at: string | null;
  settings: {
    theme?: "light" | "dark";
    notifications?: {
      email?: boolean;
      push?: boolean;
      project_updates?: boolean;
      team_invites?: boolean;
    };
  };
}

interface SignupResult {
  needsVerification: boolean;
  email: string;
  message: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  pendingVerificationEmail: string | null;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, displayName: string) => Promise<SignupResult>;
  verifyEmail: (email: string, code: string) => Promise<void>;
  resendVerificationCode: (email: string) => Promise<void>;
  forgotPassword: (email: string) => Promise<void>;
  resetPassword: (email: string, code: string, newPassword: string) => Promise<void>;
  loginWithGitHub: () => void;
  loginWithGoogle: () => void;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  clearPendingVerification: () => void;
}

// =============================================================================
// Context
// =============================================================================

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// =============================================================================
// Provider
// =============================================================================

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [pendingVerificationEmail, setPendingVerificationEmail] = useState<string | null>(null);
  const [initialAuthResolved, setInitialAuthResolved] = useState(false);

  const syncAccessTokenCookie = useCallback((token: string | null) => {
    if (typeof document === "undefined") return;
    if (!token) {
      document.cookie = "access_token=; path=/; max-age=0; samesite=lax";
      return;
    }
    document.cookie = `access_token=${encodeURIComponent(token)}; path=/; max-age=${60 * 60 * 24 * 7}; samesite=lax`;
  }, []);

  // Single startup effect: resolve localStorage tokens + OAuth/cookie check in one pass
  // so isLoading stays true until we definitively know the auth state.
  useEffect(() => {
    if (initialAuthResolved) return;
    setInitialAuthResolved(true);

    const storedToken = localStorage.getItem("access_token");
    const storedRefresh = localStorage.getItem("refresh_token");
    if (storedToken) {
      syncAccessTokenCookie(storedToken);
      setAccessToken(storedToken);
    }
    if (storedRefresh) {
      setRefreshToken(storedRefresh);
    }

    const params = new URLSearchParams(window.location.search);
    const authStatus = params.get("auth");
    const githubLogin = params.get("github");
    const googleEmail = params.get("email");
    const provider = params.get("provider");
    const githubLinked = params.get("github_linked");

    const isOAuthCallback =
      githubLinked === "true" ||
      (authStatus === "success" && (githubLogin || googleEmail || provider));
    const isOAuthError = authStatus === "error";

    if (isOAuthCallback) {
      if (githubLinked === "true") {
        console.log("[Auth] GitHub linked successfully, refreshing user...");
      }
      window.history.replaceState({}, "", window.location.pathname);
      fetchUserFromCookie().finally(() => setIsLoading(false));
    } else if (isOAuthError) {
      console.error("OAuth error:", params.get("message"));
      window.history.replaceState({}, "", window.location.pathname);
      setIsLoading(false);
    } else if (storedToken) {
      fetchUser(storedToken).finally(() => setIsLoading(false));
    } else {
      fetchUserFromCookie().finally(() => setIsLoading(false));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep cookie in sync when token changes after initial mount (e.g. login, refresh).
  // We track the token that was already handled during initial resolution to avoid a
  // duplicate /me fetch.
  const initialTokenRef = React.useRef<string | null>(null);
  if (!initialAuthResolved && typeof window !== "undefined") {
    initialTokenRef.current = localStorage.getItem("access_token");
  }

  useEffect(() => {
    if (!initialAuthResolved) return;
    if (!accessToken) return;
    if (accessToken === initialTokenRef.current) {
      initialTokenRef.current = null;
      return;
    }
    syncAccessTokenCookie(accessToken);
    fetchUser(accessToken);
  }, [accessToken, syncAccessTokenCookie, initialAuthResolved]);

  const fetchUser = async (token: string) => {
    try {
      const response = await fetch(`${API_URL}/api/auth/me`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
        credentials: "include",
      });

      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
      } else if (response.status === 401 && refreshToken) {
        // Try to refresh token
        const refreshed = await tryRefreshToken();
        if (!refreshed) {
          clearSession();
        }
      } else {
        clearSession();
      }
    } catch (error) {
      // Network errors expected in demo mode when backend isn't running
      console.log("[Auth] Backend not available - running in demo mode");
      setUser(null);
    }
  };

  // Fetch user using cookie session (for OAuth flows)
  const fetchUserFromCookie = async () => {
    // Only run on client side
    if (typeof window === 'undefined') return;
    
    console.log("[Auth] Fetching user from cookie session...");
    console.log("[Auth] API_URL:", API_URL);
    
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);
      
      const response = await fetch(`${API_URL}/api/auth/me`, {
        credentials: "include", // Include cookies
        signal: controller.signal,
      });
      
      clearTimeout(timeoutId);

      console.log("[Auth] Response status:", response.status);
      
      if (response.ok) {
        const userData = await response.json();
        console.log("[Auth] User data received:", userData);
        setUser(userData);
      } else {
        const errorText = await response.text();
        console.log("[Auth] Not authenticated:", errorText);
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        // Timeout is expected in demo mode when backend isn't running
        console.log("[Auth] Backend not available - running in demo mode");
      } else if (error instanceof TypeError && error.message.includes('fetch')) {
        // Network error - backend not running
        console.log("[Auth] Backend not available - running in demo mode");
      } else {
        console.log("[Auth] Not authenticated:", error);
      }
      // Don't crash - just means user is not authenticated via cookie (demo mode)
    }
  };

  const tryRefreshToken = async (): Promise<boolean> => {
    if (!refreshToken) return false;
    
    try {
      const response = await fetch(`${API_URL}/api/auth/refresh`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (response.ok) {
        const data = await response.json();
        localStorage.setItem("access_token", data.access_token);
        if (data.refresh_token) {
          localStorage.setItem("refresh_token", data.refresh_token);
          setRefreshToken(data.refresh_token);
        }
        setAccessToken(data.access_token);
        setUser(data.user);
        return true;
      }
    } catch (error) {
      console.error("Failed to refresh token:", error);
    }
    
    return false;
  };

  const clearSession = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    syncAccessTokenCookie(null);
    setAccessToken(null);
    setRefreshToken(null);
    setUser(null);
  };

  const login = useCallback(async (email: string, password: string) => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({ email, password }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Login failed");
      }

      const data = await response.json();
      
      // Store tokens
      localStorage.setItem("access_token", data.access_token);
      if (data.refresh_token) {
        localStorage.setItem("refresh_token", data.refresh_token);
        setRefreshToken(data.refresh_token);
      }
      setAccessToken(data.access_token);
      setUser(data.user);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const signup = useCallback(async (
    email: string, 
    password: string, 
    displayName: string
  ): Promise<SignupResult> => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/auth/signup`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({ email, password, display_name: displayName }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Signup failed");
      }

      const data = await response.json();
      
      if (!data.confirmed) {
        // Need email verification (Cognito mode)
        setPendingVerificationEmail(email);
        return {
          needsVerification: true,
          email,
          message: data.message || "Please check your email for verification code",
        };
      }
      
      // Mock mode - auto login after signup
      // Re-login to get session
      await login(email, password);
      
      return {
        needsVerification: false,
        email,
        message: data.message || "Account created successfully",
      };
    } finally {
      setIsLoading(false);
    }
  }, [login]);

  const verifyEmail = useCallback(async (email: string, code: string) => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/auth/verify`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",  // Send cookies for Cognito token
        body: JSON.stringify({ email, code }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Verification failed");
      }

      // Clear pending verification
      setPendingVerificationEmail(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const resendVerificationCode = useCallback(async (email: string) => {
    const response = await fetch(`${API_URL}/api/auth/resend-code`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",  // Send cookies for Cognito token
      body: JSON.stringify({ email }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Failed to resend code");
    }
  }, []);

  const forgotPassword = useCallback(async (email: string) => {
    const response = await fetch(`${API_URL}/api/auth/forgot-password`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Failed to send reset code");
    }
  }, []);

  const resetPassword = useCallback(async (email: string, code: string, newPassword: string) => {
    const response = await fetch(`${API_URL}/api/auth/reset-password`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email, code, new_password: newPassword }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Failed to reset password");
    }
  }, []);

  const clearPendingVerification = useCallback(() => {
    setPendingVerificationEmail(null);
  }, []);

  const loginWithGitHub = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/auth/github`, {
        credentials: "include",
      });
      const data = await response.json().catch(() => ({}));
      if (data.auth_url) {
        window.location.href = data.auth_url;
        return;
      }
      console.error("No auth_url returned from GitHub OAuth endpoint", data);
    } catch {
      console.error("Failed to initiate GitHub OAuth");
    }
  }, []);

  const loginWithGoogle = useCallback(async () => {
    try {
      // Get the auth URL from backend
      const response = await fetch(`${API_URL}/api/auth/google`, {
        credentials: "include",
      });
      
      if (response.ok) {
        const data = await response.json();
        window.location.href = data.auth_url;
      } else {
        // Fallback to direct redirect
        window.location.href = `${API_URL}/api/auth/google`;
      }
    } catch {
      // Fallback to direct redirect
      window.location.href = `${API_URL}/api/auth/google`;
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await fetch(`${API_URL}/api/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch (error) {
      console.error("Logout error:", error);
    } finally {
      clearSession();
    }
  }, []);

  const refreshUser = useCallback(async () => {
    const token = localStorage.getItem("access_token");
    if (token) {
      await fetchUser(token);
    } else {
      // Try cookie-based session
      await fetchUserFromCookie();
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        pendingVerificationEmail,
        login,
        signup,
        verifyEmail,
        resendVerificationCode,
        forgotPassword,
        resetPassword,
        loginWithGitHub,
        loginWithGoogle,
        logout,
        refreshUser,
        clearPendingVerification,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// =============================================================================
// Hook
// =============================================================================

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
