import { Link, Route, Routes } from "react-router-dom";
import { EmptyState } from "./components/Feedback";
import { Layout } from "./components/Layout";
import { DashboardPage } from "./pages/DashboardPage";
import { ItemDetailPage } from "./pages/ItemDetailPage";
import { ItemsPage } from "./pages/ItemsPage";
import { MemberDetailPage } from "./pages/MemberDetailPage";
import { MembersPage } from "./pages/MembersPage";
import { OutboxPage } from "./pages/OutboxPage";
import { OverduePage } from "./pages/OverduePage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="items" element={<ItemsPage />} />
        <Route path="items/:itemId" element={<ItemDetailPage />} />
        <Route path="members" element={<MembersPage />} />
        <Route path="members/:memberId" element={<MemberDetailPage />} />
        <Route path="overdue" element={<OverduePage />} />
        <Route path="outbox" element={<OutboxPage />} />
        <Route
          path="*"
          element={
            <EmptyState icon="search">
              Page not found. <Link to="/">Back to the dashboard</Link>
            </EmptyState>
          }
        />
      </Route>
    </Routes>
  );
}
