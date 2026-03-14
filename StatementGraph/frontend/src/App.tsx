import { NavLink, Route, Routes } from "react-router-dom";

import { AlertsPage } from "./pages/AlertsPage";
import { GraphPage } from "./pages/GraphPage";
import { SummaryPage } from "./pages/SummaryPage";
import { UploadPage } from "./pages/UploadPage";

const navItems = [
  { to: "/", label: "Загрузка" },
  { to: "/summary", label: "Сводка" },
  { to: "/alerts", label: "Алерты" },
  { to: "/graph", label: "Граф" },
];

export function App(): JSX.Element {
  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>StatementGraph — Анализ банковских выписок</h1>
        <nav className="app-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              className={({ isActive }) =>
                isActive ? "app-nav__link app-nav__link--active" : "app-nav__link"
              }
              to={item.to}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="app-content">
        <Routes>
          <Route element={<UploadPage />} path="/" />
          <Route element={<SummaryPage />} path="/summary" />
          <Route element={<AlertsPage />} path="/alerts" />
          <Route element={<GraphPage />} path="/graph" />
        </Routes>
      </main>
    </div>
  );
}
