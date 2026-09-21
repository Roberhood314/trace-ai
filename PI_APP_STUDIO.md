# TRACE-AI — Pi App Studio packaging notes

## Mục tiêu
Dùng thư mục `web/` làm frontend chạy trong Pi Browser / Pi App Studio.

## MVP hiện tại
- Dashboard mobile-first
- Danh sách vụ việc demo
- Command view
- Timeline
- Search Zones
- AI analysis panel
- Pi SDK sandbox authentication scaffold

## Chưa bật trong frontend
- Thu thập vị trí nền
- Quét IP thiết bị lân cận
- Camera công cộng
- Dữ liệu CCCD/thuê bao
- Bất kỳ nguồn dữ liệu nhạy cảm nào chưa có cơ chế phân quyền

Các chức năng trên phải đi qua backend và chỉ kết nối với nguồn có quyền hợp lệ.

## Production checklist
1. Xác minh domain/URL production.
2. Pi SDK production mode.
3. Backend token verification.
4. HTTPS.
5. RBAC + audit log.
6. Privacy policy + terms.
7. Không nhúng secret trong web build.
8. Kết nối API thật thay cho demo data.
