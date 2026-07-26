import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import type { User } from "@shared/schema";
import {
  api,
  ApiError,
  clearToken,
  getToken,
  setToken,
  setUnauthorizedHandler,
} from "./api";

interface AuthContextType {
  user: User | null;
  /** Возвращает текст ошибки или null при успехе. */
  login: (email: string, password: string) => Promise<string | null>;
  logout: () => void;
  /** Перечитать профиль после правки настроек. */
  refreshProfile: () => Promise<void>;
  isAuthenticated: boolean;
  /** Идёт восстановление сессии из сохранённого токена. */
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

interface TokenResponse {
  access_token: string;
  token_type: string;
}

/** Ответ API — snake_case, интерфейс User в приложении — camelCase. */
interface UserResponseDto {
  id: number;
  email: string;
  full_name: string | null;
  preferred_name: string | null;
  role: User["role"];
  is_active: boolean;
}

function toUser(dto: UserResponseDto): User {
  return {
    id: dto.id,
    email: dto.email,
    // full_name на сервере необязателен; подставляем email, чтобы
    // интерфейс не падал на пустом имени.
    fullName: dto.full_name || dto.email,
    preferredName: dto.preferred_name,
    role: dto.role,
    isActive: dto.is_active,
  };
}

async function fetchProfile(): Promise<User> {
  return toUser(await api.get<UserResponseDto>("/auth/me"));
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(!!getToken());

  const refreshProfile = async () => setUser(await fetchProfile());

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);

  // Истёкшая сессия должна возвращать пользователя ко входу,
  // а не оставлять его на экране с пустыми данными.
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
  }, []);

  // Восстановление сессии после перезагрузки страницы.
  useEffect(() => {
    if (!getToken()) {
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    fetchProfile()
      .then((profile) => {
        if (!cancelled) setUser(profile);
      })
      .catch(() => {
        if (!cancelled) clearToken();
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(
    async (email: string, password: string): Promise<string | null> => {
      try {
        const token = await api.post<TokenResponse>("/auth/login/json", {
          email,
          password,
        });
        setToken(token.access_token);
        setUser(await fetchProfile());
        return null;
      } catch (error) {
        clearToken();
        if (error instanceof ApiError) {
          return error.status === 401
            ? "Неверный адрес электронной почты или пароль."
            : error.message;
        }
        return "Не удалось связаться с сервером. Проверьте, запущен ли backend.";
      }
    },
    [],
  );

  return (
    <AuthContext.Provider
      value={{ user, login, logout, refreshProfile, isAuthenticated: !!user, isLoading }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
