import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/auth";
import AuthGate from "@/components/AuthGate";
import CoursePage from "@/pages/CoursePage";
import Library from "@/pages/Library";
import Settings from "@/pages/Settings";
import "@/index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <AuthGate>
            <Routes>
              <Route path="/" element={<Library />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/course/:slug" element={<CoursePage />} />
            </Routes>
          </AuthGate>
        </BrowserRouter>
        <Toaster />
      </AuthProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
