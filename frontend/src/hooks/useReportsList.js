import { useEffect, useMemo, useState } from 'react';

const SEED_REPORTS = [
  {
    id: 'rpt_001',
    title: 'Flash flood in Kurigram',
    category: 'Flood / Water Rescue',
    severity: 'Critical',
    division: 'Rangpur',
    district: 'Kurigram',
    upazila: 'Nageshwari',
    area: 'Ward 3, beside the embankment',
    affectedCount: 320,
    assistance: ['rescue_team', 'water', 'shelter', 'rescue_boat'],
    immediateDanger: true,
    incidentTime: 'just_now',
    status: 'verified',
    createdAt: '2026-07-02T11:42:00.000Z',
    coords: { lat: 25.8057, lng: 89.6361 },
  },
  {
    id: 'rpt_002',
    title: 'Building collapse in old Dhaka',
    category: 'Structural Collapse',
    severity: 'High',
    division: 'Dhaka',
    district: 'Dhaka',
    upazila: 'Kotwali',
    area: 'Near Nawabpur Road',
    affectedCount: 18,
    assistance: ['rescue_team', 'ambulance', 'medical'],
    immediateDanger: true,
    incidentTime: 'within_1h',
    status: 'dispatched',
    createdAt: '2026-07-02T09:15:00.000Z',
    coords: { lat: 23.7104, lng: 90.4074 },
  },
  {
    id: 'rpt_003',
    title: 'Fire in garment factory',
    category: 'Fire',
    severity: 'High',
    division: 'Dhaka',
    district: 'Gazipur',
    upazila: 'Kaliakair',
    area: 'Baipail industrial zone',
    affectedCount: 45,
    assistance: ['ambulance', 'medical', 'fire_service'],
    immediateDanger: false,
    incidentTime: 'today',
    status: 'verified',
    createdAt: '2026-07-02T07:05:00.000Z',
    coords: { lat: 24.0693, lng: 90.2221 },
  },
  {
    id: 'rpt_004',
    title: 'Riverbank erosion',
    category: 'Flood / Water Rescue',
    severity: 'Medium',
    division: 'Chittagong',
    district: 'Noakhali',
    upazila: 'Subarnachar',
    area: 'Char Momena',
    affectedCount: 90,
    assistance: ['food', 'water', 'shelter', 'clothes'],
    immediateDanger: false,
    incidentTime: 'yesterday',
    status: 'pending',
    createdAt: '2026-07-01T18:30:00.000Z',
    coords: { lat: 22.6011, lng: 91.0945 },
  },
  {
    id: 'rpt_005',
    title: 'Medical emergency at Rohingya camp',
    category: 'Medical Emergency',
    severity: 'Critical',
    division: 'Chittagong',
    district: 'Coxs Bazar',
    upazila: 'Ukhia',
    area: 'Camp 14, Block C',
    affectedCount: 12,
    assistance: ['medical', 'ambulance', 'medicine'],
    immediateDanger: true,
    incidentTime: 'within_1h',
    status: 'verified',
    createdAt: '2026-07-02T13:10:00.000Z',
    coords: { lat: 21.2089, lng: 92.1647 },
  },
];

export default function useReportsList({ initial = SEED_REPORTS } = {}) {
  const [reports, setReports] = useState(initial);
  const [filter, setFilter] = useState({ status: 'all', severity: 'all', query: '' });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Placeholder for future axios fetch: /api/reports?status=...&severity=...
    // Keeping a microtask to preserve async behavior for consumers.
    setLoading(false);
  }, [filter]);

  const filtered = useMemo(() => {
    const q = filter.query.trim().toLowerCase();
    return reports.filter((r) => {
      if (filter.status !== 'all' && r.status !== filter.status) return false;
      if (filter.severity !== 'all' && r.severity !== filter.severity) return false;
      if (!q) return true;
      const haystack = [r.title, r.area, r.district, r.upazila, r.category]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [reports, filter]);

  function addReport(report) {
    const next = {
      id: report.id || `rpt_${Date.now().toString(36)}`,
      status: report.status || 'pending',
      createdAt: report.createdAt || new Date().toISOString(),
      ...report,
    };
    setReports((prev) => [next, ...prev]);
    return next;
  }

  function updateStatus(id, status) {
    setReports((prev) =>
      prev.map((r) => (r.id === id ? { ...r, status } : r)),
    );
  }

  return {
    reports: filtered,
    total: reports.length,
    loading,
    filter,
    setFilter,
    addReport,
    updateStatus,
  };
}