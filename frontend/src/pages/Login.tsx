import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { useAuthStatus } from "@/api/queries";

export function Login() {
  const status = useAuthStatus();
  const nav = useNavigate();
  const [signingIn, setSigningIn] = useState(false);

  useEffect(() => {
    if (status.data?.authenticated) nav("/", { replace: true });
  }, [status.data, nav]);

  return (
    <div className="flex h-screen items-center justify-center">
      <div className="w-full max-w-sm rounded-lg border border-border bg-muted/30 p-8 shadow-xl">
        <h1 className="text-xl font-semibold">pfSense Backup</h1>
        <p className="mt-1 text-sm text-muted-fg">Sign in with your OIDC provider.</p>

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
