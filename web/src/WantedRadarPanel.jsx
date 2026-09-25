import React, { useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, RefreshCw, Search, ShieldCheck } from "lucide-react";
import {
  fetchWanted,
  fetchWantedIntelligence,
  fetchWantedSourceStatus,
  fetchWantedVisualAnalysis,
  syncWanted,
  wantedImageUrl,
} from "./api";

function RadarBlip({ item, index, onSelect }) {
  const angle = ((item.id * 137.508 + index * 23) % 360) * Math.PI / 180;
  const distance = 18 + ((item.id * 17 + index * 11) % 30);
  const x = 50 + Math.cos(angle) * distance;
  const y = 50 + Math.sin(angle) * distance;
  return (
    <button
      className="wanted-blip"
      style={{ left: `${x}%`, top: `${y}%` }}
      title={item.full_name}
      onClick={() => onSelect(item)}
      aria-label={`Xem ${item.full_name}`}
    />
  );
}

function Wanted3DProfile({ item }) {
  const [tilt, setTilt] = useState({ x: 0, y: 0 });
  const [imageFailed, setImageFailed] = useState(false);

  function move(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    const px = (event.clientX - rect.left) / rect.width - 0.5;
    const py = (event.clientY - rect.top) / rect.height - 0.5;
    setTilt({ x: Math.max(-8, Math.min(8, -py * 14)), y: Math.max(-10, Math.min(10, px * 18)) });
  }

  return (
    <div className="wanted-3d-shell">
      <div className="wanted-3d-label">3D PROFILE VISUALIZATION</div>
      <div
        className="wanted-3d-stage"
        onPointerMove={move}
        onPointerLeave={() => setTilt({ x: 0, y: 0 })}
      >
        <div
          className="wanted-3d-card"
          style={{ transform: `rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)` }}
        >
          <div className="wanted-3d-depth depth-a" />
          <div className="wanted-3d-depth depth-b" />
          {!imageFailed ? (
            <img
              src={wantedImageUrl(item.id)}
              alt={`Ảnh chính thức của ${item.full_name}`}
              onError={() => setImageFailed(true)}
            />
          ) : (
            <div className="wanted-image-missing">
              <strong>Chưa có ảnh chính thức</strong>
              <span>TRACE không tạo ảnh thay thế.</span>
            </div>
          )}
          <div className="wanted-3d-grid" />
          <div className="wanted-3d-axis axis-v" />
          <div className="wanted-3d-axis axis-h" />
          <div className="wanted-3d-caption">
            <strong>{item.full_name}</strong>
            <span>{item.birth_year || "Năm sinh chưa có"} · {item.status || "active"}</span>
          </div>
        </div>
      </div>
      <p className="wanted-3d-disclaimer">
        Mô phỏng chiều sâu từ ảnh nguồn chính thức để quan sát trực quan; không phải dựng hình pháp y hoặc mô hình sinh trắc học 3D.
      </p>
    </div>
  );
}

function ScoreBar({ label, value }) {
  const score = Math.max(0, Math.min(100, Number(value || 0)));
  return (
    <div className="wanted-score">
      <div><span>{label}</span><strong>{Math.round(score)}%</strong></div>
      <div className="wanted-score-track"><i style={{ width: `${score}%` }} /></div>
    </div>
  );
}

function IntelligencePanel({ item, intelligence, visual, loading }) {
  if (loading) return <div className="empty-card">Đang phân tích hồ sơ và ảnh chính thức…</div>;
  if (!intelligence) return <div className="empty-card">Chưa tải được lớp phân tích hồ sơ.</div>;

  return (
    <div className="wanted-intelligence">
      <div className="wanted-intel-head">
        <div>
          <div className="eyebrow">TRACE WANTED INTELLIGENCE</div>
          <h4>Phân tích hồ sơ chuyên sâu</h4>
        </div>
        <span className="source-badge"><Activity size={14}/> Human verification</span>
      </div>

      <div className="wanted-intel-metrics">
        <ScoreBar label="Độ đầy đủ hồ sơ" value={intelligence.record?.completeness_percent} />
        <ScoreBar label="Chất lượng ảnh" value={visual?.quality_score || 0} />
      </div>

      <div className="wanted-intel-grid">
        <div><span>Nguồn chính thức</span><strong>{intelligence.source?.official_host ? "Đã xác minh host" : "Cần kiểm tra"}</strong></div>
        <div><span>Checksum</span><strong>{intelligence.source?.checksum_present ? "Có" : "Chưa có"}</strong></div>
        <div><span>Lịch sử thay đổi</span><strong>{intelligence.source?.history_events ?? 0}</strong></div>
        <div><span>Ảnh đối chiếu thủ công</span><strong>{visual?.manual_comparison_ready ? "Sẵn sàng" : "Hạn chế"}</strong></div>
      </div>

      <div className="wanted-analysis-summary">{intelligence.analysis?.summary}</div>

      {visual?.available && (
        <div className="wanted-visual-metrics">
          <span>{visual.dimensions?.width}×{visual.dimensions?.height}px</span>
          <span>Brightness {visual.metrics?.brightness}</span>
          <span>Contrast {visual.metrics?.contrast}</span>
          <span>Sharpness {visual.metrics?.edge_sharpness}</span>
        </div>
      )}

      <div className="wanted-checks">
        <strong>Điểm cần xác minh</strong>
        {(intelligence.analysis?.recommended_checks || []).map((check, index) => <p key={index}>• {check}</p>)}
        {(visual?.observations || []).map((note, index) => <p key={`visual-${index}`}>• {note}</p>)}
      </div>

      <div className="wanted-ai-boundary">
        <AlertTriangle size={17}/>
        TRACE AI hỗ trợ phân tích chất lượng dữ liệu và ảnh, nhưng không tự gắn danh tính một người từ ảnh và không tự đưa ra kết luận nghiệp vụ.
      </div>
    </div>
  );
}

export default function WantedRadarPanel({ role = "viewer" }) {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [intelligence, setIntelligence] = useState(null);
  const [visual, setVisual] = useState(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const canSync = ["commander", "admin"].includes(role);

  async function load(q = query) {
    try {
      setMessage("");
      const [rows, src] = await Promise.all([
        fetchWanted(q, 100),
        fetchWantedSourceStatus(),
      ]);
      setItems(rows);
      setStatus(src);
      if (selected && !rows.some((x) => x.id === selected.id)) setSelected(null);
    } catch (error) {
      setMessage(error.message);
    }
  }

  useEffect(() => { load(""); }, []);

  useEffect(() => {
    if (!selected?.id) {
      setIntelligence(null);
      setVisual(null);
      return;
    }
    let active = true;
    setAnalysisLoading(true);
    Promise.all([
      fetchWantedIntelligence(selected.id),
      fetchWantedVisualAnalysis(selected.id),
    ]).then(([intel, imageAnalysis]) => {
      if (!active) return;
      setIntelligence(intel);
      setVisual(imageAnalysis);
    }).catch((error) => {
      if (active) setMessage(error.message);
    }).finally(() => {
      if (active) setAnalysisLoading(false);
    });
    return () => { active = false; };
  }, [selected?.id]);

  async function doSync() {
    setBusy(true);
    setMessage("");
    try {
      const result = await syncWanted(3);
      setMessage(`Đồng bộ xong: ${result.parsed_records} hồ sơ từ ${result.fetched_pages} trang; mới ${result.inserted}, cập nhật ${result.updated}.`);
      await load(query);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  const radarItems = useMemo(() => items.slice(0, 24), [items]);

  return (
    <div className="wanted-radar-layout wanted-radar-v2">
      <section className="wanted-radar-card">
        <div className="wanted-radar-head">
          <div>
            <div className="eyebrow">OFFICIAL WANTED DATA RADAR</div>
            <h3>Radar tra soát truy nã</h3>
          </div>
          <span className="source-badge"><ShieldCheck size={14}/> Nguồn Bộ Công an</span>
        </div>

        <form className="wanted-search" onSubmit={(e) => { e.preventDefault(); load(query); }}>
          <div className="wanted-search-box">
            <Search size={17}/>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Tên, tội danh, địa chỉ, số quyết định, đơn vị..."
            />
          </div>
          <button className="primary-button">Tra soát</button>
          {canSync && (
            <button type="button" className="secondary-button" disabled={busy} onClick={doSync}>
              <RefreshCw size={15} className={busy ? "spin" : ""}/>
              {busy ? "Đang cập nhật..." : "Cập nhật BCA"}
            </button>
          )}
        </form>

        <div className="radar-stage" aria-label="Mô phỏng radar tra soát dữ liệu">
          <div className="radar-circle rc1"></div>
          <div className="radar-circle rc2"></div>
          <div className="radar-circle rc3"></div>
          <div className="radar-cross horizontal"></div>
          <div className="radar-cross vertical"></div>
          <div className="radar-sweep"></div>
          <div className="radar-center"></div>
          {radarItems.map((item, index) => (
            <RadarBlip key={item.id} item={item} index={index} onSelect={setSelected}/>
          ))}
          <div className="radar-counter">{items.length} kết quả</div>
        </div>

        <div className="wanted-source-line">
          <span>
            Nguồn: {status?.source_name || "Cổng thông tin truy nã - Bộ Công an"}
            {status?.last_sync ? ` • Đồng bộ gần nhất ${new Date(status.last_sync).toLocaleString("vi-VN")}` : ""}
          </span>
          <a href={status?.source_url || "https://truyna.bocongan.gov.vn/Đối-tượng-truy-nã"} target="_blank" rel="noreferrer">
            Mở nguồn chính thức
          </a>
        </div>
        <p className="radar-disclaimer">
          Radar là trực quan hóa dữ liệu đã đồng bộ; không quét người, thiết bị, IP hoặc GPS của người xung quanh.
        </p>
        {message && <div className={message.includes("xong") ? "form-success" : "form-error"}>{message}</div>}
      </section>

      <section className="wanted-results">
        {selected && (
          <div className="wanted-selected wanted-selected-v2">
            <div className="wanted-selected-top">
              <Wanted3DProfile item={selected}/>
              <div className="wanted-selected-data">
                <div className="eyebrow">SELECTED OFFICIAL RECORD</div>
                <h3>{selected.full_name}</h3>
                <div className="wanted-detail-grid">
                  <div><span>Năm sinh</span><strong>{selected.birth_year || "—"}</strong></div>
                  <div><span>Trạng thái</span><strong>{selected.status || "active"}</strong></div>
                  <div className="wide"><span>Số/ngày quyết định</span><strong>{selected.warrant_reference || "—"}</strong></div>
                  <div className="wide"><span>Tội danh</span><strong>{selected.offense || "—"}</strong></div>
                  <div className="wide"><span>Nơi ĐKTT</span><strong>{selected.registered_address || "—"}</strong></div>
                  <div className="wide"><span>Đơn vị ra quyết định</span><strong>{selected.issuing_unit || "—"}</strong></div>
                </div>
                {selected.detail_url && <a className="official-link" href={selected.detail_url} target="_blank" rel="noreferrer">Xem hồ sơ tại nguồn Bộ Công an</a>}
              </div>
            </div>
            <IntelligencePanel item={selected} intelligence={intelligence} visual={visual} loading={analysisLoading}/>
          </div>
        )}

        <div className="wanted-list">
          {items.map((item) => (
            <button key={item.id} className={selected?.id === item.id ? "wanted-row active" : "wanted-row"} onClick={() => setSelected(item)}>
              <img
                className="wanted-row-thumb"
                src={wantedImageUrl(item.id, true)}
                alt=""
                loading="lazy"
                onError={(e) => { e.currentTarget.style.visibility = "hidden"; }}
              />
              <div>
                <strong>{item.full_name}</strong>
                <span>{item.birth_year || "—"} • {item.offense || "Chưa có tội danh"}</span>
              </div>
              <div className="wanted-row-meta">
                <span>{item.warrant_reference || "—"}</span>
                <small>{item.issuing_unit || "—"}</small>
              </div>
            </button>
          ))}
          {!items.length && <div className="empty-card">Chưa có dữ liệu đồng bộ hoặc không tìm thấy kết quả.</div>}
        </div>
      </section>
    </div>
  );
}
