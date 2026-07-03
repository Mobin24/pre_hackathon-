import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

import Landing from './user/pages/Landing.jsx';
import ReportIncident from './user/pages/ReportIncident.jsx';
import LiveMap from './user/pages/LiveMap.jsx';
import IncidentDetail from './user/pages/IncidentDetail.jsx';
import UserLogin from './user/pages/UserLogin.jsx';
import NotFound from './user/pages/NotFound.jsx';

import UserProtectedRoute from './user/components/UserProtectedRoute.jsx';

import AdminLogin from './admin/pages/AdminLogin.jsx';
import AdminDashboard from './admin/pages/AdminDashboard.jsx';
import AdminProtectedRoute from './admin/components/AdminProtectedRoute.jsx';

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        {/* User site */}
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<UserLogin />} />
        <Route
          path="/report"
          element={
            <UserProtectedRoute>
              <ReportIncident />
            </UserProtectedRoute>
          }
        />
        <Route path="/incidents" element={<LiveMap />} />
        <Route path="/incidents/:id" element={<IncidentDetail />} />

        {/* Admin site */}
        <Route path="/admin/login" element={<AdminLogin />} />
        <Route
          path="/admin/dashboard"
          element={
            <AdminProtectedRoute>
              <AdminDashboard />
            </AdminProtectedRoute>
          }
        />
        <Route path="/admin" element={<Navigate to="/admin/login" replace />} />

        {/* 404 */}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
}
