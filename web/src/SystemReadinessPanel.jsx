import React, { useEffect, useState } from "react";
import { Activity, RefreshCw, ShieldCheck } from "lucide-react";
import { fetchSystemReadiness } from "./api";

function tone(state = "") {
  const s = String(state).toLowerCase();
  if (s === "operational" || s === "connected") return "success";
  if (s === "degraded" || s === "warning") return "warning";
  if (s === "error" || s === "failed") return "danger";
  return "neutral";
}

function titleFor(key) {
  return ({
    wanted_registry: "Wanted Registry",
    wanted_image_proxy: "Official Image Pipeline",
    wanted_visual_analysis: "Visual Analysis",
    fusion_core: "Fusion Core",
    vision_connector: "Vision Connector",
    geo_connector: "Geo / Road Connector",
    airspace_connector: "UAS / Airspace Connector",
  })[key] || key;
}

export default function SystemReadinessPanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setBusy(true);
    setError("");
    try { setData(await fetchSystemReadiness()); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  useEffect(() => { load(); }, []);

  return (
    <div className="readiness-wrap">
      <div className="readiness-head">
        <div>
          <div className="eyebrow">LIVE MODULE READINESS</div>
          <h4>Trạng thái vận hành TRACE AI</h4>
          <p>Dữ liệu trạng thái được đọc từ backend và connector hiện tại, không giả lập trạng thái kết nối.</p>
        </div>
        <button className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={15}/>{busy ? "Đang kiểm tra" : "Kiểm tra lại"}</button>
      </div>

      {error && <div className="form-error">{error}</div>}
      {!data && !error && <div className="empty-card">Đang kiểm tra hệ thống…</div>}

      {data && (
        <>
          <div className="readiness-grid">
            {Object.entries(data.modules || {}).map(([key, module]) => (
              <div className="readiness-card" key={key}>
                <div className="readiness-card-top">
                  <strong>{titleFor(key)}</strong>
                  <span className={`readiness-state state-${tone(module.state)}`}>{module.state || "unknown"}</span>
                </div>
                <p>{module.detail || "Chưa có mô tả trạng thái."}</p>
                {module.records !== undefined && <small>Records: {module.records}</small>}
                {module.active_tracks !== undefined && <small>Active tracks: {module.active_tracks}</small>}
                {module.last_seen && <small>Last seen: {new Date(module.last_seen).toLocaleString("vi-VN")}</small>}
              </div>
            ))}
          </div>
          <div className="readiness-principle"><ShieldCheck size={17}/>{data.principle}</div>
          <div className="readiness-note"><Activity size={17}/>“Operational” là phần mềm/lõi đang hoạt động; connector chỉ được coi là Connected khi thực sự nhận heartbeat hoặc telemetry.</div>
        </>
      )}
    </div>
  );
}
