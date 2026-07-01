import { GraduationCap } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/auth";

export default function AuthGate({ children }: { children: ReactNode }) {
  const { ready, user, needsSetup } = useAuth();
  if (!ready) {
    return <div className="grid min-h-screen place-items-center text-muted-foreground">Loading…</div>;
  }
  if (needsSetup) return <SetupScreen />;
  if (!user) return <LoginScreen />;
  return <>{children}</>;
}

function AuthShell({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="grid min-h-screen place-items-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <div className="mb-2 grid size-11 place-items-center rounded-xl bg-primary/15 text-primary">
            <GraduationCap className="size-6" />
          </div>
          <CardTitle className="text-2xl">{title}</CardTitle>
          <CardDescription>{subtitle}</CardDescription>
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </div>
  );
}

function SetupScreen() {
  const { signUp } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password.length < 4) return setErr("Password must be at least 4 characters");
    if (password !== confirm) return setErr("Passwords don't match");
    setBusy(true);
    setErr("");
    try {
      await signUp(username.trim(), password);
    } catch (e) {
      setErr(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Welcome to Streamva" subtitle="Create your admin account">
      <form className="space-y-3" onSubmit={submit}>
        <div className="space-y-1.5">
          <Label htmlFor="su-user">Username</Label>
          <Input id="su-user" autoFocus autoComplete="username" value={username}
            onChange={(e) => setUsername(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="su-pw">Password</Label>
          <Input id="su-pw" type="password" autoComplete="new-password" value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="su-pw2">Confirm password</Label>
          <Input id="su-pw2" type="password" autoComplete="new-password" value={confirm}
            onChange={(e) => setConfirm(e.target.value)} />
        </div>
        {err && <p className="text-sm text-destructive">{err}</p>}
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </Button>
      </form>
    </AuthShell>
  );
}

function LoginScreen() {
  const { signIn } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await signIn(username, password);
    } catch {
      setErr("Invalid username or password");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Streamva" subtitle="Sign in to continue">
      <form className="space-y-3" onSubmit={submit}>
        <div className="space-y-1.5">
          <Label htmlFor="li-user">Username</Label>
          <Input id="li-user" autoFocus autoComplete="username" value={username}
            onChange={(e) => setUsername(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="li-pw">Password</Label>
          <Input id="li-pw" type="password" autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </div>
        {err && <p className="text-sm text-destructive">{err}</p>}
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </AuthShell>
  );
}
