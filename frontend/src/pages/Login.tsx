import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { useAuthStatus } from "@/api/queries";

// L9: the OIDC callback redirects back here with ?error=... on failure.
const ERROR_MESSAGES: Record<string, string> = {
  oidc_exchange_failed: "We couldn't complete the OIDC login. Try again.",
  no_email: "Your OIDC provider didn't return an email address.",
  access_denied: "Your email is not on the allowlist.",
};

export function Login() {
  const status = useAuthStatus();
  const nav = useNavigate();
  const [signingIn, setSigningIn] = useState(false);
  const [params] = useSearchParams();
  const error = params.get("error");
  const errorMessage = error ? (ERROR_MESSAGES[error] ?? "Sign-in failed.") : null;

  useEffect(() => {
    if (status.data?.authenticated) nav("/", { replace: true });
  }, [status.data, nav]);

  return (
    <div className="flex h-screen items-center justify-center">
      <div className="w-full max-w-sm rounded-lg border border-border bg-muted/30 p-8 shadow-xl">
        <h1 className="text-xl font-semibold">pfSense Backup</h1>
        <p className="mt-1 text-sm text-muted-fg">Sign in with your OIDC provider.</p>

        {errorMessage && (
          <div
            role="alert"
            className="mt-4 rounded border border-danger/50 bg-danger/10 p-3 text-sm text-danger"
          >
            {errorMessage}
          </div>
        )}

        <Button
          size="lg"
          className="mt-6 w-full"
          disabled={signingIn}
          onClick={() => {
            setSigningIn(true);
            window.location.href = "/api/auth/login";
          }}
        >
          {signingIn ? "Redirecting…" : "Sign in"}
        </Button>
      </div>
    </div>
  );
}
