# TRACE-AI — Pi App Studio packaging notes

## Mục tiêu
Dùng thư mục `web/` làm frontend chạy trong Pi Browser / Pi App Studio và `app/` làm backend API.

## MVP v0.5 hiện tại
- Dashboard mobile-first
- Pi SDK sandbox authentication scaffold
- Backend xác minh Pi access token qua `/v2/me`
- Danh sách và tạo vụ việc
- Hồ sơ người cần tìm
- Timeline API
- Bản đồ Leaflet/OpenStreetMap
- Marker từ sự kiện có tọa độ
- Search Zones từ backend
- Upload ảnh/video chứng cứ ở mức development MVP
- AI analysis panel dạng trợ lý, không ra quyết định cuối cùng

## Không được coi là production-ready
- RBAC hiện mới là scaffold bằng header
- Upload file hiện lưu local runtime
- Chưa có object storage/private signed delivery
- Chưa có migration framework
- Chưa có audit log ghi tự động cho mọi hành động
- Chưa có rate limiting / anti-abuse
- Chưa có encryption-at-rest do hạ tầng triển khai quyết định

## Không bật trong frontend
- Quét IP thiết bị lân cận
- Tự động truy cập vị trí của người dùng khác
- Dữ liệu thuê bao/CCCD không có cổng nghiệp vụ được cấp quyền
- Camera công cộng không được ủy quyền
- Thu thập sinh trắc học hoặc vân tay từ thiết bị thông thường

## Production checklist
1. Repo private.
2. HTTPS + domain production.
3. Pi SDK production mode.
4. Backend Pi-token verification.
5. User/role database thật thay cho header role.
6. Audit log bất biến cho dữ liệu nhạy cảm.
7. PostgreSQL + PostGIS + migration.
8. Private object storage cho ảnh/video.
9. Privacy policy + terms + retention policy.
10. Không nhúng secret trong web build.
11. CORS chỉ whitelist domain production.
12. Rate limiting, file scanning và quota upload.
