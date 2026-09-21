import React, { useEffect, useState } from "react";
import { fetchEvidenceBlob, uploadEvidence } from "./api";

function EvidenceMedia({ item }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    let objectUrl = "";
    fetchEvidenceBlob(item.url)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => setSrc(""));
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [item.url]);

  if (!src) return <div className="media-loading">Đang tải tệp bảo mật…</div>;
  return item.media_type.startsWith("image/")
    ? <img src={src} alt={item.original_name} />
    : <video controls preload="metadata" src={src} />;
}

export default function EvidencePanel({ caseId, items = [], onUploaded }) {
  const [file, setFile] = useState(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (!file || !caseId) return;
    setBusy(true); setError("");
    try {
      const created = await uploadEvidence(caseId, file, note);
      onUploaded(created);
      setFile(null); setNote(""); e.target.reset();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!caseId) return <div className="empty-card">Chọn vụ việc thật để quản lý chứng cứ.</div>;

  return (
    <div className="evidence-wrap">
      <form onSubmit={submit} className="evidence-upload">
        <input type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/webm" onChange={(e)=>setFile(e.target.files?.[0] || null)} />
        <input value={note} onChange={(e)=>setNote(e.target.value)} placeholder="Ghi chú chứng cứ" maxLength={500} />
        <button className="primary-button" disabled={!file || busy}>{busy ? "Đang tải..." : "Upload"}</button>
      </form>
      <div className="form-hint">Tối đa 10 MB/tệp. Ảnh JPG/PNG/WebP; video MP4/WebM.</div>
      {error && <div className="form-error">{error}</div>}
      <div className="evidence-grid">
        {items.map((item) => (
          <div className="evidence-card" key={item.id}>
            <EvidenceMedia item={item} />
            <div className="evidence-meta">
              <strong>{item.original_name}</strong>
              <span>{item.note || "Không có ghi chú"}</span>
              <span>{Math.ceil(item.size_bytes / 1024)} KB</span>
            </div>
          </div>
        ))}
        {!items.length && <div className="empty-card">Chưa có ảnh/video chứng cứ.</div>}
      </div>
    </div>
  );
}
