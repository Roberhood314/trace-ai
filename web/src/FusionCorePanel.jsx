import React, { useEffect, useState } from "react";
import { Activity, MapPinned, RefreshCw, Route, ShieldCheck } from "lucide-react";
import { Capacitor } from "@capacitor/core";
import { Geolocation } from "@capacitor/geolocation";
import {
  createFusionGeofence,
  fetchFusionStatus,
  fetchFusionTracks,
  fetchFusionTrajectory,
  reviewFusionTrack,
} from "./api";

function Metric({ label, value }) {
  return <div className="fusion-metric"><span>{label}</span><strong>{value ?? "—"}</strong></div>;
}

export default function FusionCorePanel({ role = "viewer" }) {
  const [status, setStatus] = useState(null);
  const [tracks, setTracks] = useState([]);
  const [selected, setSelected] = useState(null);
  const [trajectory, setTrajectory] = useState([]);
  const [message, setMessage] = useState("");
  const canReview = ["analyst", "commander", "admin"].includes(role);
  const canGeofence = ["commander", "admin"].includes(role);

  async function refresh() {
    setMessage("");
    try {
      const [s, t] = await Promise.all([fetchFusionStatus(), fetchFusionTracks(100)]);
      setStatus(s);
      setTracks(t.items || []);
    } catch (error) {
      setMessage(error.message || "Không thể đọc Fusion Core");
    }
  }

  useEffect(() => { refresh(); }, []);

  async function openTrajectory(track) {
    setSelected(track);
    try {
      const result = await fetchFusionTrajectory(track.id, 200);
      setTrajectory(result.points || []);
    } catch (error) {
      setMessage(error.message || "Không thể tải trajectory");
    }
  }

  async function review(track, decision) {
    try {
      await reviewFusionTrack(track.id, decision, "");
      setMessage(`Đã cập nhật review: ${decision}`);
      await refresh();
    } catch (error) {
      setMessage(error.message || "Không thể cập nhật review");
    }
  }

  async function createGeofenceHere() {
    setMessage("");
    try {
      let position;
      if (Capacitor.isNativePlatform()) {
        const permission = await Geolocation.checkPermissions();
        if (permission.location !== "granted") {
          const requested = await Geolocation.requestPermissions();
          if (requested.location !== "granted") throw new Error("Bạn chưa cấp quyền vị trí.");
        }
        position = await Geolocation.getCurrentPosition({ enableHighAccuracy: true, timeout: 10000 });
      } else {
        if (!navigator.geolocation) throw new Error("Thiết bị không hỗ trợ GPS.");
        position = await new Promise((resolve, reject) =>
          navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: 10000 })
        );
      }
      await createFusionGeofence({
        name: "Mobile geofence",
        center_latitude: position.coords.latitude,
        center_longitude: position.coords.longitude,
        radius_m: 1000,
        severity: "warning",
      });
      setMessage("Đã tạo geofence 1 km tại vị trí hiện tại.");
      await refresh();
    } catch (error) {
      setMessage(error.message || "Không lấy được GPS");
    }
  }

  return (
    <div className="fusion-console">
      <div className="fusion-toolbar">
        <div>
          <div className="eyebrow">TRACE FUSION CORE V1</div>
          <h4>UAS Operations Console</h4>
          <p>Ingest → Correlation → Classification → Trajectory → Geofence → Human Review</p>
        </div>
        <div className="fusion-actions">
          <button className="secondary-button" onClick={refresh}><RefreshCw size={15}/>Refresh</button>
          {canGeofence && <button className="primary-button" onClick={createGeofenceHere}><MapPinned size={15}/>Geofence 1 km</button>}
        </div>
      </div>

      {status ? (
        <>
          <div className="fusion-core-grid">
            {[
              ["Signal ingest", status.signal_ingest],
              ["Track correlation", status.track_correlation],
              ["Classification", status.classification],
              ["Trajectory", status.trajectory],
              ["Geofence", status.geofence],
              ["Human review", status.human_review],
            ].map(([label, value]) => (
              <div className="fusion-core-card" key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
          <div className="fusion-metrics">
            <Metric label="Active tracks" value={status.active_tracks} />
            <Metric label="Pending review" value={status.pending_review} />
            <Metric label="Geofence alerts" value={status.geofence_alerts} />
          </div>
        </>
      ) : <div className="empty-card">Fusion Core chưa đọc được trạng thái.</div>}

      {message && <div className="notice"><Activity size={17}/>{message}</div>}

      <div className="fusion-track-list">
        {tracks.map((track) => (
          <div className="fusion-track-card" key={track.id}>
            <div className="fusion-track-head">
              <div>
                <strong>{track.track_key}</strong>
                <small>{track.classification} · confidence {Math.round((track.confidence || 0) * 100)}%</small>
              </div>
              <span className={`fusion-state ${track.geofence_state}`}>{track.geofence_state}</span>
            </div>
            <div className="fusion-track-meta">
              <span>Sources: {track.source_count}</span>
              <span>Alt: {track.altitude_m ?? "—"} m</span>
              <span>Speed: {track.speed_mps ?? "—"} m/s</span>
              <span>Heading: {track.heading_deg ?? "—"}°</span>
              <span>Review: {track.review_status}</span>
            </div>
            <div className="fusion-track-actions">
              <button className="secondary-button" onClick={() => openTrajectory(track)}><Route size={14}/>Trajectory</button>
              {canReview && <>
                <button className="secondary-button" onClick={() => review(track, "verified")}><ShieldCheck size={14}/>Verified</button>
                <button className="secondary-button" onClick={() => review(track, "needs_review")}>Needs review</button>
                <button className="secondary-button" onClick={() => review(track, "rejected")}>Rejected</button>
              </>}
            </div>
          </div>
        ))}
        {!tracks.length && <div className="empty-card">Chưa có Fusion Track. Hãy gửi telemetry Remote ID/radar/RF hoặc observation từ Mobile Camera/GPS.</div>}
      </div>

      {selected && (
        <div className="fusion-trajectory">
          <h4>Trajectory · {selected.track_key}</h4>
          <div className="fusion-points">
            {trajectory.slice(-30).map((point, index) => (
              <div key={index}>
                <span>{new Date(point.observed_at).toLocaleTimeString("vi-VN")}</span>
                <strong>{point.latitude?.toFixed?.(5) ?? "—"}, {point.longitude?.toFixed?.(5) ?? "—"}</strong>
                <small>{point.altitude_m ?? "—"} m · {point.speed_mps ?? "—"} m/s · {point.heading_deg ?? "—"}°</small>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
