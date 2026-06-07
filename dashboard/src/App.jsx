import { useEffect, useMemo, useState } from 'react';

const API_BASE = '/api';

const emptyStats = {
  totalReports: 0,
  categories: { FIRE: 0, FLOOD: 0, NORMAL: 0, UNKNOWN: 0 },
  risks: { HIGH: 0, MEDIUM: 0, LOW: 0, NORMAL: 0 },
  averageProcessingMs: 0,
};

const DISPLAY_REGIONS = [
  '서울 강남구',
  '서울 동대문구',
  '인천 미추홀구',
  '부산 해운대구',
  '강원 춘천시',
  '대구 중구',
  '광주 서구',
  '대전 유성구',
];

function transformLocationData(data) {
  const apiMap = {};
  for (const [location, s] of Object.entries(data.locations || {})) {
    const topModelLabel =
      Object.entries(s.categories || {}).sort((a, b) => b[1] - a[1])[0]?.[0] || '-';
    apiMap[location] = {
      location,
      totalReports: s.totalReports,
      topModelLabel,
      riskCounts: s.risks,
      recentReports: s.recentReports || [],
    };
  }

  return DISPLAY_REGIONS.map((location) =>
    apiMap[location] ?? {
      location,
      totalReports: 0,
      topModelLabel: '-',
      riskCounts: { HIGH: 0, LOW: 0, NORMAL: 0 },
      recentReports: [],
    }
  );
}

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

function LocationCard({ region }) {
  const getRiskColor = (level) => {
    switch (level) {
      case 'HIGH':
        return '#ff3333';
      case 'LOW':
        return '#ffaa33';
      case 'NORMAL':
        return '#33dd33';
      default:
        return '#cccccc';
    }
  };

  return (
    <div className="location-card">
      <div className="card-header">
        <h3>{region.location}</h3>
        <span className="total-badge">신고 {region.totalReports}건</span>
      </div>

      {region.totalReports === 0 ? (
        <div className="card-empty">신고 없음</div>
      ) : (
        <>
          <div className="card-section">
            <span className="label">주요 재난</span>
            <span className="value">{region.topModelLabel || '-'}</span>
          </div>

          <div className="card-risks">
            {Object.entries(region.riskCounts || {}).map(([level, count]) => (
              <div key={level} className="risk-badge" style={{ borderLeftColor: getRiskColor(level) }}>
                <span className="risk-label">{level}</span>
                <span className="risk-count">{count}</span>
              </div>
            ))}
          </div>

          {region.recentReports?.length > 0 && (
            <div className="card-recent">
              <span className="label">최근 신고</span>
              <ul>
                {region.recentReports.slice(0, 3).map((report) => (
                  <li key={report.reportId}>
                    <span className="model-label">{report.modelLabel}</span>
                    <span className="confidence">{report.confidence ? `신뢰도 ${(report.confidence * 100).toFixed(0)}%` : '-'}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function QueueGraph({ history }) {
  const W = 800, H = 88;

  if (history.length < 2) {
    return <div className="queue-graph-empty">데이터 수집 중...</div>;
  }

  const maxVal = Math.max(...history.map(h => h.messages), 30);
  const n = history.length;
  const cx = (i) => (i / (n - 1)) * W;
  const cy = (v) => H - (v / maxVal) * H * 0.92 - 4;

  const current = history[history.length - 1].messages;
  const color = current >= 30 ? '#ef4444' : current >= 10 ? '#f59e0b' : '#3b82f6';

  const linePoints = history.map((h, i) => `${cx(i)},${cy(h.messages)}`).join(' ');
  const areaPoints = [`0,${H}`, ...history.map((h, i) => `${cx(i)},${cy(h.messages)}`), `${W},${H}`].join(' ');

  const y10 = cy(10), y30 = cy(30);

  return (
    <div className="queue-graph">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="queue-svg">
        <defs>
          <linearGradient id="qg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.2" />
            <stop offset="100%" stopColor={color} stopOpacity="0.01" />
          </linearGradient>
        </defs>
        {y30 > 0 && y30 < H && <line x1="0" y1={y30} x2={W} y2={y30} stroke="#f87171" strokeWidth="1" strokeDasharray="5,4" opacity="0.45" />}
        {y10 > 0 && y10 < H && <line x1="0" y1={y10} x2={W} y2={y10} stroke="#fbbf24" strokeWidth="1" strokeDasharray="5,4" opacity="0.45" />}
        <polygon points={areaPoints} fill="url(#qg)" />
        <polyline points={linePoints} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={cx(n - 1)} cy={cy(current)} r="4" fill={color} />
      </svg>
      <div className="queue-graph-legend">
        <span style={{ color: '#fbbf24' }}>— 경고 10</span>
        <span style={{ color: '#f87171' }}>— 위험 30</span>
        <span className="queue-graph-time">최근 2분</span>
      </div>
    </div>
  );
}

export default function App({ icons }) {
  const { AlertTriangle, Activity, Gauge, ServerCog, MapPin } = icons;
  const [stats, setStats] = useState(emptyStats);
  const [queue, setQueue] = useState({ messages: 0 });
  const [reports, setReports] = useState([]);
  const [error, setError] = useState('');
  const [lastUpdated, setLastUpdated] = useState(null);
  const [uploadPending, setUploadPending] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [userLocation, setUserLocation] = useState(null);
  const [locationError, setLocationError] = useState(null);
  const [locationRegions, setLocationRegions] = useState(
    DISPLAY_REGIONS.map(location => ({
      location,
      totalReports: 0,
      topModelLabel: '-',
      riskCounts: { HIGH: 0, LOW: 0, NORMAL: 0 },
      recentReports: [],
    }))
  );
  const [queueHistory, setQueueHistory] = useState([]);

  useEffect(() => {
    let alive = true;

    async function refresh() {
      try {
        const [statsData, queueData, recentData, locationData] = await Promise.all([
          getJson('/stats/summary'),
          getJson('/queue/status'),
          getJson('/reports/recent?limit=12'),
          getJson('/stats/location'),
        ]);
        if (!alive) return;
        setStats(statsData);
        setQueue(queueData);
        setReports(recentData.items || []);
        setLocationRegions(transformLocationData(locationData));
        setQueueHistory(prev => [...prev.slice(-59), { messages: queueData.messages }]);
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

      <section className="queue-history-panel">
        <div className="queue-history-header">
          <div className="queue-history-title">
            <Activity size={16} />
            <span>큐 길이 실시간 추이</span>
          </div>
          <span className="queue-history-current" data-level={queueAlertLevel}>
            현재 {queue.messages}건
          </span>
        </div>
        <QueueGraph history={queueHistory} />
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
            <div className="location-group">
              <label htmlFor="location">위치 *</label>
              <button
                type="button"
                className="geolocation-btn"
                onClick={() => {
                  if ('geolocation' in navigator) {
                    navigator.geolocation.getCurrentPosition(
                      (position) => {
                        const { latitude, longitude } = position.coords;
                        setUserLocation(`${latitude.toFixed(4)}, ${longitude.toFixed(4)}`);
                        setLocationError(null);
                        // 폼의 location 필드에 자동 입력
                        const locationInput = document.getElementById('location');
                        if (locationInput) {
                          locationInput.value = `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`;
                        }
                      },
                      (error) => {
                        setLocationError(`위치 조회 실패: ${error.message}`);
                      }
                    );
                  } else {
                    setLocationError('브라우저가 지정학적 위치를 지원하지 않습니다');
                  }
                }}
                disabled={uploadPending}
              >
                📍 현재 위치 사용
              </button>
            </div>
            <input
              type="text"
              id="location"
              name="location"
              placeholder="예: 서울시 동대문구 또는 위도,경도"
              required
              disabled={uploadPending}
            />
            {locationError && <div className="location-error">⚠️ {locationError}</div>}
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

      {(
        <section className="locations-section">
          <div className="section-header">
            <MapPin size={24} />
            <h2>지역별 재난 상황</h2>
          </div>
          <div className="locations-grid">
            {locationRegions.map((region) => (
              <LocationCard key={region.location} region={region} />
            ))}
          </div>
        </section>
      )}

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
              <span>Model Label</span>
              <span>Confidence</span>
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
                  <span className={`pill ${(report.modelLabel || report.category || '').toLowerCase()}`}>
                    {report.modelLabel || report.category || '-'}
                  </span>
                  <span className={`pill ${(report.confidence * 100).toFixed(0)}`}>
                    {report.confidence ? `${(report.confidence * 100).toFixed(0)}%` : '-'}
                  </span>
                  <span className={`pill ${report.riskLevel?.toLowerCase()}`}>{report.riskLevel || '-'}</span>
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
