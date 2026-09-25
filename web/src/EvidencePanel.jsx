import React, { useEffect, useState } from "react";
import { Camera, CameraResultType, CameraSource } from "@capacitor/camera";
import { Capacitor } from "@capacitor/core";
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

async function captureNativePhoto() {
  const permission = await Camera.checkPermissions();
  if (permission.camera !== "granted") {
    const requested = await Camera.requestPermissions({ permissions: ["camera"] });
    if (requested.camera !== "granted") throw new Error("Bạn chưa cấp quyền Camera.");
  }
  const photo = await Camera.getPhoto({
    quality: 88,
    resultType: CameraResultType.Uri,
    source: CameraSource.Camera,
    correctOrientation: true,
    saveToGallery: false,
  });
  if (!photo.webPath) throw new Error("Không nhận được ảnh từ Camera.");
  const response = await fetch(photo.webPath);
  const blob = await response.blob();
  return new File([blob], `trace-camera-${Date.now()}.${photo.format || "jpeg"}`, {
    type: blob.type || `image/${photo.format || "jpeg"}`,
  });
}

export default function EvidencePanel({ caseId, items = [], onUploaded }) {
  const [file, setFile] = useState(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function takePhoto() {
    setError("");
    try {
      if (!Capacitor.isNativePlatform()) {
        throw new Error("Chụp Camera native chỉ khả dụng trên ứng dụng Android/iOS.");
      }
      setFile(await captureNativePhoto());
    } catch (err) {
      setError(err.message || "Không thể mở Camera.");
    }
  }

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
        <button type="button" className="secondary-button" onClick={takePhoto}>Chụp ảnh bằng Camera</button>
        <input type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/webm" onChange={(e)=>setFile(e.target.files?.[0] || null)} />
        {file && <span className="form-hint">Đã chọn: {file.name}</span>}
        <input value={note} onChange={(e)=>setNote(e.target.value)} placeholder="Ghi chú chứng cứ" maxLength={500} />
        <button className="primary-button" disabled={!file || busy}>{busy ? "Đang tải..." : "Upload"}</button>
      </form>
      <div className="form-hint">Camera chỉ được mở sau khi bạn chủ động bấm Chụp ảnh. Tối đa 10 MB/tệp.</div>
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
