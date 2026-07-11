import { Switch, Route, Router, Redirect } from "wouter";
import { useHashLocation } from "wouter/use-hash-location";
import { queryClient } from "./lib/queryClient";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider, useAuth } from "@/lib/auth";
import { ThemeProvider } from "@/lib/theme";
import { AppLayout } from "@/components/layout";
import LoginPage from "@/pages/login";
import DashboardPage from "@/pages/dashboard";
import ApplicationsListPage from "@/pages/applications-list";
import ApplicationDetailPage from "@/pages/application-detail";
import NewApplicationPage from "@/pages/new-application";
import { ClientsListPage, ClientDetailPage } from "@/pages/clients";
import NotificationsPage from "@/pages/notifications";
import AuditPage from "@/pages/audit";
import AdminPage from "@/pages/admin";
import NotFound from "@/pages/not-found";

function AuthenticatedRoutes() {
  const { user } = useAuth();

  return (
    <AppLayout>
      <Switch>
        <Route path="/dashboard" component={DashboardPage} />
        <Route path="/applications/new" component={NewApplicationPage} />
        <Route path="/applications/:id" component={ApplicationDetailPage} />
        <Route path="/applications" component={ApplicationsListPage} />
        {(user?.role !== "client") && <Route path="/clients/:id" component={ClientDetailPage} />}
        {(user?.role !== "client") && <Route path="/clients" component={ClientsListPage} />}
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
  const { isAuthenticated } = useAuth();

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
