# TRACE-AI Web / Pi App Studio

Frontend mobile-first dành cho Pi Browser và luồng import/upload vào Pi App Studio.

## Chạy local

```bash
cd web
npm install
npm run dev
```

## Build

```bash
npm run build
```

Output nằm tại `web/dist`.

## Biến môi trường

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_PI_SANDBOX=true
```

## Pi SDK

Pi SDK được nạp trong `index.html`. Frontend nhận access token từ Pi SDK và gửi về backend để xác minh với Pi Platform.

Khi production:
- đổi `VITE_PI_SANDBOX=false`;
- bắt buộc HTTPS;
- backend xác minh token;
- không lưu API key/secret ở frontend;
- chỉ yêu cầu scope thật sự cần thiết.

## v0.5

Frontend đã có:
- dashboard;
- tạo vụ việc;
- hồ sơ người cần tìm;
- timeline;
- bản đồ + marker;
- vùng tìm kiếm;
- upload chứng cứ;
- AI assistant panel.

Upload ảnh/video hiện là **development MVP**. Dữ liệu thật cần private object storage và access control ở backend trước khi vận hành.
