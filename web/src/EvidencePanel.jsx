import React, { useState } from "react";
import { absoluteAssetUrl, uploadEvidence } from "./api";

export default function EvidencePanel({ caseId, items = [], onUploaded }) {
  const [file, setFile] = useState(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (!file || !caseId) return;
    setBusy(true);
    setError("");
    try {
      const created = await uploadEvidence(caseId, file, note);
      onUploaded(created);
      setFile(null);
      setNote("");
      e.target.reset();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!caseId) return <div className="empty-card">Chứng cứ demo chưa nối backend.</div>;

  return (
    <div className="evidence-wrap">
      <form onSubmit={submit} className="evidence-upload">
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp,video/mp4,video/webm"
          onChange={(e)=>setFile(e.target.files?.[0] || null)}
        />
        <input value={note} onChange={(e)=>setNote(e.target.value)} placeholder="Ghi chú chứng cứ" />
        <button className="primary-button" disabled={!file || busy}>{busy ? "Đang tải..." : "Upload"}</button>
      </form>
      {error && <div className="form-error">{error}</div>}

      <div className="evidence-grid">
        {items.map((item) => (
          <div className="evidence-card" key={item.id}>
            {item.media_type.startsWith("image/") ? (
              <img src={absoluteAssetUrl(item.url)} alt={item.original_name} />
            ) : (
              <video controls preload="metadata" src={absoluteAssetUrl(item.url)} />
            )}
            <div className="evidence-meta">
              <strong>{item.original_name}</strong>
              <span>{item.note || "Không có ghi chú"}</span>
            </div>
          </div>
        ))}
        {!items.length && <div className="empty-card">Chưa có ảnh/video chứng cứ.</div>}
      </div>
    </div>
  );
}
