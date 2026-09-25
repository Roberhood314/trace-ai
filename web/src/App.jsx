import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Bot,
  Camera,
  ChevronRight,
  Clock3,
  LogIn,
  MapPinned,
  Radar,
  ShieldCheck,
  UserRoundSearch
} from "lucide-react";
import { authenticatePi, loadPiSdk, startTestPayment } from "./pi";
import MapPanel from "./MapPanel";
import CreateCaseModal from "./CreateCaseModal";
import PersonPanel from "./PersonPanel";
import EvidencePanel from "./EvidencePanel";
import TimelinePanel from "./TimelinePanel";
import ZonesPanel from "./ZonesPanel";
import AIAnalysisPanel from "./AIAnalysisPanel";
import AuditPanel from "./AuditPanel";
import AdminPanel from "./AdminPanel";
import WantedRadarPanel from "./WantedRadarPanel";
import FusionCorePanel from "./FusionCorePanel";
import { deleteMyAccount, fetchCases, fetchEvidence, fetchPerson, fetchTimeline, fetchZones, reviewerLogin, testPaymentConfig } from "./api";
 

function Badge({ children, tone = "neutral" }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

function StatCard({ icon: Icon, label, value }) {
  return (
    <div className="stat-card">
      <div className="stat-icon"><Icon size={18} /></div>
      <div>
        <div className="stat-label">{label}</div>
        <div className="stat-value">{value}</div>
      </div>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [activeCase, setActiveCase] = useState(null);
  const [tab, setTab] = useState("overview");
  const [piReady, setPiReady] = useState(false);
  const [paymentEnabled, setPaymentEnabled] = useState(false);
  const [paymentStatus, setPaymentStatus] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [reviewerOpen, setReviewerOpen] = useState(false);
  const [reviewerUser, setReviewerUser] = useState("");
  const [reviewerPassword, setReviewerPassword] = useState("");
  const [reviewerError, setReviewerError] = useState("");
  const [liveCases, setLiveCases] = useState([]);
  const [person, setPerson] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [zones, setZones] = useState([]);
  const [evidence, setEvidence] = useState([]);

  useEffect(() => {
    loadPiSdk().then(setPiReady);
    testPaymentConfig().then(({ enabled }) => setPaymentEnabled(enabled)).catch(() => {});
    loadCases().catch(() => {});
  }, []);

  useEffect(() => {
    if (!activeCase?.dbId) {
      setPerson(null); setTimeline([]); setZones([]); setEvidence([]);
      return;
    }
    Promise.all([
      fetchPerson(activeCase.dbId),
      fetchTimeline(activeCase.dbId),
      fetchZones(activeCase.dbId),
      fetchEvidence(activeCase.dbId),
    ]).then(([p, t, z, e]) => {
      setPerson(p); setTimeline(t); setZones(z); setEvidence(e);
    }).catch(() => {});
  }, [activeCase?.dbId]);

  const zoneScore = useMemo(() => zones.length ? Math.max(...zones.map(z=>z.score)) : 0, [zones]);

  async function loadCases() {
    const rows = await fetchCases();
    const mapped = rows.map((row) => ({
      id: row.case_code,
      dbId: row.id,
      title: row.title,
      status: row.status,
      lastSeen: "Chưa có dữ liệu",
      radius: "Chưa tính",
      confidence: 0,
      priority: "Mới"
    }));
    setLiveCases(mapped);
    setActiveCase(mapped[0] || null);
    return mapped;
  }

  async function signIn() {
    try {
      const profile = await authenticatePi();
      setUser(profile);
      await loadCases();
    } catch (error) {
      alert(error.message || "Không thể đăng nhập Pi hoặc tải dữ liệu lúc này.");
    }
  }

  async function signInReviewer(event) {
    event.preventDefault();
    setReviewerError("");
    try {
      const profile = await reviewerLogin(reviewerUser, reviewerPassword);
      setUser({ username: profile.username, role: profile.role, verified: true, reviewer: true });
      setReviewerOpen(false);
      setReviewerPassword("");
      await loadCases();
    } catch (error) {
      setReviewerError(error.message || "Không thể đăng nhập tài khoản kiểm thử.");
    }
  }

  async function deleteAccount() {
    if (!window.confirm("Xóa tài khoản TRACE AI và dữ liệu cá nhân liên kết? Hành động này không thể hoàn tác.")) return;
    try {
      await deleteMyAccount();
      setUser(null);
      setActiveCase(null);
      setLiveCases([]);
      alert("Tài khoản đã được xóa.");
    } catch (error) {
      alert(error.message || "Không thể xóa tài khoản.");
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">SEARCH INTELLIGENCE PLATFORM</div>
          <div className="brand-row">
            <Radar size={26} />
            <h1>TRACE-AI</h1>
          </div>
        </div>

        <div style={{display:"flex",gap:8,alignItems:"center"}}>
          <button className="profile-button" onClick={signIn}>
            <LogIn size={17} />
            <span>{user ? `${user.username || "User"} · ${user.role || ""}` : piReady ? "Đăng nhập Pi" : "Đăng nhập"}</span>
          </button>
          {!user && <button className="secondary-button" onClick={()=>setReviewerOpen(true)}>Reviewer</button>}
          {user && !user.reviewer && <button className="secondary-button" onClick={deleteAccount}>Xóa tài khoản</button>}
        </div>
      </header>

      {paymentEnabled && piReady && user?.verified && (
        <section style={{ padding: "12px 20px" }}>
          <button type="button" onClick={() => {
            setPaymentStatus("Đang mở ví Pi...");
            try { startTestPayment(setPaymentStatus); }
            catch (error) { setPaymentStatus(error.message); }
          }}>Thử thanh toán 0,01 Pi (Testnet)</button>
          <p role="status">{paymentStatus}</p>
        </section>
      )}

      <main>
        <section className="hero">
          <div>
            <Badge tone="success"><ShieldCheck size={13} /> Phiên bản MVP an toàn dữ liệu</Badge>
            <h2>Trung tâm điều phối truy tìm và phân tích dấu vết</h2>
            <p>
              Tổng hợp dữ liệu đã được cấp quyền, xây dựng timeline, vùng tìm kiếm và gợi ý
              ưu tiên để hỗ trợ đội hiện trường.
            </p>
          </div>
          <div className="hero-radar">
            <div className="radar-ring r1"></div>
            <div className="radar-ring r2"></div>
            <div className="radar-ring r3"></div>
            <div className="radar-dot"></div>
          </div>
        </section>

        <section className="stats-grid">
          <StatCard icon={UserRoundSearch} label="Vụ việc đang mở" value={liveCases.length} />
          <StatCard icon={Camera} label="Chứng cứ" value={evidence.length} />
          <StatCard icon={MapPinned} label="Vùng ưu tiên" value={zones.length} />
          <StatCard icon={Activity} label="Điểm tin cậy cao nhất" value={zones.length ? `${zoneScore}%` : "—"} />
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <div className="eyebrow">ACTIVE CASES</div>
              <h3>Hồ sơ đang xử lý</h3>
            </div>
            {!user?.reviewer && <button className="primary-button" onClick={() => setShowCreate(true)}>+ Tạo vụ việc</button>}
          </div>

          <div className="case-list">
            {liveCases.map((item) => (
              <button
                key={item.id}
                onClick={() => setActiveCase(item)}
                className={`case-card ${activeCase.id === item.id ? "active" : ""}`}
              >
                <div className="case-topline">
                  <strong>{item.id}</strong>
                  <Badge tone={item.priority === "Cao" ? "danger" : "warning"}>{item.priority}</Badge>
                </div>
                <div className="case-title">{item.title}</div>
                <div className="case-meta">
                  <span><Clock3 size={14} /> {item.lastSeen}</span>
                  <span><MapPinned size={14} /> {item.radius}</span>
                </div>
                <ChevronRight className="case-arrow" size={18} />
              </button>
            ))}
            {!liveCases.length && <div className="empty-card">Chưa có vụ việc. Đăng nhập và tạo dữ liệu thật để bắt đầu.</div>}
          </div>
        </section>

        {activeCase && <section className="panel command-panel">
          <div className="panel-header">
            <div>
              <div className="eyebrow">COMMAND VIEW</div>
              <h3>{activeCase.id}</h3>
            </div>
            <Badge tone="info">{activeCase.status}</Badge>
          </div>

          <div className="tabs">
            {[
              ["overview", "Tổng quan"],
              ["wanted", "Radar truy nã"],
              ["fusion", "UAS Fusion"],
              ["profile", "Hồ sơ"],
              ["timeline", "Timeline"],
              ["zones", "Vùng tìm kiếm"],
              ["evidence", "Chứng cứ"],
              ["ai", "AI phân tích"],
              ...(user && ["commander","admin","reviewer"].includes(user.role) ? [["audit","Audit"]] : []),
              ...(["admin","reviewer"].includes(user?.role) ? [["admin","Quản trị"]] : [])
            ].map(([key, label]) => (
              <button
                key={key}
                className={tab === key ? "tab active" : "tab"}
                onClick={() => setTab(key)}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === "overview" && (
            <div className="overview-grid">
              <MapPanel timeline={timeline} zones={zones} />

              <div className="summary-card">
                <h4>Thông tin nhanh</h4>
                <div className="summary-row"><span>Lần cuối xác minh</span><strong>{timeline.length ? new Date(timeline[timeline.length-1].event_time).toLocaleString("vi-VN") : activeCase.lastSeen}</strong></div>
                <div className="summary-row"><span>Bán kính lớn nhất</span><strong>{zones.length ? `${(Math.max(...zones.map(z=>z.radius_m))/1000).toFixed(1)} km` : activeCase.radius}</strong></div>
                <div className="summary-row"><span>Độ tin cậy dấu vết</span><strong>{timeline.length ? `${Math.round(Math.max(...timeline.map(x=>x.confidence ?? 0))*100)}%` : `${activeCase.confidence}%`}</strong></div>
                <div className="notice">
                  <AlertTriangle size={18} />
                  Chỉ sử dụng nguồn dữ liệu có quyền truy cập hợp lệ và được ghi audit log.
                </div>
              </div>
            </div>
          )}

          {tab === "wanted" && (
            <WantedRadarPanel role={user?.role || "viewer"} />
          )}

          {tab === "fusion" && (
            <FusionCorePanel role={user?.role || "viewer"} />
          )}

          {tab === "profile" && (
            <PersonPanel caseId={activeCase.dbId} person={person} onCreated={setPerson} />
          )}

          {tab === "timeline" && (
            <TimelinePanel caseId={activeCase.dbId} items={timeline} onCreated={(item)=>setTimeline(prev=>[...prev,item].sort((a,b)=>new Date(a.event_time)-new Date(b.event_time)))} />
          )}

          {tab === "zones" && (
            <ZonesPanel caseId={activeCase.dbId} items={zones} onCreated={(item)=>setZones(prev=>[...prev,item].sort((a,b)=>b.score-a.score))} />
          )}

          {tab === "evidence" && (
            <EvidencePanel caseId={activeCase.dbId} items={evidence} onUploaded={(item)=>setEvidence((prev)=>[item,...prev])} />
          )}

          {tab === "ai" && (
            <AIAnalysisPanel caseId={activeCase.dbId} />
          )}
          {tab === "audit" && (
            <AuditPanel caseId={activeCase.dbId} />
          )}
          {tab === "admin" && (
            <AdminPanel />
          )}        </section>}
      </main>

      {reviewerOpen && (
        <div className="modal-backdrop" onMouseDown={()=>setReviewerOpen(false)}>
          <div className="modal-card" onMouseDown={e=>e.stopPropagation()}>
            <div className="modal-header"><div><div className="eyebrow">GOOGLE PLAY REVIEW</div><h3>Tài khoản kiểm thử</h3></div><button className="icon-button" onClick={()=>setReviewerOpen(false)}>×</button></div>
            <form className="case-form" onSubmit={signInReviewer}>
              <label>Tên đăng nhập<input required autoComplete="username" value={reviewerUser} onChange={e=>setReviewerUser(e.target.value)} /></label>
              <label>Mật khẩu<input required type="password" autoComplete="current-password" value={reviewerPassword} onChange={e=>setReviewerPassword(e.target.value)} /></label>
              {reviewerError && <div className="form-error">{reviewerError}</div>}
              <button className="primary-button">Đăng nhập kiểm thử</button>
            </form>
          </div>
        </div>
      )}

      {user?.reviewer && <div className="notice" style={{margin:"12px 20px"}}>Google Play Reviewer Mode · chỉ đọc, không thay đổi dữ liệu production.</div>}

      {showCreate && (
        <CreateCaseModal
          onClose={() => setShowCreate(false)}
          onCreated={(created) => {
            const uiCase = {
              id: created.case_code,
              dbId: created.id,
              title: created.title,
              status: created.status || "open",
              lastSeen: "Chưa có dữ liệu",
              radius: "Chưa tính",
              confidence: 0,
              priority: "Mới"
            };
            setLiveCases((prev) => [uiCase, ...prev]);
            setActiveCase(uiCase);
          }}
        />
      )}

      <nav className="bottom-nav">
        <button className={tab==="overview"?"active":""} onClick={()=>setTab("overview")}><Radar size={20} /><span>Trung tâm</span></button>
        <button className={tab==="zones"?"active":""} onClick={()=>setTab("zones")} disabled={!activeCase}><MapPinned size={20} /><span>Bản đồ</span></button>
        <button className={tab==="evidence"?"active":""} onClick={()=>setTab("evidence")} disabled={!activeCase}><Camera size={20} /><span>Dữ liệu</span></button>
        <button className={tab==="ai"?"active":""} onClick={()=>setTab("ai")} disabled={!activeCase}><Bot size={20} /><span>AI</span></button>
      </nav>
    </div>
  );
}
