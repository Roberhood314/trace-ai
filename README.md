# TRACE-AI — Pi-ready Release Candidate

TRACE-AI là web app hỗ trợ quản lý vụ việc tìm kiếm/người mất tích, timeline dấu vết, bản đồ vùng tìm kiếm, chứng cứ và phân tích hỗ trợ. Frontend được thiết kế mobile-first cho Pi Browser/Pi App Studio; backend FastAPI đảm nhiệm xác thực, dữ liệu và audit.

## Release
- Version: `1.5.0-rc2`
- Frontend: React + Vite + Leaflet + Pi SDK
- Backend: FastAPI + SQLAlchemy
- Dev DB: SQLite
- Deployment DB: PostgreSQL/PostGIS-ready

## Chức năng
- Đăng nhập Pi SDK và xác minh token server-side.
- Tài khoản nội bộ gắn Pi UID; role viewer/analyst/commander/admin.
- Tạo và quản lý vụ việc.
- Hồ sơ người cần tìm.
- Timeline dấu vết có nguồn, tọa độ và độ tin cậy.
- Bản đồ marker + vùng tìm kiếm A/B/C.
- Upload ảnh/video chứng cứ có kiểm soát truy cập.
- Audit log cho thao tác nhạy cảm.
- Bảng quản trị quyền.
- AI Search Assistant dạng tổng hợp/decision-support, không tự ra quyết định nghiệp vụ.
- Radar tra soát truy nã dạng trực quan hóa dữ liệu.
- Đồng bộ thủ công dữ liệu truy nã công khai từ `https://truyna.bocongan.gov.vn/Đối-tượng-truy-nã`, giữ nguyên nguồn và link hồ sơ chính thức.
- Privacy Policy template và placeholder xác minh domain Pi.

## Không phải chức năng của bản release
Ứng dụng không tự quét IP/GPS của người xung quanh, không thu thập dữ liệu thuê bao/CCCD/camera công cộng trái quyền, không coi điện thoại thường là camera nhiệt/vân tay pháp y. Các nguồn dữ liệu nghiệp vụ phải được tích hợp qua gateway được cấp quyền.

## Chạy local

Backend:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
export DEV_AUTH_BYPASS=true
uvicorn app.main:app --reload
```

Frontend:

```bash
cd web
npm install
cp .env.example .env
npm run dev
```

## Test

```bash
PYTHONPATH=. APP_ENV=development DEV_AUTH_BYPASS=true \
DATABASE_URL=sqlite:///./test_trace_ai.db python -m pytest -q

cd web
npm install
npm run build
```

## Production
Đọc [DEPLOYMENT.md](./DEPLOYMENT.md), [SECURITY.md](./SECURITY.md) và [PI_APP_STUDIO.md](./PI_APP_STUDIO.md) trước khi đưa dữ liệu thật vào hệ thống.

**Bắt buộc:** đổi `APP_SECRET`, tắt `DEV_AUTH_BYPASS`, cấu hình HTTPS/CORS, khai báo bootstrap admin, dùng storage riêng cho evidence, cấu hình retention/backup và thay thông tin operator trong Privacy Policy.

## Production controls (1.5.0-rc2 hardening)
- Alembic revision `0003_security_operations` adds indexed queue lookup and tamper-evident audit hashes.
- The worker recovers jobs abandoned by an interrupted deploy after a bounded lease.
- API sessions are short-lived (30 minutes by default); public, write and login routes have app-level rate limits.
- `/health/ready` reports database and queue state; `/metrics` remains token-protected in production.
- CI runs migrations, tests, SAST/dependency audit, load smoke, and a PostgreSQL backup–restore check. Edge WAF, encrypted offsite backups and malware scanning remain mandatory hosting controls for real sensitive evidence.


## Nguồn truy nã Bộ Công an
TRACE-AI chỉ đồng bộ dữ liệu công khai được hiển thị trên Cổng thông tin truy nã của Bộ Công an. Việc đồng bộ được kích hoạt thủ công bởi role `commander` hoặc `admin`, giới hạn số trang mỗi lần để tránh tạo tải không cần thiết. Giao diện "radar" chỉ là trực quan hóa kết quả tra cứu trong dữ liệu đã nhập; không phải radar vật lý và không quét thiết bị/người ở gần.
