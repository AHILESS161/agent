import { Switch, Route, Router, Redirect } from "wouter";
import { Loader2 } from "lucide-react";
import { useHashLocation } from "wouter/use-hash-location";
import { queryClient } from "./lib/queryClient";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider, useAuth } from "@/lib/auth";
import { ThemeProvider } from "@/lib/theme";
import { AppLayout } from "@/components/layout";
import { ClientPortalLayout } from "@/components/client-portal-layout";
import LoginPage from "@/pages/login";
import DashboardPage from "@/pages/dashboard";
import ApplicationsListPage from "@/pages/applications-list";
import ApplicationDetailPage from "@/pages/application-detail";
import IntakePage from "@/pages/intake";
import ProfilePage from "@/pages/profile";
import { ClientsListPage, ClientDetailPage } from "@/pages/clients";
import NotificationsPage from "@/pages/notifications";
import AuditPage from "@/pages/audit";
import AdminPage from "@/pages/admin";
import NotFound from "@/pages/not-found";
import ClientDashboardPage from "@/pages/client-dashboard";
import ClientApplicationPage from "@/pages/client-application";

function ClientRoutes() {
  return (
    <ClientPortalLayout>
      <Switch>
        <Route path="/dashboard" component={ClientDashboardPage} />
        <Route path="/start" component={IntakePage} />
        <Route path="/intake">
          <Redirect to="/start" />
        </Route>
        <Route path="/applications/new">
          <Redirect to="/start" />
        </Route>
        <Route path="/applications/:id" component={ClientApplicationPage} />
        <Route path="/applications">
          <Redirect to="/dashboard" />
        </Route>
        <Route path="/notifications" component={NotificationsPage} />
        <Route path="/profile" component={ProfilePage} />
        <Route path="/">
          <Redirect to="/dashboard" />
        </Route>
        <Route component={NotFound} />
      </Switch>
    </ClientPortalLayout>
  );
}

function AuthenticatedRoutes() {
  const { user } = useAuth();

  if (user?.role === "client") {
    return <ClientRoutes />;
  }

  return (
    <AppLayout>
      <Switch>
        <Route path="/dashboard" component={DashboardPage} />
        <Route path="/intake" component={IntakePage} />
        <Route path="/profile" component={ProfilePage} />
        <Route path="/applications/new">
          <Redirect to="/intake" />
        </Route>
        <Route path="/applications/:id" component={ApplicationDetailPage} />
        <Route path="/applications" component={ApplicationsListPage} />
        <Route path="/clients/:id" component={ClientDetailPage} />
        <Route path="/clients" component={ClientsListPage} />
        <Route path="/notifications" component={NotificationsPage} />
        {(user?.role === "admin" || user?.role === "lawyer") && <Route path="/audit" component={AuditPage} />}
        {user?.role === "admin" && <Route path="/admin" component={AdminPage} />}
        <Route path="/">
          <Redirect to="/dashboard" />
        </Route>
        <Route component={NotFound} />
      </Switch>
    </AppLayout>
  );
}

function AppRouter() {
  const { isAuthenticated, isLoading } = useAuth();

  // Пока восстанавливается сессия из сохранённого токена, показывать
  // экран входа нельзя — иначе он мигает при каждой перезагрузке.
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-sm">Загрузка…</span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return <AuthenticatedRoutes />;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <ThemeProvider>
          <AuthProvider>
            <Toaster />
            <Router hook={useHashLocation}>
              <AppRouter />
            </Router>
          </AuthProvider>
        </ThemeProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
