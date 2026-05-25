import { useEffect, useMemo, useState } from 'react';

const API_BASE = '/api';

const emptyStats = {
  totalReports: 0,
  categories: { FIRE: 0, FLOOD: 0, NORMAL: 0, UNKNOWN: 0 },
  risks: { HIGH: 0, MEDIUM: 0, LOW: 0 },
  averageProcessingMs: 0,
};

async function getJson(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`${path} ${response.status}`);
  }
  return response.json();
}

function StatTile({ label, value, tone }) {
  return (
    <section className={`tile ${tone || ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </section>
  );
}

export default function App({ icons }) {
  const { AlertTriangle, Activity, Gauge, ServerCog } = icons;
  const [stats, setStats] = useState(emptyStats);
  const [queue, setQueue] = useState({ messages: 0 });
  const [reports, setReports] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;

    async function refresh() {
      try {
        const [statsData, queueData, recentData] = await Promise.all([
          getJson('/stats/summary'),
          getJson('/queue/status'),
          getJson('/reports/recent?limit=12'),
        ]);
        if (!alive) return;
        setStats(statsData);
        setQueue(queueData);
        setReports(recentData.items || []);
        setError('');
      } catch (err) {
        if (alive) setError(err.message);
      }
    }

    refresh();
    const timer = setInterval(refresh, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  const categoryRows = useMemo(
    () => Object.entries(stats.categories || {}),
    [stats.categories]
  );
  const riskRows = useMemo(() => Object.entries(stats.risks || {}), [stats.risks]);

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Kubernetes/k3s Distributed Image Analysis</p>
          <h1>DISASTER Real-time Dashboard</h1>
        </div>
        <div className="status">
          <ServerCog size={18} />
          <span>{error ? 'API 연결 확인 필요' : 'Live polling'}</span>
        </div>
      </header>

      <section className="summary">
        <StatTile label="총 제보" value={stats.totalReports} tone="blue" />
        <StatTile label="현재 큐 길이" value={queue.messages} tone="amber" />
        <StatTile label="평균 처리 시간" value={`${stats.averageProcessingMs} ms`} tone="green" />
      </section>

      <section className="grid">
        <div className="panel">
          <div className="panel-title">
            <AlertTriangle size={20} />
            <h2>카테고리</h2>
          </div>
          {categoryRows.map(([name, value]) => (
            <div className="metric" key={name}>
              <span>{name}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>

        <div className="panel">
          <div className="panel-title">
            <Gauge size={20} />
            <h2>위험도</h2>
          </div>
          {riskRows.map(([name, value]) => (
            <div className="metric" key={name}>
              <span>{name}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>

        <div className="panel wide">
          <div className="panel-title">
            <Activity size={20} />
            <h2>최근 분석 결과</h2>
          </div>
          <div className="table">
            <div className="table-head">
              <span>Report</span>
              <span>Category</span>
              <span>Risk</span>
              <span>Worker</span>
              <span>Processing</span>
            </div>
            {reports.length === 0 ? (
              <p className="empty">아직 분석된 제보가 없습니다.</p>
            ) : (
              reports.map((report) => (
                <div className="table-row" key={report.reportId}>
                  <span>{report.reportId}</span>
                  <span className={`pill ${report.category?.toLowerCase()}`}>{report.category}</span>
                  <span className={`pill ${report.riskLevel?.toLowerCase()}`}>{report.riskLevel}</span>
                  <span>{report.workerId}</span>
                  <span>{report.processingMs} ms</span>
                </div>
              ))
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
