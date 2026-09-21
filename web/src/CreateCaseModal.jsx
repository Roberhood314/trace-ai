import React, { useState } from "react";
import { createCase } from "./api";

export default function CreateCaseModal({ onClose, onCreated }) {
  const [form, setForm] = useState({
    case_code: "",
    title: "",
    legal_reference: "",
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  function update(name, value) {
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const created = await createCase({
        ...form,
        legal_reference: form.legal_reference || null,
      });
      onCreated(created);
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal-card" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <div className="eyebrow">NEW CASE</div>
            <h3>Tạo vụ việc</h3>
          </div>
          <button className="icon-button" onClick={onClose}>×</button>
        </div>

        <form onSubmit={submit} className="case-form">
          <label>
            Mã vụ việc
            <input required value={form.case_code} onChange={(e) => update("case_code", e.target.value)} placeholder="MP-2026-003" />
          </label>
          <label>
            Tiêu đề
            <input required value={form.title} onChange={(e) => update("title", e.target.value)} placeholder="Người mất tích..." />
          </label>
          <label>
            Công văn / căn cứ
            <input value={form.legal_reference} onChange={(e) => update("legal_reference", e.target.value)} placeholder="Tùy chọn" />
          </label>

          {error && <div className="form-error">{error}</div>}

          <div className="form-actions">
            <button type="button" className="secondary-button" onClick={onClose}>Hủy</button>
            <button className="primary-button" disabled={saving}>{saving ? "Đang lưu..." : "Tạo vụ việc"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}
