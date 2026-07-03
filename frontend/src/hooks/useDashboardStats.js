import { useMemo } from 'react';
import useReportsList from './useReportsList.js';

const RELIEF_LABELS = {
  rescue_team: 'Rescue Teams',
  food: 'Food packs',
  water: 'Drinking water',
  medical: 'Medical teams',
  shelter: 'Shelters',
  medicine: 'Medicine',
  ambulance: 'Ambulances',
  rescue_boat: 'Rescue boats',
  baby_supplies: 'Baby supplies',
  clothes: 'Clothes',
  fire_service: 'Fire service',
};

function bucketCount(reports, predicate) {
  return reports.filter(predicate).length;
}

function tallyRelief(reports) {
  const counts = {};
  for (const r of reports) {
    for (const a of r.assistance || []) {
      counts[a] = (counts[a] || 0) + 1;
    }
  }
  return Object.entries(counts)
    .map(([key, count]) => ({ key, label: RELIEF_LABELS[key] || key, count }))
    .sort((a, b) => b.count - a.count);
}

function tallyByDivision(reports) {
  const counts = {};
  for (const r of reports) {
    if (!r.division) continue;
    counts[r.division] = (counts[r.division] || 0) + 1;
  }
  return Object.entries(counts)
    .map(([division, count]) => ({ division, count }))
    .sort((a, b) => b.count - a.count);
}

function tallyBySeverity(reports) {
  const order = ['Critical', 'High', 'Medium', 'Low'];
  const counts = order.map((severity) => ({
    severity,
    count: bucketCount(reports, (r) => r.severity === severity),
  }));
  return counts;
}

export default function useDashboardStats() {
  const { reports, total } = useReportsList();

  const stats = useMemo(() => {
    const critical = bucketCount(reports, (r) => r.severity === 'Critical');
    const active = bucketCount(
      reports,
      (r) => r.status === 'verified' || r.status === 'dispatched',
    );
    const affectedPeople = reports.reduce(
      (sum, r) => sum + (Number(r.affectedCount) || 0),
      0,
    );
    const dangerActive = bucketCount(reports, (r) => r.immediateDanger);

    return {
      total,
      critical,
      active,
      affectedPeople,
      dangerActive,
      reliefTallies: tallyRelief(reports),
      divisionTallies: tallyByDivision(reports),
      severityTallies: tallyBySeverity(reports),
    };
  }, [reports, total]);

  return stats;
}