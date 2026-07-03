// API service layer.
// IMPORTANT: backend is NOT yet ready. All methods return mock data.
// When backend is wired up, only this file + mockData.js should change.

import axios from 'axios';
import SAMPLE_REPORTS, {
  mockInsights,
  buildDashboardStats,
  simulateLatency,
} from './mockData.js';

// Toggle: when VITE_USE_MOCK is not "false", use mock. Set in .env to flip.
const USE_MOCK =
  import.meta?.env?.VITE_USE_MOCK === undefined
    ? true
    : String(import.meta.env.VITE_USE_MOCK).toLowerCase() !== 'false';

export const apiClient = axios.create({
  baseURL: import.meta?.env?.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

// --- Mock implementations ----------------------------------------------

async function mockListReports({ search = '', category = '', severity = '' } = {}) {
  await simulateLatency();
  let rows = [...SAMPLE_REPORTS];
  if (search) {
    const q = search.toLowerCase();
    rows = rows.filter(
      (r) =>
        r.title.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q) ||
        r.location.toLowerCase().includes(q),
    );
  }
  if (category) rows = rows.filter((r) => r.ai.category === category);
  if (severity) rows = rows.filter((r) => r.ai.severity === severity);
  // newest first
  rows.sort((a, b) => new Date(b.submittedAt) - new Date(a.submittedAt));
  return rows;
}

async function mockGetReport(id) {
  await simulateLatency(200);
  const found = SAMPLE_REPORTS.find((r) => r.id === id);
  if (!found) {
    const err = new Error('Report not found');
    err.code = 'NOT_FOUND';
    throw err;
  }
  return found;
}

async function mockCreateReport(payload) {
  await simulateLatency(700);
  const id = `RPT-${1000 + SAMPLE_REPORTS.length + 1}`;
  const now = new Date().toISOString();
  // Pretend AI just produced insights
  const ai = {
    ...mockInsights,
    summary:
      payload.description?.slice(0, 140) ||
      'AI-generated summary pending further analysis.',
    category: payload.category || mockInsights.category,
    severity: payload.severity || mockInsights.severity,
    confidence: 0.7 + Math.random() * 0.25,
  };
  const newReport = {
    id,
    title: payload.title,
    description: payload.description,
    category: payload.category || ai.category,
    severity: ai.severity,
    status: 'pending',
    location: payload.location || 'Unknown',
    hasImage: Boolean(payload.imageDataUrl),
    imageUrl: payload.imageDataUrl || null,
    submittedBy: payload.submittedBy || 'Anonymous',
    submittedAt: now,
    ai,
  };
  SAMPLE_REPORTS.unshift(newReport);
  return newReport;
}

async function mockGetDashboardStats() {
  await simulateLatency(250);
  return buildDashboardStats(SAMPLE_REPORTS);
}

// --- Public API (auto-switches mock vs real) ----------------------------

export const reportsApi = {
  async list(params) {
    if (USE_MOCK) return mockListReports(params);
    const { data } = await apiClient.get('/reports', { params });
    return data;
  },
  async get(id) {
    if (USE_MOCK) return mockGetReport(id);
    const { data } = await apiClient.get(`/reports/${id}`);
    return data;
  },
  async create(payload) {
    if (USE_MOCK) return mockCreateReport(payload);
    const { data } = await apiClient.post('/reports', payload);
    return data;
  },
};

export const dashboardApi = {
  async stats() {
    if (USE_MOCK) return mockGetDashboardStats();
    const { data } = await apiClient.get('/dashboard/stats');
    return data;
  },
};

export { USE_MOCK };