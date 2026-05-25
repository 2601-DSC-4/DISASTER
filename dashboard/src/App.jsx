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

function StatTile({ label, value, tone, pulse }) {
  return (
    <section className={`tile ${tone || ''} ${pulse ? 'pulse' : ''}`}>
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
  const [lastUpdated, setLastUpdated] = useState(null);
  const [uploadPending, setUploadPending] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);

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
        setLastUpdated(Date.now());
      } catch (err) {
        if (alive) {
          if (err.message.includes('503') || err.message.includes('502')) {
            setError('⚠️ 백엔드 서비스 불가 (RabbitMQ/Redis 확인 필요)');
          } else {
            setError(`🔌 연결 오류: ${err.message}`);
          }
        }
      }
    }

    refresh();
    const timer = setInterval(refresh, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  async function handleUpload(e) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);

    setUploadPending(true);
    setUploadResult(null);

    try {
      const res = await fetch(`${API_BASE}/reports`, {
        method: 'POST',
        body: fd,
      });
      if (!res.ok) throw new Error(`upload failed: ${res.status}`);
      const data = await res.json();
      setUploadResult({ reportId: data.reportId, error: null });
      form.reset();
      // 즉시 테이블 갱신
      setTimeout(() => {
        const refresh = async () => {
          const [statsData, queueData, recentData] = await Promise.all([
            getJson('/stats/summary'),
            getJson('/queue/status'),
            getJson('/reports/recent?limit=12'),
          ]);
          setStats(statsData);
          setQueue(queueData);
          setReports(recentData.items || []);
        };
        refresh();
      }, 500);
    } catch (err) {
      let errorMsg = err.message;
      if (err.message.includes('503') || err.message.includes('502')) {
        errorMsg = 'RabbitMQ/Redis 서비스 불가 — 잠시 후 다시 시도하세요';
      } else if (err.message.includes('failed to fetch')) {
        errorMsg = '네트워크 연결 오류 — 인터넷 연결을 확인하세요';
      }
      setUploadResult({ reportId: null, error: errorMsg });
    } finally {
      setUploadPending(false);
    }
  }

  const categoryRows = useMemo(
    () => Object.entries(stats.categories || {}),
    [stats.categories]
  );
  const riskRows = useMemo(() => Object.entries(stats.risks || {}), [stats.risks]);

  const queueAlertLevel = useMemo(() => {
    const m = queue.messages ?? 0;
    if (m >= 100) return 'critical';
    if (m >= 30) return 'warning';
    if (m >= 10) return 'caution';
    return 'normal';
  }, [queue.messages]);

  const activeWorkers = useMemo(() => {
    const ids = new Set(reports.map(r => r.workerId).filter(Boolean));
    return ids.size;
  }, [reports]);

  const dangerRatio = useMemo(() => {
    const total = stats.totalReports || 1;
    return (stats.categories.FIRE + stats.categories.FLOOD) / total;
  }, [stats]);

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Kubernetes/k3s Distributed Image Analysis</p>
          <h1>DISASTER Real-time Dashboard</h1>
        </div>
        <div className="status">
          <ServerCog size={18} />
          <span>
            {error ? `❌ ${error}` : '🟢 Live polling'}
            {lastUpdated && ` (${Math.round((Date.now() - lastUpdated) / 1000)}초 전)`}
          </span>
        </div>
      </header>

      {queueAlertLevel !== 'normal' && (
        <div className={`alert-banner alert-${queueAlertLevel}`}>
          <AlertTriangle size={16} />
          <span>
            {queueAlertLevel === 'critical'
              ? `🚨 긴급! 큐 적체 ${queue.messages}건 — 즉시 Worker Scale-out 필요`
              : queueAlertLevel === 'warning'
              ? `⚠️ 재난 경보! 큐 적체 ${queue.messages}건 — Worker 확장 권장`
              : `⚠️ 큐 누적 경고 (${queue.messages}건) — 처리 지연 발생 중`}
          </span>
        </div>
      )}

      <section className="summary">
        <StatTile label="총 제보" value={stats.totalReports} tone="blue" />
        <StatTile
          label="현재 큐 길이"
          value={queue.messages ?? '--'}
          tone={queueAlertLevel === 'critical' ? 'red' : queueAlertLevel === 'warning' ? 'orange' : queueAlertLevel === 'caution' ? 'orange' : 'amber'}
          pulse={queueAlertLevel === 'critical'}
        />
        <StatTile label="평균 처리 시간" value={`${stats.averageProcessingMs.toFixed(1)} ms`} tone="green" />
        <StatTile label="활성 Worker 추정" value={activeWorkers || '--'} tone="purple" />
      </section>

      <section className="upload-section">
        <h2>이미지 제보</h2>
        <form onSubmit={handleUpload} className="upload-form">
          <div className="form-group">
            <label htmlFor="image">이미지 파일 *</label>
            <input
              type="file"
              id="image"
              name="image"
              accept="image/*"
              required
              disabled={uploadPending}
            />
          </div>
          <div className="form-group">
            <label htmlFor="location">위치 *</label>
            <input
              type="text"
              id="location"
              name="location"
              placeholder="예: 서울시 동대문구"
              required
              disabled={uploadPending}
            />
          </div>
          <div className="form-group">
            <label htmlFor="description">설명</label>
            <input
              type="text"
              id="description"
              name="description"
              placeholder="선택 입력"
              disabled={uploadPending}
            />
          </div>
          <button type="submit" disabled={uploadPending} className="upload-btn">
            {uploadPending ? '업로드 중...' : '제보하기'}
          </button>
        </form>
        {uploadResult?.error && <div className="upload-error">❌ {uploadResult.error}</div>}
        {uploadResult?.reportId && (
          <div className="upload-success">✅ 제보 완료: {uploadResult.reportId}</div>
        )}
      </section>

      <section className="grid">
        <div className={`panel ${dangerRatio >= 0.5 ? 'panel-danger' : ''}`}>
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
              reports.map((report, idx) => (
                <div className={`table-row ${idx === 0 ? 'row-new' : ''}`} key={report.reportId}>
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
