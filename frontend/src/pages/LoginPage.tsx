import { useState, type FormEvent } from "react";
import { Fingerprint, LogIn } from "lucide-react";

import { ApiError } from "@/api/client";
import { useLogin } from "@/api/queries";
import { Button } from "@/components/ui";
import { useI18n } from "@/i18n";

export function LoginPage() {
  const { t } = useI18n();
  const login = useLogin();
  const [password, setPassword] = useState("");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!password.trim()) return;
    login.mutate(password);
  };

  const errorMessage =
    login.error instanceof ApiError && login.error.status === 401
      ? t("login.error")
      : login.error instanceof Error
        ? login.error.message
        : null;

  return (
    <div className="login-screen">
      <div className="login-screen__glow" aria-hidden="true" />
      <div className="login-card">
        <div className="login-brand">
          <span className="brand__mark">R</span>
          <div>
            <strong>RUN</strong>
            <small>{t("app.tagline")}</small>
          </div>
        </div>

        <div className="login-card__head">
          <span className="login-card__icon">
            <Fingerprint size={22} aria-hidden="true" />
          </span>
          <h1>{t("login.title")}</h1>
          <p>{t("login.subtitle")}</p>
        </div>

        <form className="login-form" onSubmit={submit}>
          <label>
            <span>{t("login.password")}</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              autoFocus
              required
            />
          </label>
          {errorMessage ? (
            <p className="form-error" role="alert">
              {errorMessage}
            </p>
          ) : null}
          <Button
            type="submit"
            variant="primary"
            size="lg"
            loading={login.isPending}
            disabled={!password.trim()}
          >
            <LogIn size={16} aria-hidden="true" />
            {login.isPending ? t("login.submitting") : t("login.submit")}
          </Button>
        </form>

        <p className="login-footer">
          <span className="mono">GPL-3.0</span>
          <span>{t("app.local")}</span>
        </p>
      </div>
    </div>
  );
}
