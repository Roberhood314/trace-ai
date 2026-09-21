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
import { authenticatePi, initPi } from "./pi";
import MapPanel from "./MapPanel";
import CreateCaseModal from "./CreateCaseModal";
import { demoCases, demoTimeline, demoZones } from "./demoData";

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
  const [activeCase, setActiveCase] = useState(demoCases[0]);
  const [tab, setTab] = useState("overview");
  const [piReady, setPiReady] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [liveCases, setLiveCases] = useState([]);

  useEffect(() => {
    setPiReady(initPi());
  }, []);

  const zoneScore = useMemo(
    () => Math.max(...demoZones.map((z) => z.score)),
    []
  );

  async function signIn() {
    try {
      const profile = await authenticatePi();
      setUser(profile);
    } catch (error) {
      alert("Không thể đăng nhập Pi lúc này. Bạn vẫn có thể xem giao diện demo.");
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

        <button className="profile-button" onClick={signIn}>
          <LogIn size={17} />
          <span>{user ? user.username : piReady ? "Đăng nhập Pi" : "Demo"}</span>
        </button>
      </header>

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
          <StatCard icon={UserRoundSearch} label="Vụ việc đang mở" value="2" />
          <StatCard icon={Camera} label="Nguồn đã xác minh" value="14" />
          <StatCard icon={MapPinned} label="Vùng ưu tiên" value="3" />
          <StatCard icon={Activity} label="Điểm tin cậy cao nhất" value={`${zoneScore}%`} />
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <div className="eyebrow">ACTIVE CASES</div>
              <h3>Hồ sơ đang xử lý</h3>
            </div>
            <button className="primary-button" onClick={() => setShowCreate(true)}>+ Tạo vụ việc</button>
          </div>

          <div className="case-list">
            {[...liveCases, ...demoCases].map((item) => (
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
          </div>
        </section>

        <section className="panel command-panel">
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
              ["timeline", "Timeline"],
              ["zones", "Vùng tìm kiếm"],
              ["ai", "AI phân tích"]
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
              <MapPanel />

              <div className="summary-card">
                <h4>Thông tin nhanh</h4>
                <div className="summary-row"><span>Lần cuối xác minh</span><strong>{activeCase.lastSeen}</strong></div>
                <div className="summary-row"><span>Bán kính hiện tại</span><strong>{activeCase.radius}</strong></div>
                <div className="summary-row"><span>Độ tin cậy tổng hợp</span><strong>{activeCase.confidence}%</strong></div>
                <div className="notice">
                  <AlertTriangle size={18} />
                  Chỉ sử dụng nguồn dữ liệu có quyền truy cập hợp lệ và được ghi audit log.
                </div>
              </div>
            </div>
          )}

          {tab === "timeline" && (
            <div className="timeline">
              {demoTimeline.map((item) => (
                <div className="timeline-item" key={item.time + item.label}>
                  <div className="time">{item.time}</div>
                  <div className="timeline-dot"></div>
                  <div>
                    <strong>{item.label}</strong>
                    <p>{item.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {tab === "zones" && (
            <div className="zone-list">
              {demoZones.map((zone) => (
                <div className="zone-card" key={zone.name}>
                  <div className="zone-score">{zone.score}</div>
                  <div className="zone-content">
                    <div className="zone-title-row">
                      <strong>{zone.name}</strong>
                      <span>{zone.radius}</span>
                    </div>
                    <div className="progress"><div style={{ width: `${zone.score}%` }}></div></div>
                    <p>{zone.reason}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {tab === "ai" && (
            <div className="ai-card">
              <div className="ai-icon"><Bot size={28} /></div>
              <div>
                <h4>AI Search Assistant</h4>
                <p>
                  Dữ liệu hiện tại ưu tiên Zone A do có dấu vết xác minh gần nhất và hướng
                  di chuyển phù hợp. Zone B cần được rà soát song song nếu xuất hiện bằng chứng mới.
                </p>
                <div className="ai-disclaimer">
                  AI chỉ đưa ra gợi ý hỗ trợ. Kết luận và quyết định nghiệp vụ phải do người có thẩm quyền xác minh.
                </div>
              </div>
            </div>
          )}
        </section>
      </main>

      {showCreate && (
        <CreateCaseModal
          onClose={() => setShowCreate(false)}
          onCreated={(created) => {
            const uiCase = {
              id: created.case_code,
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
        <button className="active"><Radar size={20} /><span>Trung tâm</span></button>
        <button><MapPinned size={20} /><span>Bản đồ</span></button>
        <button><Camera size={20} /><span>Dữ liệu</span></button>
        <button><Bot size={20} /><span>AI</span></button>
      </nav>
    </div>
  );
}
