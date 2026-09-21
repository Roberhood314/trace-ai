import React, { useEffect, useMemo, useState } from "react";
import { RefreshCw, Search, ShieldCheck } from "lucide-react";
import { fetchWanted, fetchWantedSourceStatus, syncWanted } from "./api";

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

export default function WantedRadarPanel({ role = "viewer" }) {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
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
    <div className="wanted-radar-layout">
      <section className="wanted-radar-card">
        <div className="wanted-radar-head">
          <div>
            <div className="eyebrow">OFFICIAL WANTED DATA RADAR</div>
            <h3>Radar tra soát truy nã</h3>
          </div>
          <span className="source-badge"><ShieldCheck size={14}/> Nguồn Bộ Công an</span>
        </div>

        <form
          className="wanted-search"
          onSubmit={(e) => { e.preventDefault(); load(query); }}
        >
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
          Radar này là giao diện trực quan hóa kết quả tra cứu trong cơ sở dữ liệu đã đồng bộ; không quét IP, GPS, thiết bị hay người dùng ở khu vực xung quanh.
        </p>
        {message && <div className={message.includes("xong") ? "form-success" : "form-error"}>{message}</div>}
      </section>

      <section className="wanted-results">
        {selected && (
          <div className="wanted-selected">
            <div className="eyebrow">SELECTED RECORD</div>
            <h3>{selected.full_name}</h3>
            <div className="wanted-detail-grid">
              <div><span>Năm sinh</span><strong>{selected.birth_year || "—"}</strong></div>
              <div><span>Số/ngày quyết định</span><strong>{selected.warrant_reference || "—"}</strong></div>
              <div className="wide"><span>Tội danh</span><strong>{selected.offense || "—"}</strong></div>
              <div className="wide"><span>Nơi ĐKTT</span><strong>{selected.registered_address || "—"}</strong></div>
              <div className="wide"><span>Đơn vị ra quyết định</span><strong>{selected.issuing_unit || "—"}</strong></div>
            </div>
            {selected.detail_url && <a className="official-link" href={selected.detail_url} target="_blank" rel="noreferrer">Xem hồ sơ tại nguồn Bộ Công an</a>}
          </div>
        )}

        <div className="wanted-list">
          {items.map((item) => (
            <button key={item.id} className={selected?.id === item.id ? "wanted-row active" : "wanted-row"} onClick={() => setSelected(item)}>
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
