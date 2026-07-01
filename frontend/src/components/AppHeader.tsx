import { ArrowLeft, LogOut, SlidersHorizontal } from "lucide-react";
import { type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/auth";

export default function AppHeader({ center }: { center?: ReactNode }) {
  const { signOut, isAdmin } = useAuth();
  const { pathname } = useLocation();
  const onHome = pathname === "/";

  return (
    <header className="sticky top-0 z-20 border-b bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-[1700px] items-center gap-3 px-4 md:px-6">
        <Link to="/" className="text-lg font-bold tracking-tight">
          Streamva
        </Link>
        {!onHome && (
          <Button asChild variant="ghost" size="sm">
            <Link to="/">
              <ArrowLeft />
              <span className="hidden sm:inline">Library</span>
            </Link>
          </Button>
        )}
        <div className="flex flex-1 justify-center px-2">{center}</div>
        <Button asChild variant="ghost" size="sm">
          <Link to="/settings">
            <SlidersHorizontal />
            <span className="hidden sm:inline">{isAdmin ? "Settings" : "Account"}</span>
          </Link>
        </Button>
        <Button variant="ghost" size="sm" onClick={() => void signOut()}>
          <LogOut />
          <span className="hidden sm:inline">Logout</span>
        </Button>
      </div>
    </header>
  );
}
